"""
Shared rate limiter instance for all API routers.

Usage in routers:
    from app.rate_limit import limiter
    from fastapi import Request

    @router.post("/endpoint")
    @limiter.limit("30/minute")
    async def my_endpoint(request: Request, ...):
        ...

Limits are per client IP, so uvicorn has to see the real client address behind Caddy: see
FORWARDED_ALLOW_IPS in docker-compose.yml.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# The API's other user-facing errors are {"detail": "Arabic\nEnglish"}, which the app shows in its
# own language. slowapi's default 429 body is {"error": "Rate limit exceeded: ..."}, which the app
# cannot show.
RATE_LIMITED = (
    "طلبات كثيرة جداً. انتظر قليلاً ثم حاول مرة أخرى.\n"
    "Too many requests. Please wait a moment and try again."
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """HTTP 429 with a bilingual `detail`. Retry-After is the length of the limit's window, an upper bound."""
    headers = {}
    try:
        headers["Retry-After"] = str(exc.limit.limit.get_expiry())
    except Exception:  # slowapi/limits internals changed: the message alone is still useful
        pass
    return JSONResponse({"detail": RATE_LIMITED}, status_code=429, headers=headers)
