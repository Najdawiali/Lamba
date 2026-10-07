"""
End-to-end test app. It is started by e2e_run.py (see README.md in this folder), not by hand.

It runs the REAL backend/app/api/auth_v1.py router together with the real app/api/auth.py (get_current_user),
app/rate_limit.py, app/services/signin_throttle.py, cache.py (get_redis), password_policy.py,
whatsapp_service.py (normalize_jo_mobile), auth.py (real PyJWT access tokens), refresh_tokens.py (the rotation
rules) and schemas/auth_v1.py, on the real FastAPI, slowapi, redis-py and PyJWT. Stand-ins exist only for what
needs other packages: SQLAlchemy (a tiny fake database, with an in-memory refresh token store), bcrypt (fake
hashing), httpx, pydantic-settings and email-validator. If auth_v1.py gains a new third-party import, add a
stand-in here.

Test-only hooks (never part of the real app): /__warp moves the clock forward for the refresh tokens (like
MiniRedis.warp does for Redis), /__delete_user deletes an account the way the database does (tokens go with it),
/__mint_token makes an access token of a given age.

Needs the environment variable E2E_REDIS_PORT: the port of the Redis server the app talks to.
"""

import importlib.metadata
import os
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

if "E2E_REDIS_PORT" not in os.environ:
    raise SystemExit("e2e_app.py is started by e2e_run.py: see README.md in this folder")

BACKEND = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(BACKEND))


def stub(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------- tiny fake ORM / DB (replaces sqlalchemy)
class Column:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    __hash__ = object.__hash__


class User:
    id = Column("id")
    email = Column("email")
    phone_number = Column("phone_number")


class Select:
    def __init__(self, model):
        self.conds = []

    def where(self, *conds):
        self.conds.extend(conds)
        return self


def or_(*conds):
    return ("or", conds)


def _flatten(cond):
    if cond[0] == "or":
        for sub in cond[1]:
            yield from _flatten(sub)
    else:
        yield cond


class FakeDB:
    def __init__(self):
        self.users, self.queries = [], 0
        self.refresh_rows = []  # the refresh_tokens table
        self.commits = 0
        self.last_error_committed = None  # did the last FAILED request commit before it answered?

    async def execute(self, stmt):
        self.queries += 1
        found = None
        for cond in stmt.conds:
            for _, col, val in _flatten(cond):
                for u in self.users:
                    if found is None and getattr(u, col) == val:  # exact match, like the real column comparison
                        found = u
        return SimpleNamespace(scalar_one_or_none=lambda: found)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


FAKE_DB = FakeDB()
SENT = []


async def get_db():
    """Like app/database.py get_db: commit at the end, roll back (here: only note it) on an exception.
    The real one rolls back, so a state change before an HTTPException survives only if it was committed first."""
    start = FAKE_DB.commits
    try:
        yield FAKE_DB
        await FAKE_DB.commit()
    except Exception:
        FAKE_DB.last_error_committed = FAKE_DB.commits > start
        raise


async def send_verification_email(email, code):
    SENT.append((email, code))


stub("sqlalchemy", select=Select, or_=or_)
stub("sqlalchemy.ext")
stub("sqlalchemy.ext.asyncio", AsyncSession=object)
stub("app.database", get_db=get_db)
stub("app.models")
stub("app.models.user", User=User)
stub("httpx")
stub("app.config", settings=SimpleNamespace(
    phone_signup_enabled=False, redis_host="127.0.0.1", redis_port=int(os.environ["E2E_REDIS_PORT"]), redis_password="",
    jwt_secret="e2e-secret-e2e-secret-e2e-secret-e2e-secret", jwt_algorithm="HS256", jwt_expiration_minutes=1440,
    access_token_minutes=30, refresh_idle_days=30, refresh_absolute_days=90, refresh_reuse_leeway_seconds=10))
stub("app.services.email_service", send_verification_email=send_verification_email)
# bcrypt is slow and not what is under test: a fake with the same four calls app/services/auth.py makes
stub("bcrypt", gensalt=lambda: b"", hashpw=lambda pw, salt: b"hash:" + pw, checkpw=lambda pw, hashed: hashed == b"hash:" + pw)

# the refresh token store: the rules (app/services/refresh_tokens.py) are real, only the storage is in memory
from tests.refresh_store_fake import InMemoryRefreshStore  # noqa: E402


class InMemoryStoreOnFakeDB(InMemoryRefreshStore):
    def __init__(self, db):
        super().__init__(db.refresh_rows)


stub("app.services.refresh_token_store", SqlRefreshStore=InMemoryStoreOnFakeDB)

# the REAL schemas module, without running app/schemas/__init__.py and without email-validator
schemas_pkg = stub("app.schemas")
schemas_pkg.__path__ = [str(BACKEND / "app" / "schemas")]

# ---------------------------------------------------------------- the REAL code
from fastapi import FastAPI  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
import pydantic  # noqa: E402
pydantic.EmailStr = str  # AFTER the fastapi import, which restores the real class

import app.api.auth_v1 as auth_v1  # noqa: E402  (real file)
import app.rate_limit as rate_limit  # noqa: E402  (real file)
from app.rate_limit import limiter, rate_limit_exceeded_handler  # noqa: E402


def make_user(email, password, verified=True):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(id=uuid.uuid4(), email=email, phone_number=None, full_name=None, user_type="customer",
                           verified=verified, created_at=now, password_hash="hash:" + password,
                           verification_code="123456", verification_code_created_at=now, verification_attempts=0,
                           tokens_valid_after=None)


for name in ("ali", "bob", "carol", "dave", "gina", "hana", "ivan", "judy", "kim", "lena", "mona", "nour", "omar", "pia", "quin"):
    FAKE_DB.users.append(make_user("%s@example.com" % name, "right-pass-" + name))
FAKE_DB.users.append(make_user("erin@example.com", "right-pass-erin", verified=False))

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # same wiring as app/main.py
app.include_router(auth_v1.router)
app.dependency_overrides[auth_v1.get_db] = get_db


@app.post("/__warp")
async def warp(seconds: float):
    """Move the clock forward for every stored refresh token (all their timestamps go back by `seconds`)."""
    from datetime import timedelta
    for row in FAKE_DB.refresh_rows:
        for field in ("created_at", "expires_at", "family_expires_at", "used_at", "revoked_at"):
            if getattr(row, field) is not None:
                setattr(row, field, getattr(row, field) - timedelta(seconds=seconds))
    return {"rows": len(FAKE_DB.refresh_rows)}


@app.post("/__delete_user")
async def delete_user(email: str):
    """What DELETE /api/v1/account does to the database: the user is gone and ON DELETE CASCADE takes the tokens."""
    user = next(u for u in FAKE_DB.users if u.email == email)
    FAKE_DB.users.remove(user)
    FAKE_DB.refresh_rows[:] = [r for r in FAKE_DB.refresh_rows if r.user_id != user.id]
    return {"rows": len(FAKE_DB.refresh_rows)}


@app.post("/__mint_token")
async def mint_token(email: str, age_seconds: int = 0, minutes: int = 30):
    """An access token for `email` as if it had been issued `age_seconds` ago (to test expired / pre-reset tokens)."""
    import jwt as pyjwt
    from datetime import timedelta
    user = next(u for u in FAKE_DB.users if u.email == email)
    issued = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    settings = sys.modules["app.config"].settings
    return {"access_token": pyjwt.encode(
        {"sub": str(user.id), "role": user.user_type, "iat": issued, "exp": issued + timedelta(minutes=minutes)},
        settings.jwt_secret, algorithm=settings.jwt_algorithm)}


@app.get("/__stats")
async def stats():
    return {
        "queries": FAKE_DB.queries,
        "refresh_rows": len(FAKE_DB.refresh_rows),
        "last_error_committed": FAKE_DB.last_error_committed,
        "session_ended": auth_v1.SESSION_ENDED,
        "auth_v1_file": auth_v1.__file__,
        "rate_limit_file": rate_limit.__file__,
        "rate_limited_message": rate_limit.RATE_LIMITED,
        "signin_locked": auth_v1.SIGNIN_LOCKED,
        "versions": {"python": sys.version.split()[0],
                     **{n: importlib.metadata.version(n) for n in ("fastapi", "starlette", "uvicorn", "slowapi", "limits", "redis")}},
    }
