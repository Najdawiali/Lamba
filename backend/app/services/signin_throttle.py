"""
Per-account throttle for failed sign-ins.

NIST SP 800-63B-4 (3.2.2) limits failed authentication attempts on the account itself. slowapi's
per-IP limits cannot do that alone: a guesser can spread attempts over many IPs.

Fixed window: MAX_FAILURES failed sign-ins for one account within WINDOW_SECONDS block further
attempts for that account until the window ends. The window starts at the first failure; later
failures do not extend it. The counter lives in Redis as "signin_fail:<sha256 of the account
identifier>" (the identifier itself is never stored). Failures are counted for unknown accounts
too, so being blocked never reveals whether an account exists. A correct password, or a password
reset, clears the counter.

If Redis is unreachable the throttle fails open and logs a warning: the per-IP limiter still
applies, and signing in must keep working. Every function here is async and never raises.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60


def canonical_identifier(identifier: str, normalize_phone: Callable[[str], str | None]) -> str:
    """The same account always gives the same string: a lower-cased email, or the phone number
    in canonical form ('0791234567' and '+962 79 123 4567' are one account)."""
    identifier = identifier.strip()
    if "@" in identifier:
        return identifier.lower()
    return normalize_phone(identifier) or identifier


def _key(identifier: str) -> str:
    return "signin_fail:" + hashlib.sha256(identifier.encode("utf-8")).hexdigest()


async def _client() -> Any:
    from app.services.cache import get_redis  # imported here so this module loads without redis installed
    return await get_redis()


def _log_unavailable(error: Exception) -> None:
    logger.warning("Sign-in throttle unavailable (%s: %s); not limiting this attempt",
                   type(error).__name__, error)


async def seconds_locked(identifier: str, *, redis: Any = None) -> int:
    """Seconds the account stays blocked, or 0 when signing in may go ahead."""
    try:
        r = redis if redis is not None else await _client()
        key = _key(identifier)
        count = await r.get(key)
        if count is None or int(count) < MAX_FAILURES:
            return 0
        ttl = await r.ttl(key)
        if ttl == -2:  # expired between the two calls
            return 0
        if ttl == -1:  # a counter without an expiry would block for good, so give it one
            await r.expire(key, WINDOW_SECONDS)
            ttl = WINDOW_SECONDS
        return max(int(ttl), 1)
    except Exception as error:
        _log_unavailable(error)
        return 0


async def record_failure(identifier: str, *, redis: Any = None) -> None:
    """Count one failed sign-in for the account."""
    try:
        r = redis if redis is not None else await _client()
        key = _key(identifier)
        count = await r.incr(key)
        if count == 1 or await r.ttl(key) == -1:  # new window, or a counter that lost its expiry
            await r.expire(key, WINDOW_SECONDS)
    except Exception as error:
        _log_unavailable(error)


async def reset_failures(identifier: str, *, redis: Any = None) -> None:
    """Forget the account's failures (after a correct password or a password reset)."""
    try:
        r = redis if redis is not None else await _client()
        await r.delete(_key(identifier))
    except Exception as error:
        _log_unavailable(error)
