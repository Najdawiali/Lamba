import asyncio
import json
import hashlib
import logging
from typing import Optional, List, Dict, Any
import redis.asyncio as redis
from app.config import settings
from app.services.arabic_norm import normalize_arabic

logger = logging.getLogger(__name__)

_redis: Optional[redis.Redis] = None


async def get_redis() -> Any:
    """Get or initialize singleton async Redis client with fallback."""
    global _redis
    if _redis is None:
        try:
            r = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
            await asyncio.wait_for(r.ping(), timeout=0.5)
            _redis = r
        except Exception:
            try:
                import fakeredis.aioredis
                _redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
            except Exception:
                _redis = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    decode_responses=True,
                    socket_timeout=0.5,
                    socket_connect_timeout=0.5,
                )
    return _redis


def _cache_key(prefix: str, text: str, **kwargs) -> str:
    """Deterministic hash key generator."""
    raw = f"{text.strip().lower()}:{json.dumps(kwargs, sort_keys=True, default=str)}"
    hashed = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"lamba:{prefix}:{hashed}"


# ── Synonym Lookup Table (<1ms O(1) Redis HGET) ─────────────────────
async def lookup_synonym(term: str) -> Optional[str]:
    """
    O(1) Redis lookup for dialect → formal Arabic mapping.
    Returns the formal equivalent or None if not found.
    """
    try:
        r = await get_redis()
        normalized = normalize_arabic(term.strip())
        result = await r.hget("lamba:synonyms", normalized)
        if result:
            logger.debug(f"[SYNONYM HIT] '{term}' → '{result}'")
        return result
    except Exception:
        return None


async def lookup_synonyms_multi(terms: List[str]) -> Dict[str, str]:
    """Batch lookup for multiple terms."""
    try:
        r = await get_redis()
        pipe = r.pipeline()
        normalized_terms = [normalize_arabic(t.strip()) for t in terms]
        for nt in normalized_terms:
            pipe.hget("lamba:synonyms", nt)
        results = await pipe.execute()
        return {
            terms[i]: results[i]
            for i in range(len(terms))
            if results[i] is not None
        }
    except Exception:
        return {}


# ── Expansion cache (saves expensive LLM call) ──────────────────────
async def get_cached_expansion(query: str) -> Optional[List[str]]:
    """Retrieve cached query expansion variants from Redis."""
    try:
        r = await get_redis()
        key = _cache_key("exp", query)
        cached = await r.get(key)
        if cached:
            logger.debug(f"[CACHE HIT] expansion for '{query}'")
            return json.loads(cached)
    except Exception as e:
        logger.debug(f"[CACHE ERROR] get_cached_expansion failed: {e}")
    return None


async def cache_expansion(query: str, variants: List[str]) -> None:
    """Store query expansion variants in Redis with TTL."""
    if not variants:
        return
    try:
        r = await get_redis()
        key = _cache_key("exp", query)
        await r.set(key, json.dumps(variants, ensure_ascii=False), ex=settings.cache_expansion_ttl)
    except Exception as e:
        logger.debug(f"[CACHE ERROR] cache_expansion failed: {e}")


# ── Full search result cache ────────────────────────────────────────
async def get_cached_search(
    query: str, lat: float, lng: float, listing_type: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Retrieve cached hybrid search response from Redis."""
    try:
        r = await get_redis()
        key = _cache_key(
            "search",
            query,
            lat=round(lat, 3),
            lng=round(lng, 3),
            lt=listing_type or "all",
        )
        cached = await r.get(key)
        if cached:
            logger.debug(f"[CACHE HIT] full search for '{query}'")
            return json.loads(cached)
    except Exception as e:
        logger.debug(f"[CACHE ERROR] get_cached_search failed: {e}")
    return None


async def cache_search(
    query: str, lat: float, lng: float, listing_type: Optional[str], result: Any
) -> None:
    """Store serialized search response in Redis with TTL."""
    try:
        r = await get_redis()
        key = _cache_key(
            "search",
            query,
            lat=round(lat, 3),
            lng=round(lng, 3),
            lt=listing_type or "all",
        )
        # Handle dict or Pydantic model serialization
        if hasattr(result, "model_dump"):
            payload = result.model_dump(mode="json")
        elif hasattr(result, "dict"):
            payload = result.dict()
        else:
            payload = result

        serialized = json.dumps(payload, default=str, ensure_ascii=False)
        await r.set(key, serialized, ex=settings.cache_search_ttl)
    except Exception as e:
        logger.debug(f"[CACHE ERROR] cache_search failed: {e}")


async def close_redis() -> None:
    """Close Redis connection pool gracefully during shutdown."""
    global _redis
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:
            pass
        _redis = None

