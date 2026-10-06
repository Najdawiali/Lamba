"""
End-to-end test app. It is started by e2e_run.py (see README.md in this folder), not by hand.

It runs the REAL backend/app/api/auth_v1.py router together with the real app/rate_limit.py,
app/services/signin_throttle.py, app/services/cache.py (get_redis), password_policy.py, whatsapp_service.py
(normalize_jo_mobile) and schemas/auth_v1.py, on the real FastAPI, slowapi and redis-py. Stand-ins exist only
for what needs other packages: SQLAlchemy (a tiny fake database), bcrypt and PyJWT (fake hashing and tokens),
httpx, pydantic-settings and email-validator. If auth_v1.py gains a new third-party import, add a stand-in here.

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
        pass


FAKE_DB = FakeDB()
SENT = []


async def get_db():
    yield FAKE_DB


async def send_verification_email(email, code):
    SENT.append((email, code))


stub("sqlalchemy", select=Select, or_=or_)
stub("sqlalchemy.ext")
stub("sqlalchemy.ext.asyncio", AsyncSession=object)
stub("app.database", get_db=get_db)
stub("app.models")
stub("app.models.user", User=User)
stub("httpx")
stub("app.config", settings=SimpleNamespace(phone_signup_enabled=False, redis_host="127.0.0.1",
                                            redis_port=int(os.environ["E2E_REDIS_PORT"]), redis_password=""))
stub("app.services.email_service", send_verification_email=send_verification_email)
stub("app.services.auth", hash_password=lambda p: "hash:" + p,
     verify_password=lambda plain, hashed: hashed == "hash:" + plain,
     create_access_token=lambda uid, utype: "token-%s" % uid)

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
                           verification_code="123456", verification_code_created_at=now, verification_attempts=0)


for name in ("ali", "bob", "carol", "dave", "gina", "hana", "ivan", "judy"):
    FAKE_DB.users.append(make_user("%s@example.com" % name, "right-pass-" + name))
FAKE_DB.users.append(make_user("erin@example.com", "right-pass-erin", verified=False))

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # same wiring as app/main.py
app.include_router(auth_v1.router)
app.dependency_overrides[auth_v1.get_db] = lambda: FAKE_DB


@app.get("/__stats")
async def stats():
    return {
        "queries": FAKE_DB.queries,
        "auth_v1_file": auth_v1.__file__,
        "rate_limit_file": rate_limit.__file__,
        "rate_limited_message": rate_limit.RATE_LIMITED,
        "signin_locked": auth_v1.SIGNIN_LOCKED,
        "versions": {"python": sys.version.split()[0],
                     **{n: importlib.metadata.version(n) for n in ("fastapi", "starlette", "uvicorn", "slowapi", "limits", "redis")}},
    }
