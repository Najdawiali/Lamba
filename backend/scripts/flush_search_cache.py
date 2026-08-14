import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.services.cache import get_redis
from scripts.build_synonym_table import build_synonym_table


async def main():
    r = await get_redis()
    if r:
        # Delete search query caches
        keys = await r.keys("search:*")
        if keys:
            await r.delete(*keys)
            print(f"Cleared {len(keys)} cached search query keys from Redis.")
        else:
            print("No cached search keys found in Redis.")
    
    # Rebuild synonym table
    await build_synonym_table()
    print("Synonym table ready.")


if __name__ == "__main__":
    asyncio.run(main())
