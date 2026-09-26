"""
Search Terms Enrichment Script — batch (re-)enrichment of catalog items.

Picks up items without LLM search terms (embedding_status != "completed", e.g. rows
added by CSV upload) or, with --force, every item; enriches AND re-embeds each one.

Enriches each GlobalItem by calling the LLM once to generate comprehensive search terms:
1. Formal Arabic (فصحى) terms
2. Jordanian/Levantine dialectal Arabic terms
3. Common casual abbreviations (e.g. أرز → رز, دجاج → جاج, ثوم → توم)
4. English translations
5. Arabizi (Franco-Arabic) spellings
6. Common misspellings
7. Related category terms

Stores the comma-separated search terms in `global_items.search_terms`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import async_session
from app.config import settings
from app.models.global_item import GlobalItem
from app.models.category import Category
from app.services.item_enrichment import enrich_and_embed

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_search_terms")

# Prompt, LLM call and term merging live in app.services.item_enrichment so the
# merchant flow, CSV upload, catalog import and this script all behave identically.


async def run_enrichment(limit: Optional[int] = None, batch_size: int = 20, concurrency: int = 10, force: bool = False) -> None:
    logger.info(f"Starting product search terms enrichment (limit={limit}, batch_size={batch_size}, concurrency={concurrency}, force={force})")

    async with async_session() as db:
        stmt = select(GlobalItem, Category).outerjoin(
            Category, GlobalItem.category_id == Category.id
        )
        if not force:
            stmt = stmt.where(
                (GlobalItem.embedding_status.is_(None)) | (GlobalItem.embedding_status != "completed")
            )
        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        rows = result.unique().all()
        total_items = len(rows)
        logger.info(f"Found {total_items} items to enrich.")

        if total_items == 0:
            print("No items need enrichment. Use --force to re-enrich all items.")
            return

        semaphore = asyncio.Semaphore(concurrency)
        updated_count = 0

        async def _process_item(idx: int, item: GlobalItem, cat: Optional[Category]):
            nonlocal updated_count
            async with semaphore:
                cat_name = (cat.name_en or cat.name) if cat is not None else None
                if await enrich_and_embed(item, cat_name):
                    updated_count += 1
                    logger.info(f"[{idx+1}/{total_items}] Enriched + embedded '{item.name}'")

        for i in range(0, total_items, batch_size):
            chunk = rows[i : i + batch_size]
            tasks = [_process_item(i + j, item, cat) for j, (item, cat) in enumerate(chunk)]
            await asyncio.gather(*tasks)
            await db.commit()
            logger.info(f"Committed batch: {min(i + batch_size, total_items)}/{total_items} items processed.")

        await db.commit()
        logger.info(f"Enrichment completed successfully! Enriched {updated_count}/{total_items} products.")

        # The synonym table is a curated list and is intentionally NOT rebuilt from
        # catalog search terms (that mapped dialect words to single product names).

        # Resolve pending search alerts for newly enriched catalog items
        try:
            from app.services.alert_service import resolve_matching_alerts
            resolved = await resolve_matching_alerts(db)
            logger.info(f"Auto-resolved {resolved} search alerts matching newly enriched catalog items.")
        except Exception as e:
            logger.warning(f"Alert resolution step failed: {e}")



def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Enrich global_items search_terms using LLM")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to process")
    parser.add_argument("--batch-size", type=int, default=20, help="Commit batch size (default 20)")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent LLM requests (default 10)")
    parser.add_argument("--force", action="store_true", help="Re-enrich all products, even if search_terms exists")
    args = parser.parse_args()

    asyncio.run(run_enrichment(limit=args.limit, batch_size=args.batch_size, concurrency=args.concurrency, force=args.force))


if __name__ == "__main__":
    main()
