"""
One-time LLM enrichment — doc2query-style expansion of `search_terms`.

For every GlobalItem, a cheap DeepInfra-hosted instruct LLM generates search
aliases a real customer might type:

    - Arabic name (normalized) and English name
    - brand name in Arabic AND Latin script (e.g. غزالين / Ghazaleen)
    - 2-3 common Arabic synonyms / dialect words
    - 1-2 Arabizi spellings
    - category label in both languages

The aliases are merged into the existing (deterministic) `search_terms`, then
`text_embedding` is re-encoded from name + description + search_terms so both
the lexical tsvector branch and the semantic branch benefit.

Cost: one small LLM call + one embedding call per item — a one-time spend of
roughly a few dollars for thousands of items.

Run (from backend/ directory):
    python scripts/enrich_search_terms_llm.py                 # only items missing LLM enrichment marker-wise: processes ALL items
    python scripts/enrich_search_terms_llm.py --limit 100     # trial run on 100 items
    python scripts/enrich_search_terms_llm.py --qps 2         # throttle provider calls
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import async_session  # type: ignore
from app.config import settings
from app.models.global_item import GlobalItem
from app.models.category import Category
from app.services.embedding import embedding_service
from app.services.arabic_norm import normalize_arabic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_llm")

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.S)

_SYSTEM_PROMPT = (
    "You enrich product search metadata for a retail marketplace in the Middle "
    "East. Given a product (name, description, category), return ONLY a JSON "
    "array of up to 10 short search aliases a customer might type, covering: "
    "the Arabic name (no diacritics), the English name, the brand name in "
    "Arabic AND in Latin script if a brand is present, 2-3 common Arabic "
    "synonyms or dialect words, 1-2 Arabizi (Latin-letter Arabic) spellings, "
    "and the category in Arabic and English. No duplicates, no explanations, "
    "JSON array of strings only."
)


async def _llm_aliases(client, name: str, description: str | None,
                       category: str | None) -> list[str]:
    """One chat-completion call → list of alias strings ([] on any failure)."""
    user_msg = f"name: {name}"
    if description:
        user_msg += f"\ndescription: {description[:300]}"
    if category:
        user_msg += f"\ncategory: {category}"

    try:
        resp = await client.post(
            f"{settings.deepinfra_api_base}/openai/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepinfra_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.expansion_model,
                "temperature": 0.2,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        match = _JSON_ARRAY_RE.search(content or "")
        if not match:
            return []
        raw = json.loads(match.group(0))
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for a in raw:
            if isinstance(a, str):
                a = a.strip()
                if a and len(a) <= 80:
                    out.append(a)
        return out[:10]
    except Exception as e:
        logger.warning(f"LLM aliases failed for '{name[:40]}': {e}")
        return []


def _merge_terms(existing: str | None, aliases: list[str]) -> str:
    """Append aliases not already present (normalized substring check)."""
    merged = (existing or "").strip()
    norm_existing = normalize_arabic(merged)
    for alias in aliases:
        norm_alias = normalize_arabic(alias)
        if norm_alias and norm_alias not in norm_existing:
            merged = f"{merged} {alias}".strip()
            norm_existing = f"{norm_existing} {norm_alias}"
    return merged


async def enrich(limit: int | None = None, batch_size: int = 32, qps: int = 3) -> None:
    logger.info("LLM enrichment starting (limit=%s, batch=%d, qps=%d).",
                limit, batch_size, qps)
    embedding_service.load_model()

    try:
        import httpx
    except ImportError:
        logger.error("httpx is required. pip install httpx")
        return

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        async with async_session() as db:  # type: AsyncSession
            stmt = select(GlobalItem, Category).outerjoin(
                Category, GlobalItem.category_id == Category.id
            )
            if limit:
                stmt = stmt.limit(limit)

            rows = (await db.execute(stmt)).unique().all()
            logger.info(f"Found {len(rows)} items to enrich.")

            updated = 0
            min_interval = 1.0 / max(1, qps)

            for gi, cat in rows:
                try:
                    t0 = time.monotonic()
                    category_name = cat.name if cat is not None else None

                    aliases = await _llm_aliases(
                        client, gi.name, gi.description, category_name
                    )
                    if aliases:
                        gi.search_terms = _merge_terms(gi.search_terms, aliases)

                        vec = await embedding_service.encode_product_async(
                            name=gi.name,
                            description=gi.description,
                            search_terms=gi.search_terms,
                        )
                        gi.text_embedding = vec.tolist()
                        updated += 1

                    if updated and updated % batch_size == 0:
                        await db.commit()
                        logger.info(f"Committed batch — {updated} items enriched.")

                    elapsed = time.monotonic() - t0
                    if elapsed < min_interval:
                        await asyncio.sleep(min_interval - elapsed)
                except Exception as e:
                    logger.error(f"Failed on item {gi.id} ({gi.name}): {e}",
                                 exc_info=True)

            await db.commit()
            logger.info(f"LLM enrichment complete. {updated} items enriched.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM doc-expansion of search_terms + re-embedding."
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N items (trial run).")
    parser.add_argument("--batch", type=int, default=32,
                        help="Commit batch size (default 32).")
    parser.add_argument("--qps", type=int, default=3,
                        help="Max provider requests per second (default 3).")
    args = parser.parse_args()
    asyncio.run(enrich(limit=args.limit, batch_size=args.batch, qps=args.qps))


if __name__ == "__main__":
    main()
