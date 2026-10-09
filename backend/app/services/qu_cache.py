"""
Cache and outcome counters for query understanding. Standard library only: the Redis client is a
parameter, so tests need no server, and every call fails soft (a cache is never allowed to break search).

The cache holds what the MODEL answered for a normalised query (not the rule-based attributes, which
are free to recompute), keyed by query + model + prompt version so that changing either invalidates it.
Beyond saving a model call it makes the answer for a query stable: the same query always gets the same
category and attributes, instead of whatever the model happened to say this time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

KEY_PREFIX = "lamba:qu:"
STATS_PREFIX = "lamba:stats:"
STATS_TTL_SECONDS = 14 * 24 * 3600

# What is cached (and what QueryIntent is rebuilt from).
FIELDS = ("intent", "category_name", "brand", "search_query", "query_clean", "attributes")


def cache_key(normalized_query: str, model: str, prompt_version: str) -> str:
    raw = f"{(normalized_query or '').strip().lower()}|{model}|{prompt_version}"
    return KEY_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _clean(fields: Any) -> Optional[dict]:
    """The cached shape, or None if the stored value is not usable."""
    if not isinstance(fields, dict) or not isinstance(fields.get("attributes", {}), dict):
        return None
    cleaned = {name: fields.get(name) for name in FIELDS}
    cleaned["attributes"] = cleaned["attributes"] or {}
    for name in FIELDS[:-1]:
        if cleaned[name] is not None and not isinstance(cleaned[name], str):
            return None
    return cleaned


async def get(redis_client: Any, key: str) -> Optional[dict]:
    if redis_client is None:
        return None
    try:
        stored = await redis_client.get(key)
        return _clean(json.loads(stored)) if stored else None
    except Exception as exc:  # unreachable Redis, corrupt value: a miss
        logger.debug("[QU CACHE] get failed: %r", exc)
        return None


async def put(redis_client: Any, key: str, fields: dict, ttl_seconds: int) -> bool:
    cleaned = _clean(fields)
    if redis_client is None or cleaned is None:
        return False
    try:
        await redis_client.set(key, json.dumps(cleaned, ensure_ascii=False), ex=ttl_seconds)
        return True
    except Exception as exc:
        logger.debug("[QU CACHE] put failed: %r", exc)
        return False


async def count(redis_client: Any, outcome: str, group: str = "qu", today: Optional[str] = None) -> None:
    """
    Add one to today's counter for `outcome`: read with
    HGETALL lamba:stats:<group>:<YYYY-MM-DD>   (kept for 14 days).
    """
    if redis_client is None:
        return
    day = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{STATS_PREFIX}{group}:{day}"
    try:
        await redis_client.hincrby(key, outcome, 1)
        await redis_client.expire(key, STATS_TTL_SECONDS)
    except Exception as exc:
        logger.debug("[QU STATS] count failed: %r", exc)
