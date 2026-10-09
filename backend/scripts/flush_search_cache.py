"""
Delete the cached search results from Redis (the 5-minute full-response cache) and nothing else:
not the synonym table, not the query-understanding cache. Run it between two runs of scripts/eval_search.py
so the second run is computed, not served from the cache.

On the server (scripts/ is not in the image, so use a one-off command in the api container):

    docker compose exec -T api python -c "import asyncio; from app.services.cache import get_redis; ..."
    (see CLAUDE.md, "Golden-query comparison", for the exact command)
"""

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.services.cache import get_redis

# app.services.cache._cache_key("search", ...) builds "lamba:search:<md5>"
SEARCH_KEY_PATTERN = "lamba:search:*"


async def flush(redis_client) -> int:
    """Delete every cached search response; returns how many."""
    deleted = 0
    async for key in redis_client.scan_iter(match=SEARCH_KEY_PATTERN, count=500):
        await redis_client.delete(key)
        deleted += 1
    return deleted


async def main():
    r = await get_redis()
    if not r:
        print("No Redis connection.")
        return
    deleted = await flush(r)
    print(f"Cleared {deleted} cached search results from Redis." if deleted else "No cached search results found in Redis.")


if __name__ == "__main__":
    asyncio.run(main())
