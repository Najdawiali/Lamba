"""
Build a synonym lookup table from enriched product search_terms.

For each product, the enrichment LLM generated terms like:
  "دجاج, جاج, فراخ, دياي, chicken, djaj, fara5"

This script extracts all terms and maps each one back to the product's
canonical name (name_ar or name). The result is a Redis hash:
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
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from typing import Dict, List

import redis.asyncio as redis
from sqlalchemy import select

# Ensure backend root is in sys.path when executed directly or as a module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import async_session
from app.config import settings
from app.models.global_item import GlobalItem
from app.services.arabic_norm import normalize_arabic
from app.services.cache import get_redis

logger = logging.getLogger("build_synonym_table")

# Terms that are too generic to be useful as synonyms
STOP_TERMS = {
    "هدية", "gift", "فطور", "breakfast", "تنظيف", "cleaning",
    "طبخ", "cooking", "ضيافة", "رمضان", "حفلة", "party",
    "مدرسة", "school", "أطفال", "kids", "صحي", "healthy",
    "عضوي", "organic", "طبيعي", "natural", "بلدي", "fresh",
    "طازج", "premium", "جودة", "quality",
}

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
    Extract dialect/synonym mappings from GlobalItem.search_terms
    and store them in Redis under the 'lamba:synonyms' hash.
    """
    synonyms: Dict[str, str] = {}

    # 1. Initialize with standard retail dialect mappings
    for term, canonical in CORE_SYNONYMS.items():
        synonyms[normalize_arabic(term)] = normalize_arabic(canonical)

    async with async_session() as session:
        result = await session.execute(
            select(GlobalItem.name, GlobalItem.name_ar, GlobalItem.search_terms)
            .where(GlobalItem.search_terms.isnot(None))
        )
        items = result.all()

    for name, name_ar, search_terms in items:
        # Canonical name = Arabic name if available, else English name
        canonical = name_ar or name
        if not canonical or not search_terms:
            continue

        canonical_normalized = normalize_arabic(canonical.strip())

        # Split search_terms by comma (or Arabic comma / newline)
        terms = [t.strip() for t in re.split(r"[,،\n]+", search_terms) if t.strip()]

        for term in terms:
            term_normalized = normalize_arabic(term.strip())

            # Skip if term is the canonical name itself
            if term_normalized == canonical_normalized:
                continue

            # Skip stop terms (too generic)
            if term_normalized in STOP_TERMS or term in STOP_TERMS:
                continue

            # Skip very short terms (1-2 chars) or very long terms (probably a phrase)
            if len(term_normalized) < 2 or len(term_normalized) > 20:
                continue

            # Skip English terms for Arabic canonical names (handled by cross-lingual embedding)
            if re.match(r"^[a-zA-Z0-9\s]+$", term) and re.search(r"[\u0600-\u06FF]", canonical):
                continue

            # Map this variant to the canonical product name
            # If multiple products claim the same variant, keep the first one
            if term_normalized not in synonyms:
                synonyms[term_normalized] = canonical_normalized

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
