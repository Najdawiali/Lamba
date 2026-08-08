"""
Shared rate limiter instance for all API routers.

Usage in routers:
    from app.rate_limit import limiter
    from fastapi import Request

    @router.post("/endpoint")
    @limiter.limit("30/minute")
    async def my_endpoint(request: Request, ...):
        ...
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
