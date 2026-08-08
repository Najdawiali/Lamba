"""
Backfill — populate `search_terms` and re-encode `text_embedding` for every GlobalItem.

The enrichment is deterministic and free — no LLM calls. For each item we build:

    search_terms = normalize_arabic(name)
                 + " " + translate_ar_to_en(name)    # English alias
                 + " " + translate_en_to_ar(name)    # Arabic alias
                 + " " + dialect/Arabizi hints
                 + " " + category label (if present)

Then re-encode text_embedding via Qwen3 using `name + description + search_terms`.

Idempotent: skips rows already populated unless --force is passed.

Run (from backend/ directory):
    python scripts/backfill_search_terms.py
    python scripts/backfill_search_terms.py --force
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import os
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import async_session  # type: ignore
from app.config import settings
from app.models.global_item import GlobalItem
from app.models.category import Category
from app.services.embedding import embedding_service
from app.services.translation import translate_ar_to_en, translate_en_to_ar
from app.services.arabic_norm import normalize_arabic, arabizi_to_arabic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")


def build_search_terms(name: str, description: str | None,
                        category_name: str | None) -> str:
    """
    Deterministic, free-of-cost enrichment: assemble aliases from translations
    and normalization variants so the lexical/tsvector branch and the Qwen3
    encoder both see شاي even when the original name is "Ghazaleen Tea".
    """
    parts: list[str] = []

    # 1. Normalized Arabic form (canonicalizes alef/hamza/etc.)
    norm_name = normalize_arabic(name)
    if norm_name:
        parts.append(norm_name)

    # 2. Bidirectional translations — Google's free public translate API.
    en_alias = translate_ar_to_en(name)
    ar_alias = translate_en_to_ar(name)
    if en_alias and en_alias != name:
        parts.append(en_alias)
    if ar_alias and ar_alias != name and ar_alias != norm_name:
        parts.append(ar_alias)

    # 3. Arabizi-transliterated form (so "shay" / "3asal" catalog names surface too)
    arabizi_form = arabizi_to_arabic(name)
    if arabizi_form and arabizi_form != name:
        parts.append(arabizi_form)

    # 4. Normalized description (short, helps category-style queries)
    if description:
        norm_desc = normalize_arabic(description)
        if norm_desc:
            parts.append(norm_desc)

    # 5. Category label — acts as a weak semantic anchor
    if category_name:
        parts.append(normalize_arabic(category_name))
        parts.append(translate_en_to_ar(category_name))

    # Dedup while preserving order
    seen: set[str] = set()
    unique = []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            unique.append(p)
    return " ".join(unique)


async def backfill(force: bool = False, batch_size: int = 32, qps: int = 5) -> None:
    """
    Enrich every GlobalItem with deterministic search_terms and re-encode
    text_embedding via the configured provider (DeepInfra by default).
    """
    logger.info(
        "Backfill starting (force=%s, batch=%d, qps=%d).",
        force, batch_size, qps,
    )
    embedding_service.load_model()

    async with async_session() as db:  # type: AsyncSession
        stmt = select(GlobalItem, Category).outerjoin(
            Category, GlobalItem.category_id == Category.id
        )
        if not force:
            stmt = stmt.where(GlobalItem.search_terms.is_(None))

        result = await db.execute(stmt)
        rows = result.unique().all()

        logger.info(f"Found {len(rows)} items to enrich.")
        updated = 0
        min_interval = 1.0 / max(1, qps)

        for gi, cat in rows:
            try:
                t0 = time.monotonic()
                category_name = cat.name if cat is not None else None
                terms = build_search_terms(gi.name, gi.description, category_name)
                gi.search_terms = terms

                # Async embedding call (DeepInfra serverless path)
                vec = await embedding_service.encode_product_async(
                    name=gi.name, description=gi.description, search_terms=terms
                )
                gi.text_embedding = vec.tolist()

                updated += 1
                if updated % batch_size == 0:
                    await db.commit()
                    logger.info(f"Committed batch — {updated} items enriched so far.")

                # Throttle to the configured QPS ceiling.
                elapsed = time.monotonic() - t0
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)
            except Exception as e:
                logger.error(f"Failed on item {gi.id} ({gi.name}): {e}", exc_info=True)
                await db.rollback()

        await db.commit()
        logger.info(f"Backfill complete. {updated} items enriched.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill search_terms & Qwen3 embeddings.")
    parser.add_argument("--force", action="store_true",
                        help="Re-enrich and re-encode every row, even if search_terms is populated.")
    parser.add_argument("--batch", type=int, default=32,
                        help="Commit batch size (default 32).")
    parser.add_argument("--qps", type=int, default=5,
                        help="Max provider requests per second (default 5).")
    args = parser.parse_args()
    asyncio.run(backfill(force=args.force, batch_size=args.batch, qps=args.qps))


if __name__ == "__main__":
    main()