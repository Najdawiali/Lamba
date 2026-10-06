"""
Tests for app.services.signin_throttle: pure logic against an in-memory stand-in for Redis
(no network, no server).
"""

import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import signin_throttle as throttle
from app.services.signin_throttle import MAX_FAILURES, WINDOW_SECONDS


class FakeRedis:
    """The few async commands the throttle uses, with Redis' expiry behaviour on a manual clock."""

    def __init__(self):
        self.now = 0
        self.values = {}
        self.expires = {}

    def _alive(self, key):
        expires = self.expires.get(key)
        if expires is not None and expires <= self.now:
            self.values.pop(key, None)
            self.expires.pop(key, None)
        return key in self.values

    async def get(self, key):
        return str(self.values[key]) if self._alive(key) else None

    async def incr(self, key):
        self._alive(key)
        self.values[key] = int(self.values.get(key, 0)) + 1  # like Redis, INCR keeps an existing expiry
        return self.values[key]

    async def ttl(self, key):
        if not self._alive(key):
            return -2
        expires = self.expires.get(key)
        return -1 if expires is None else expires - self.now

    async def expire(self, key, seconds):
        if not self._alive(key):
            return False
        self.expires[key] = self.now + seconds
        return True

    async def delete(self, key):
        existed = self._alive(key)
        self.values.pop(key, None)
        self.expires.pop(key, None)
        return int(existed)


class BrokenRedis:
    """Every command fails, like an unreachable server."""

    def __getattr__(self, name):
        async def fail(*args, **kwargs):
            raise ConnectionError("redis is down")
        return fail


def fake_normalize(raw):
    """Like whatsapp_service.normalize_jo_mobile: one canonical form per phone number, None if not a phone."""
    digits = re.sub(r"\D", "", raw)
    return "+962" + digits[-9:] if len(digits) >= 9 else None


class TestSigninThrottle(unittest.IsolatedAsyncioTestCase):
    async def fail(self, redis, identifier, times):
        for _ in range(times):
            await throttle.record_failure(identifier, redis=redis)

    def test_policy_is_ten_failures_in_fifteen_minutes(self):
        self.assertEqual(MAX_FAILURES, 10)
        self.assertEqual(WINDOW_SECONDS, 15 * 60)

    async def test_blocks_only_after_max_failures(self):
        r = FakeRedis()
        await self.fail(r, "ali@example.com", MAX_FAILURES - 1)
        self.assertEqual(await throttle.seconds_locked("ali@example.com", redis=r), 0)
        await self.fail(r, "ali@example.com", 1)
        wait = await throttle.seconds_locked("ali@example.com", redis=r)
        self.assertTrue(0 < wait <= WINDOW_SECONDS, wait)

    async def test_window_ends_and_the_counter_disappears(self):
        r = FakeRedis()
        await self.fail(r, "a@x.com", MAX_FAILURES)
        r.now = WINDOW_SECONDS
        self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), 0)
        self.assertEqual(r.values, {})

    async def test_window_starts_at_the_first_failure_and_is_not_extended(self):
        r = FakeRedis()
        await self.fail(r, "a@x.com", 1)                        # t = 0
        r.now = WINDOW_SECONDS - 60
        await self.fail(r, "a@x.com", MAX_FAILURES - 1)         # the 10th failure, 60 s before the end
        self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), 60)
        r.now = WINDOW_SECONDS
        self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), 0)

    async def test_a_correct_password_clears_the_failures(self):
        r = FakeRedis()
        await self.fail(r, "a@x.com", MAX_FAILURES)
        await throttle.reset_failures("a@x.com", redis=r)
        self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), 0)
        self.assertEqual(r.values, {})

    async def test_accounts_are_counted_separately(self):
        r = FakeRedis()
        await self.fail(r, "a@x.com", MAX_FAILURES)
        self.assertGreater(await throttle.seconds_locked("a@x.com", redis=r), 0)
        self.assertEqual(await throttle.seconds_locked("b@x.com", redis=r), 0)

    async def test_the_key_is_a_hash_not_the_identifier(self):
        r = FakeRedis()
        await self.fail(r, "ali@example.com", 1)
        (key,) = r.values
        self.assertTrue(key.startswith("signin_fail:"))
        self.assertNotIn("ali", key)
        self.assertEqual(len(key), len("signin_fail:") + 64)

    def test_one_account_gives_one_identifier(self):
        canon = lambda raw: throttle.canonical_identifier(raw, fake_normalize)
        self.assertEqual(canon(" Ali@Example.COM "), canon("ali@example.com"))
        self.assertEqual(canon("0791234567"), canon("+962 79 123 4567"))
        self.assertEqual(canon("someone"), "someone")           # neither an email nor a phone: used as typed
        self.assertNotEqual(canon("ali@example.com"), canon("bob@example.com"))

    async def test_uses_the_shared_client_when_none_is_passed(self):
        r = FakeRedis()

        async def shared_client():
            return r

        with mock.patch.object(throttle, "_client", shared_client):
            await self.fail(None, "a@x.com", MAX_FAILURES)      # redis=None -> the shared client
            self.assertGreater(await throttle.seconds_locked("a@x.com"), 0)
            await throttle.reset_failures("a@x.com")
            self.assertEqual(await throttle.seconds_locked("a@x.com"), 0)

    async def test_fails_open_when_redis_is_down(self):
        r = BrokenRedis()
        with self.assertLogs("app.services.signin_throttle", level="WARNING"):
            self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), 0)
            await throttle.record_failure("a@x.com", redis=r)   # must not raise
            await throttle.reset_failures("a@x.com", redis=r)

    async def test_a_counter_without_an_expiry_cannot_block_for_good(self):
        r = FakeRedis()
        key = throttle._key("a@x.com")
        r.values[key] = MAX_FAILURES                            # e.g. left behind by a crash between INCR and EXPIRE
        self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), WINDOW_SECONDS)
        self.assertEqual(r.expires[key], WINDOW_SECONDS)        # it has an expiry now
        r.now = WINDOW_SECONDS
        self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), 0)

    async def test_counting_a_failure_repairs_a_missing_expiry(self):
        r = FakeRedis()
        key = throttle._key("a@x.com")
        r.values[key] = 3
        await throttle.record_failure("a@x.com", redis=r)
        self.assertEqual(r.values[key], 4)
        self.assertEqual(r.expires[key], WINDOW_SECONDS)

    async def test_a_counter_that_expires_between_the_two_reads_does_not_block(self):
        class Racy(FakeRedis):
            async def ttl(self, key):
                return -2                                       # gone by the time we ask

        r = Racy()
        r.values[throttle._key("a@x.com")] = MAX_FAILURES
        self.assertEqual(await throttle.seconds_locked("a@x.com", redis=r), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
