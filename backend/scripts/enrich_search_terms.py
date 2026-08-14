"""
Search Terms Enrichment Script — Production-Grade Jordanian Retail Term Generator.

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
from app.services.llm import llm_adapter
from app.services.arabic_norm import normalize_arabic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_search_terms")

ENRICHMENT_PROMPT = """You are a search index builder for a retail marketplace serving ALL Arab countries.

Given this product:
Name: {name}
Description: {description}  
Category: {category}

Generate a comprehensive, comma-separated list of search terms. Include ALL of the following:

1. Formal Arabic (فصحى) name and synonyms
2. English name and common English variants
3. Arabizi/Franco-Arab spellings (e.g., 7aleeb, za3tar, knafeh, shawarma, falafel, labneh, mansaf)
4. CRITICAL — Dialectal Arabic from EVERY major dialect. Be thorough:
   Jordanian/Palestinian: e.g., دجاج→جاج, ثوم→توم, سكر→شكر, بطاطس→بطاطا, خبز→خبز كماج
   Egyptian: e.g., دجاج→فراخ, خبز→عيش, طماطم→أوطة, بصل→بصلة, ليمون→لمون, فاصوليا→فصوليا
   Gulf/Saudi: e.g., دجاج→دياي, شاي→چاي, فطور→ريوق, ملعقة→خاشوقة, لبن→روب
   Iraqi: e.g., دجاج→دجاج, خبز→صمون, طماطم→طماطة
   Levantine: e.g., بندورة→بندوره, باذنجان→بتنجان
   Maghrebi: e.g., خبز→كسرة, بطاطا→بطاطا
5. Common misspellings and taa marbouta variants (e.g., بامية→باميه, كوسة→كوسا, جبنة→جبنه)
6. Brand-associated terms if applicable (do NOT translate brand names)
7. Category and related terms
8. Occasion/use-case tags: هدية/gift, فطور/breakfast, تنظيف/cleaning, طبخ/cooking, ضيافة/hospitality, رمضان/ramadan, حفلة/party, أطفال/kids, مدرسة/school
9. Recipe/dish associations: If this product is a key ingredient in known dishes, include those dish names
   e.g., for chicken: مقلوبة, مسخن, شاورما, فتة. For rice: منسف, كبسة, مقلوبة

Generate at LEAST 20 terms. More is better. Return ONLY a comma-separated list, no explanations."""


async def enrich_product(name: str, description: Optional[str], category: Optional[str]) -> str:
    """Call the LLM with the Jordanian search terms builder prompt using Gemma 4 31B."""
    prompt = ENRICHMENT_PROMPT.format(
        name=name or "",
        description=description or "",
        category=category or "",
    )

    try:
        response = await llm_adapter.generate(
            system_prompt="Return only comma-separated search terms. No explanations.",
            user_prompt=prompt,
            model=settings.offline_llm_model,  # Uses Gemma 4 31B
            enable_thinking=False,
            max_tokens=500,  # Enrichment needs more tokens than query understanding
        )
        if not response:
            return ""

        # Clean any accidental fences or extra lines
        cleaned = response.replace("\n", ", ").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1].strip()
        return cleaned
    except Exception as e:
        logger.warning(f"Enrichment LLM call failed for '{name[:30]}': {e}")
        return ""


def _merge_terms(existing: Optional[str], new_terms_csv: str) -> str:
    """Merge new comma-separated terms into existing search terms with deduplication."""
    existing_list = [t.strip() for t in (existing or "").replace(",", " ").split() if t.strip()]
    seen_norm = {normalize_arabic(t) for t in existing_list if t}

    new_list = [t.strip() for t in new_terms_csv.split(",") if t.strip()]
    merged_terms = list(existing_list)

    for term in new_list:
        norm_t = normalize_arabic(term)
        if norm_t and norm_t not in seen_norm:
            seen_norm.add(norm_t)
            merged_terms.append(term)

    return " ".join(merged_terms)


async def run_enrichment(limit: Optional[int] = None, batch_size: int = 20, concurrency: int = 10, force: bool = False) -> None:
    logger.info(f"Starting product search terms enrichment (limit={limit}, batch_size={batch_size}, concurrency={concurrency}, force={force})")

    async with async_session() as db:
        stmt = select(GlobalItem, Category).outerjoin(
            Category, GlobalItem.category_id == Category.id
        )
        if not force:
            stmt = stmt.where(
                (GlobalItem.search_terms.is_(None)) | (GlobalItem.search_terms == "")
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
                cat_name = cat.name if cat is not None else None
                name_val = item.name_ar or item.name or ""
                desc_val = item.description_ar or item.description or ""

                terms = await enrich_product(name=name_val, description=desc_val, category=cat_name)
                if terms:
                    item.search_terms = _merge_terms(item.search_terms, terms)
                    updated_count += 1
                    logger.info(f"[{idx+1}/{total_items}] Enriched '{name_val}': {terms[:80]}...")

        for i in range(0, total_items, batch_size):
            chunk = rows[i : i + batch_size]
            tasks = [_process_item(i + j, item, cat) for j, (item, cat) in enumerate(chunk)]
            await asyncio.gather(*tasks)
            await db.commit()
            logger.info(f"Committed batch: {min(i + batch_size, total_items)}/{total_items} items processed.")

        await db.commit()
        logger.info(f"Enrichment completed successfully! Enriched {updated_count}/{total_items} products.")

        # Rebuild synonym table from enriched catalog
        try:
            from scripts.build_synonym_table import build_synonym_table
            await build_synonym_table()
        except Exception as e:
            logger.warning(f"Synonym table rebuild failed/skipped: {e}")

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
