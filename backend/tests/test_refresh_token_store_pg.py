"""
Refresh tokens against a REAL PostgreSQL: the SQL store, row locking under concurrency, the delete cascade,
and the whole HTTP flow (sign-in, refresh, rotation, reuse, logout, /me, password reset, account deletion)
through the real routers.

Skipped unless LAMBA_TEST_DATABASE_URL is set, so the normal test run needs no database. Point it at a
THROWAWAY database that has migrations up to 0003 (never the production one; the tests create and delete
users there):

    docker run -d --name lamba-test-pg -e POSTGRES_PASSWORD=throwaway -e POSTGRES_DB=t -p 127.0.0.1:55432:5432 postgis/postgis:16-3.4
    DATABASE_URL=postgresql+asyncpg://postgres:throwaway@127.0.0.1:55432/t alembic upgrade head
    LAMBA_TEST_DATABASE_URL=postgresql+asyncpg://postgres:throwaway@127.0.0.1:55432/t python -m unittest tests.test_refresh_token_store_pg
    docker rm -f lamba-test-pg

(The full alembic chain needs the PostGIS + pgvector image from backend/Dockerfile.postgres. A database that only has
the `users` table plus migration 0003's changes is enough for these tests.)
"""

import asyncio
import os
import sys
import unittest
import uuid
from unittest import mock
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB_URL = os.environ.get("LAMBA_TEST_DATABASE_URL")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql+asyncpg://unused:unused@localhost/unused")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import refresh_tokens as rt
from app.services.auth import hash_password
from app.services.refresh_token_store import SqlRefreshStore

POLICY = rt.Policy(idle=timedelta(days=30), absolute=timedelta(days=90), leeway=timedelta(seconds=10))
STRICT = rt.Policy(idle=POLICY.idle, absolute=POLICY.absolute, leeway=timedelta(0))


@unittest.skipUnless(TEST_DB_URL, "LAMBA_TEST_DATABASE_URL not set")
class TestRefreshTokensPostgres(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(TEST_DB_URL)
        self.sessions = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.users = []

    async def asyncTearDown(self):
        async with self.sessions() as db:
            for uid in self.users:
                await db.execute(text("DELETE FROM users WHERE id = :i"), {"i": uid})
            await db.commit()
        await self.engine.dispose()

    async def make_user(self, **kw):
        user = User(email="pg-%s@example.com" % uuid.uuid4().hex[:10], password_hash=hash_password("Unit-Test-Pass-91"),
                    user_type="customer", verified=True, **kw)
        async with self.sessions() as db:
            db.add(user)
            await db.commit()
        self.users.append(user.id)
        return user

    async def test_sign_in_rotate_and_reuse_with_committed_revocation(self):
        user = await self.make_user()
        async with self.sessions() as db:
            first = await rt.issue(SqlRefreshStore(db), user.id, POLICY)
            await db.commit()
        async with self.sessions() as db:
            res = await rt.rotate(SqlRefreshStore(db), first, POLICY)
            await db.commit()
        self.assertTrue(res.ok)
        # replay after the leeway: simulate it by using the strict policy
        async with self.sessions() as db:
            bad = await rt.rotate(SqlRefreshStore(db), first, STRICT)
            self.assertEqual((bad.ok, bad.reason, bad.changed), (False, "reuse", True))
            await db.commit()  # what the endpoint does before it raises 401
        async with self.sessions() as db:
            rows = (await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))).scalars().all()
            self.assertTrue(rows and all(r.revoked_at is not None for r in rows))
            self.assertEqual((await rt.rotate(SqlRefreshStore(db), res.raw_token, STRICT)).reason, "revoked")
            for r in rows:  # only hashes in the database
                self.assertEqual(len(r.token_hash), 64)
                self.assertNotIn(r.token_hash, (first, res.raw_token))

    async def test_concurrent_refreshes_of_one_token_cannot_both_succeed(self):
        user = await self.make_user()
        async with self.sessions() as db:
            token = await rt.issue(SqlRefreshStore(db), user.id, STRICT)
            await db.commit()

        async def attempt():
            async with self.sessions() as db:
                res = await rt.rotate(SqlRefreshStore(db), token, STRICT)
                await asyncio.sleep(0.2)  # hold the row lock for a while, as a slow request would
                await db.commit()
                return res

        results = await asyncio.gather(*[attempt() for _ in range(4)])
        self.assertEqual(sum(r.ok for r in results), 1)
        # the first loser detects the reuse and revokes the family; the ones after it find it revoked
        self.assertEqual({r.reason for r in results if not r.ok}, {"reuse", "revoked"})

    async def test_deleting_the_user_deletes_the_tokens(self):
        user = await self.make_user()
        async with self.sessions() as db:
            await rt.issue(SqlRefreshStore(db), user.id, POLICY)
            await rt.issue(SqlRefreshStore(db), user.id, POLICY)
            await db.commit()
            await db.execute(text("DELETE FROM users WHERE id = :i"), {"i": user.id})
            await db.commit()
            left = (await db.execute(text("SELECT count(*) FROM refresh_tokens WHERE user_id = :i"), {"i": user.id})).scalar()
        self.assertEqual(left, 0)

    async def test_revoke_user_and_prune(self):
        user, other = await self.make_user(), await self.make_user()
        long_ago = datetime.now(timezone.utc) - timedelta(days=200)
        async with self.sessions() as db:
            store = SqlRefreshStore(db)
            await rt.issue(store, user.id, POLICY, long_ago)   # dead rows from old sign-ins...
            await rt.issue(store, other.id, POLICY, long_ago)
            mine = [await rt.issue(store, user.id, POLICY) for _ in range(2)]  # ...removed at the next sign-in
            theirs = await rt.issue(store, other.id, POLICY)
            await db.commit()
            count = lambda uid: db.execute(text("SELECT count(*) FROM refresh_tokens WHERE user_id = :i"), {"i": uid})
            self.assertEqual(((await count(user.id)).scalar(), (await count(other.id)).scalar()), (2, 1))
            self.assertEqual(await rt.revoke_all(store, user.id, "password_reset"), 2)
            await db.commit()
        async with self.sessions() as db:
            for raw in mine:
                self.assertEqual((await rt.rotate(SqlRefreshStore(db), raw, POLICY)).reason, "revoked")
            self.assertTrue((await rt.rotate(SqlRefreshStore(db), theirs, POLICY)).ok)

    async def test_tokens_valid_after_round_trip(self):
        user = await self.make_user()
        now = datetime.now(timezone.utc)
        async with self.sessions() as db:
            u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
            self.assertIsNone(u.tokens_valid_after)
            u.tokens_valid_after = now
            await db.commit()
        async with self.sessions() as db:
            u = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
            self.assertEqual(u.tokens_valid_after, now)


@unittest.skipUnless(TEST_DB_URL, "LAMBA_TEST_DATABASE_URL not set")
class TestAuthFlowPostgres(unittest.IsolatedAsyncioTestCase):
    """The real routers on the real database (Redis is optional: without it the sign-in throttle fails open)."""

    async def asyncSetUp(self):
        import httpx
        from fastapi import FastAPI
        from slowapi.errors import RateLimitExceeded
        from app.api import account_v1, auth_v1
        from app.rate_limit import limiter, rate_limit_exceeded_handler
        from app.services import signin_throttle

        self.engine = create_async_engine(TEST_DB_URL)
        self.sessions = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

        async def get_db():
            async with self.sessions() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
        app.include_router(auth_v1.router)
        app.include_router(account_v1.router)
        app.dependency_overrides[auth_v1.get_db] = get_db
        app.dependency_overrides[account_v1.get_db] = get_db
        from app.api.auth import get_db as auth_get_db
        app.dependency_overrides[auth_get_db] = get_db
        # Isolation: the sign-in throttle would create the process-wide Redis client inside this test's
        # event loop, which other tests would then inherit after it is closed. (Throttling has its own tests.)
        for name, value in (("seconds_locked", 0), ("record_failure", None), ("reset_failures", None)):
            patcher = mock.patch.object(signin_throttle, name, mock.AsyncMock(return_value=value))
            patcher.start()
            self.addCleanup(patcher.stop)
        was_enabled = limiter.enabled
        limiter.enabled = False
        self.addCleanup(setattr, limiter, "enabled", was_enabled)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.email = "flow-%s@example.com" % uuid.uuid4().hex[:10]
        self.password = "Correct-Horse-91-Battery"
        async with self.sessions() as db:
            self.user = User(email=self.email, password_hash=hash_password(self.password), user_type="customer", verified=True)
            db.add(self.user)
            await db.commit()

    async def asyncTearDown(self):
        await self.client.aclose()
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM users WHERE id = :i"), {"i": self.user.id})
            await db.commit()
        await self.engine.dispose()

    async def sign_in(self, refresh=True):
        body = {"email_or_phone": self.email, "password": self.password}
        if refresh:
            body["client_supports_refresh"] = True
        r = await self.client.post("/api/v1/auth/signin", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def bearer(self, token):
        return {"Authorization": "Bearer " + token}

    async def test_old_clients_get_the_24_hour_token_and_no_refresh_token(self):
        data = await self.sign_in(refresh=False)
        self.assertIsNone(data["refresh_token"])
        from app.services.auth import decode_access_token
        p = decode_access_token(data["access_token"])
        self.assertEqual(p["exp"] - p["iat"], 24 * 3600)
        self.assertEqual((await self.client.get("/api/v1/auth/me", headers=self.bearer(data["access_token"]))).status_code, 200)

    async def test_new_clients_get_30_minutes_and_a_refresh_token(self):
        data = await self.sign_in()
        from app.services.auth import decode_access_token
        p = decode_access_token(data["access_token"])
        self.assertEqual(p["exp"] - p["iat"], 30 * 60)
        self.assertEqual(data["expires_in"], 1800)
        self.assertTrue(data["refresh_token"])
        me = await self.client.get("/api/v1/auth/me", headers=self.bearer(data["access_token"]))
        self.assertEqual(me.json()["email"], self.email)

    async def test_refresh_rotates_and_reuse_ends_the_session(self):
        data = await self.sign_in()
        r1 = await self.client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
        self.assertEqual(r1.status_code, 200, r1.text)
        new = r1.json()
        self.assertNotEqual(new["refresh_token"], data["refresh_token"])
        self.assertEqual(new["user"]["email"], self.email)
        # leeway 10s by default: age the first use, then replay it
        async with self.sessions() as db:
            await db.execute(text("UPDATE refresh_tokens SET used_at = used_at - interval '1 minute' WHERE user_id = :i AND used_at IS NOT NULL"), {"i": self.user.id})
            await db.commit()
        r2 = await self.client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
        self.assertEqual(r2.status_code, 401)
        self.assertIn("\n", r2.json()["detail"])  # bilingual
        # the revocation was committed even though the request failed: the thief's successor is dead too
        r3 = await self.client.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]})
        self.assertEqual(r3.status_code, 401)

    async def test_logout_revokes_and_is_idempotent(self):
        data = await self.sign_in()
        for _ in range(2):
            r = await self.client.post("/api/v1/auth/logout", json={"refresh_token": data["refresh_token"]})
            self.assertEqual(r.status_code, 204)
        r = await self.client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
        self.assertEqual(r.status_code, 401)
        r = await self.client.post("/api/v1/auth/logout", json={"refresh_token": "z" * 43})
        self.assertEqual(r.status_code, 204)

    async def test_password_reset_ends_every_session_including_old_access_tokens(self):
        keep = await self.sign_in()
        legacy = await self.sign_in(refresh=False)
        await asyncio.sleep(1.1)  # tokens are timestamped in whole seconds
        async with self.sessions() as db:
            u = (await db.execute(select(User).where(User.id == self.user.id))).scalar_one()
            u.verification_code, u.verification_code_created_at, u.verification_attempts = "123456", datetime.now(timezone.utc), 0
            await db.commit()
        r = await self.client.post("/api/v1/auth/reset-password",
                                   json={"email": self.email, "code": "123456", "new_password": "Brand-New-Pass-7734"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((await self.client.post("/api/v1/auth/refresh", json={"refresh_token": keep["refresh_token"]})).status_code, 401)
        for tok in (keep["access_token"], legacy["access_token"]):
            self.assertEqual((await self.client.get("/api/v1/auth/me", headers=self.bearer(tok))).status_code, 401)
        # signing in with the new password works again and gives a working session
        self.password = "Brand-New-Pass-7734"
        again = await self.sign_in()
        self.assertEqual((await self.client.get("/api/v1/auth/me", headers=self.bearer(again["access_token"]))).status_code, 200)

    async def test_account_deletion_ends_the_session_and_removes_tokens(self):
        data = await self.sign_in()
        r = await self.client.delete("/api/v1/account", headers=self.bearer(data["access_token"]))
        self.assertEqual(r.status_code, 204, r.text)
        self.assertEqual((await self.client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})).status_code, 401)
        self.assertEqual((await self.client.get("/api/v1/auth/me", headers=self.bearer(data["access_token"]))).status_code, 401)
        async with self.sessions() as db:
            left = (await db.execute(text("SELECT count(*) FROM refresh_tokens WHERE user_id = :i"), {"i": self.user.id})).scalar()
        self.assertEqual(left, 0)


if __name__ == "__main__":
    unittest.main()
