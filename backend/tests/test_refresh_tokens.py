"""
Tests for app.services.refresh_tokens (the rules: rotation, reuse detection, leeway, expiry, revocation)
and the access-token helpers in app.services.auth. They run against an in-memory store with a clock the
test moves; the SQL store has its own test (test_refresh_token_store_pg.py).
"""

import hashlib
import os
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import refresh_tokens as rt
from app.services.auth import create_access_token, decode_access_token, issued_before
from app.config import settings
from tests.refresh_store_fake import InMemoryRefreshStore

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
POLICY = rt.Policy(idle=timedelta(days=30), absolute=timedelta(days=90), leeway=timedelta(seconds=10))


def after(**kw):
    return T0 + timedelta(**kw)


class TestRefreshTokens(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = InMemoryRefreshStore()
        self.user = uuid.uuid4()

    async def sign_in(self, user=None):
        return await rt.issue(self.store, user or self.user, POLICY, T0)

    async def test_only_the_hash_is_stored(self):
        raw = await self.sign_in()
        (row,) = self.store.rows
        self.assertEqual(row.token_hash, hashlib.sha256(raw.encode()).hexdigest())
        self.assertNotIn(raw, repr(vars(row)))
        self.assertGreaterEqual(len(raw), 40)  # 256 bits, url-safe

    async def test_rotation_issues_a_new_token_and_marks_the_old_one_used(self):
        first = await self.sign_in()
        res = await rt.rotate(self.store, first, POLICY, after(minutes=31))
        self.assertTrue(res.ok)
        self.assertEqual(res.user_id, self.user)
        self.assertNotEqual(res.raw_token, first)
        old, new = self.store.rows
        self.assertEqual(old.used_at, after(minutes=31))
        self.assertEqual(old.replaced_by_id, new.id)
        self.assertEqual(new.family_id, old.family_id)
        # the idle window slides, the absolute cap does not
        self.assertEqual(new.expires_at, after(minutes=31) + timedelta(days=30))
        self.assertEqual(new.family_expires_at, old.family_expires_at)

    async def test_the_new_token_works_and_a_chain_can_continue(self):
        token = await self.sign_in()
        for i in range(1, 6):
            res = await rt.rotate(self.store, token, POLICY, after(hours=i))
            self.assertTrue(res.ok, i)
            token = res.raw_token

    async def test_unknown_token(self):
        res = await rt.rotate(self.store, "x" * 43, POLICY, T0)
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "unknown")
        self.assertFalse(res.changed)

    async def test_idle_window(self):
        token = await self.sign_in()
        res = await rt.rotate(self.store, token, POLICY, after(days=29, hours=23))
        self.assertTrue(res.ok)
        token2 = await self.sign_in()
        res = await rt.rotate(self.store, token2, POLICY, after(days=30, seconds=1))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "expired")

    async def test_idle_window_slides_but_the_absolute_cap_does_not(self):
        token = await self.sign_in()
        day = 0
        while day < 85:  # active every 20 days: never idle for 30
            day += 20 if day + 20 < 90 else 5
            res = await rt.rotate(self.store, token, POLICY, after(days=day))
            self.assertTrue(res.ok, day)
            token = res.raw_token
        # the last token cannot outlive the family, even though its own idle window would
        self.assertEqual(self.store.rows[-1].expires_at, T0 + timedelta(days=90))
        res = await rt.rotate(self.store, token, POLICY, after(days=90, seconds=1))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "expired")

    async def test_reuse_after_the_leeway_revokes_the_family(self):
        first = await self.sign_in()
        second = (await rt.rotate(self.store, first, POLICY, after(minutes=1))).raw_token
        res = await rt.rotate(self.store, first, POLICY, after(minutes=1, seconds=11))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "reuse")
        self.assertTrue(res.changed)  # the caller must commit this before it answers 401
        # the thief's successor is dead too, and so is everything else in the family
        res = await rt.rotate(self.store, second, POLICY, after(minutes=2))
        self.assertFalse(res.ok)
        self.assertEqual(res.reason, "revoked")
        self.assertTrue(all(r.revoked_at is not None for r in self.store.rows))

    async def test_reuse_when_the_successor_was_already_used(self):
        first = await self.sign_in()
        second = (await rt.rotate(self.store, first, POLICY, after(seconds=1))).raw_token
        self.assertTrue((await rt.rotate(self.store, second, POLICY, after(seconds=2))).ok)
        # inside the leeway, but the owner has clearly moved on: this replay is someone else
        res = await rt.rotate(self.store, first, POLICY, after(seconds=3))
        self.assertEqual(res.reason, "reuse")
        self.assertTrue(all(r.revoked_at is not None for r in self.store.rows))

    async def test_lost_response_is_forgiven_once_inside_the_leeway(self):
        first = await self.sign_in()
        lost = (await rt.rotate(self.store, first, POLICY, after(minutes=1))).raw_token  # response never arrived
        with self.assertLogs("app.services.refresh_tokens", level="WARNING") as logs:
            res = await rt.rotate(self.store, first, POLICY, after(minutes=1, seconds=5))
        self.assertTrue(res.ok)
        self.assertIn("forgiven", logs.output[0])
        self.assertNotEqual(res.raw_token, lost)
        # only one live successor remains: the lost one is superseded
        lost_row = next(r for r in self.store.rows if r.token_hash == rt.hash_token(lost))
        self.assertEqual(lost_row.revoked_reason, rt.SUPERSEDED)
        # the new token carries on normally
        self.assertTrue((await rt.rotate(self.store, res.raw_token, POLICY, after(minutes=2))).ok)

    async def test_the_superseded_token_is_treated_as_stolen_if_it_ever_shows_up(self):
        first = await self.sign_in()
        lost = (await rt.rotate(self.store, first, POLICY, after(minutes=1))).raw_token
        kept = (await rt.rotate(self.store, first, POLICY, after(minutes=1, seconds=2))).raw_token
        res = await rt.rotate(self.store, lost, POLICY, after(minutes=1, seconds=3))
        self.assertEqual(res.reason, "reuse")
        res = await rt.rotate(self.store, kept, POLICY, after(minutes=1, seconds=4))
        self.assertEqual(res.reason, "revoked")

    async def test_the_leeway_does_not_slide(self):
        first = await self.sign_in()
        await rt.rotate(self.store, first, POLICY, after(seconds=0))
        self.assertTrue((await rt.rotate(self.store, first, POLICY, after(seconds=6))).ok)
        res = await rt.rotate(self.store, first, POLICY, after(seconds=12))  # 12s after the FIRST use
        self.assertEqual(res.reason, "reuse")

    async def test_leeway_zero_means_every_replay_is_reuse(self):
        strict = rt.Policy(idle=POLICY.idle, absolute=POLICY.absolute, leeway=timedelta(0))
        first = await rt.issue(self.store, self.user, strict, T0)
        await rt.rotate(self.store, first, strict, T0)
        res = await rt.rotate(self.store, first, strict, T0)
        self.assertEqual(res.reason, "reuse")

    async def test_expired_tokens_are_not_reuse(self):
        first = await self.sign_in()
        await rt.rotate(self.store, first, POLICY, after(seconds=1))
        res = await rt.rotate(self.store, first, POLICY, after(days=31))
        self.assertEqual(res.reason, "expired")
        self.assertFalse(res.changed)

    async def test_logout_revokes_the_whole_family_and_ignores_unknown_tokens(self):
        first = await self.sign_in()
        second = (await rt.rotate(self.store, first, POLICY, after(minutes=1))).raw_token
        self.assertTrue(await rt.revoke_by_raw(self.store, second, after(minutes=2)))
        res = await rt.rotate(self.store, second, POLICY, after(minutes=3))
        self.assertEqual(res.reason, "revoked")
        self.assertFalse(await rt.revoke_by_raw(self.store, "nope" * 10, after(minutes=3)))

    async def test_revoke_all_covers_every_session_of_the_user_only(self):
        a1, a2 = await self.sign_in(), await self.sign_in()  # two devices
        other = await self.sign_in(uuid.uuid4())
        self.assertEqual(await rt.revoke_all(self.store, self.user, "password_reset", after(minutes=1)), 2)
        for token in (a1, a2):
            self.assertEqual((await rt.rotate(self.store, token, POLICY, after(minutes=2))).reason, "revoked")
        self.assertTrue((await rt.rotate(self.store, other, POLICY, after(minutes=2))).ok)

    async def test_signing_in_again_removes_dead_rows(self):
        await self.sign_in()
        await rt.issue(self.store, self.user, POLICY, after(days=100))
        self.assertEqual(len(self.store.rows), 1)

    async def test_rotation_removes_expired_rows_of_the_family(self):
        token = await self.sign_in()
        token = (await rt.rotate(self.store, token, POLICY, after(days=20))).raw_token
        token = (await rt.rotate(self.store, token, POLICY, after(days=45))).raw_token
        # the first row (expired on day 30) is gone; a replay of it is now just unknown
        self.assertEqual(len(self.store.rows), 2)

    async def test_raw_tokens_are_never_logged(self):
        first = await self.sign_in()
        second = (await rt.rotate(self.store, first, POLICY, after(seconds=1))).raw_token
        with self.assertLogs("app.services.refresh_tokens", level="WARNING") as logs:
            third = (await rt.rotate(self.store, first, POLICY, after(seconds=2))).raw_token  # leeway
            await rt.rotate(self.store, first, POLICY, after(seconds=30))  # reuse
        text = "\n".join(logs.output)
        self.assertEqual(len(logs.output), 2)
        for raw in (first, second, third):
            self.assertNotIn(raw, text)
            self.assertNotIn(rt.hash_token(raw), text)

    def test_policy_reads_the_settings(self):
        p = rt.policy_from_settings(settings)
        self.assertEqual((p.idle, p.absolute, p.leeway), (timedelta(days=30), timedelta(days=90), timedelta(seconds=10)))


class TestAccessTokens(unittest.TestCase):
    def test_default_lifetime_is_the_legacy_24_hours(self):
        payload = decode_access_token(create_access_token(uuid.uuid4(), "customer"))
        self.assertEqual(payload["exp"] - payload["iat"], 24 * 3600)

    def test_short_lifetime_for_clients_with_refresh(self):
        payload = decode_access_token(create_access_token(uuid.uuid4(), "customer", minutes=30))
        self.assertEqual(payload["exp"] - payload["iat"], 30 * 60)
        self.assertEqual(settings.access_token_minutes, 30)

    def test_issued_before(self):
        reset = datetime(2026, 10, 7, 12, 0, 0, 500000, tzinfo=timezone.utc)
        base = int(reset.timestamp())
        self.assertFalse(issued_before({"iat": base - 1000}, None))  # never reset
        self.assertTrue(issued_before({"iat": base - 1}, reset))     # older token
        self.assertFalse(issued_before({"iat": base}, reset))        # same second as the reset: allowed
        self.assertFalse(issued_before({"iat": base + 60}, reset))
        self.assertTrue(issued_before({}, reset))                    # no iat at all


if __name__ == "__main__":
    unittest.main()
