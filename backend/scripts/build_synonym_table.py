"""
Load the curated dialect synonym table into Redis.

The result is a Redis hash built from CORE_SYNONYMS below:
  lamba:synonyms → {
    "عيش": "خبز",
    "جاج": "دجاج",
    "فراخ": "دجاج",
    "دياي": "دجاج",
    "شكر": "سكر",
    "توم": "ثوم",
    ...
  }

At query time, a single HGET lookup (<1ms) converts dialect terms
to their formal equivalent before embedding.

The catalog's search_terms are deliberately NOT mined for synonyms. That used to map every
term of every product to the name of the first product that listed it, which rewrote queries
into single product names. To add a dialect pair, add it to CORE_SYNONYMS.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Dict

# Ensure backend root is in sys.path when executed directly or as a module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.arabic_norm import normalize_arabic
from app.services.cache import get_redis

logger = logging.getLogger("build_synonym_table")

# Core standard dialect mappings across Arab regions
CORE_SYNONYMS = {
    "عيش": "خبز",
    "جاج": "دجاج",
    "فراخ": "دجاج",
    "دياي": "دجاج",
    "شكر": "سكر",
    "توم": "ثوم",
    "طماطة": "طماطم",
    "اوطة": "طماطم",
    "بندورة": "طماطم",
    "بندوره": "طماطم",
    "بتنجان": "باذنجان",
    "باميه": "بامية",
    "كوسه": "كوسا",
    "طربيزه": "طاولة",
    "بطاطس": "بطاطا",
    "صمون": "خبز",
    "ريوق": "فطور",
    "خاشوقة": "ملعقة",
    "خاشوقه": "ملعقة",
    "روب": "لبن",
    "لمون": "ليمون",
    "فصوليا": "فاصوليا",
    "چاي": "شاي",
    "شاهي": "شاي",
    "مي": "ماء",
    "مية": "ماء",
    "ميه": "ماء",
    "ماي": "ماء",
    "موية": "ماء",
    "مويه": "ماء",
}


async def build_synonym_table() -> Dict[str, str]:
    """
    Store the curated CORE_SYNONYMS in Redis under the 'lamba:synonyms' hash (replacing whatever
    was there) and return them. Nothing is read from the database.
    """
    synonyms: Dict[str, str] = {
        normalize_arabic(term): normalize_arabic(canonical)
        for term, canonical in CORE_SYNONYMS.items()
    }

    try:
        r = await get_redis()
        if synonyms:
            await r.delete("lamba:synonyms")
            # Store in batches
            batch_size = 500
            items_list = list(synonyms.items())
            for i in range(0, len(items_list), batch_size):
                batch = dict(items_list[i : i + batch_size])
                await r.hset("lamba:synonyms", mapping=batch)

        print(f"Built synonym table with {len(synonyms)} entries")

        # Print some examples
        examples = ["عيش", "جاج", "فراخ", "شكر", "توم", "دياي", "باميه", "طربيزه"]
        for ex in examples:
            normalized = normalize_arabic(ex)
            value = await r.hget("lamba:synonyms", normalized)
            print(f"  {ex} → {value or '(not found)'}")

    except Exception as e:
        logger.warning(f"Could not connect to Redis to save synonyms: {e}")
        print(f"Synonym table extraction finished ({len(synonyms)} entries), but Redis update skipped: {e}")

    return synonyms


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(build_synonym_table())
