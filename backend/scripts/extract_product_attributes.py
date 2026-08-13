"""
Product Attribute Extraction Script — LLM-based structured attribute extractor.

For each GlobalItem, calls the LLM to extract structured attributes from the
product name and description, then stores merged results in the `attributes`
JSONB column. Existing service-level attributes (appointment_required, etc.)
are preserved via merge.

Usage:
    python -m scripts.extract_product_attributes --dry-run
    python -m scripts.extract_product_attributes
    python -m scripts.extract_product_attributes --limit 50 --concurrency 5
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
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import async_session
from app.models.global_item import GlobalItem
from app.models.category import Category
from app.services.llm import llm_adapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("extract_product_attributes")

ATTRIBUTE_EXTRACTION_PROMPT = """You are a product attribute extractor for a retail marketplace.

Given this product:
Name: {name}
Description: {description}
Category: {category}

Extract structured attributes as a JSON object. Only include attributes that are clearly present — do not guess.

Standard attribute keys:
- "type": product sub-type (e.g., "أخضر"/"green" for green tea, "بلدي" for local, "فوري"/"instant" for instant coffee)
- "color": color if relevant (e.g., "أحمر", "أبيض", "أسمر")
- "flavor": flavor/infusion (e.g., "نعناع"/"mint", "ليمون"/"lemon")
- "origin": country/region of origin (e.g., "فلسطيني", "أردني", "يوناني", "صيني")
- "organic": true/false
- "size": size descriptor (e.g., "كبير", "صغير", "500مل", "1كغ")
- "brand": brand name if present
- "temperature": "hot"/"cold"/"iced" if relevant
- "dietary": dietary info (e.g., "خالي من الغلوتين", "قليل الدسم", "بدون سكر", "بدون كافيين")
- "material": material if relevant (e.g., "بلاستيك", "خشب", "زجاج")
- "gender": "male"/"female"/"unisex" if relevant (personal care products)

Examples:
- "شاي أخضر صيني" → {{"type": "أخضر", "origin": "صيني"}}
- "زيت زيتون بالليمون" → {{"flavor": "ليمون"}}
- "جبنة بيضاء بلدية" → {{"type": "بيضاء", "origin": "بلدي"}}
- "قهوة تركية بدون هيل" → {{"type": "تركية", "flavor": "بدون هيل"}}
- "حليب قليل الدسم" → {{"dietary": "قليل الدسم"}}
- "صابون نابلسي" → {{"origin": "نابلسي"}}
- "مزيل عرق نسائي" → {{"gender": "female"}}

Return ONLY the JSON object. If no attributes can be extracted, return {{}}.
Do not include the product name or description in the attributes."""

# Only these keys are allowed in the output — anything else is discarded.
ALLOWED_ATTR_KEYS = {
    "type", "color", "flavor", "origin", "organic", "size",
    "brand", "temperature", "dietary", "material", "gender",
}

# Service-specific keys that must never be overwritten by LLM extraction.
SERVICE_ATTR_KEYS = {"appointment_required", "home_service_available"}


def _clean_json_response(text: str) -> str:
    """Strip markdown fences and leading/trailing whitespace from LLM response."""
    if not text:
        return "{}"
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ``` wrappers
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


async def extract_attributes_for_product(
    name: str,
    description: str,
    category: str,
) -> dict:
    """Call the LLM to extract structured attributes for a single product."""
    prompt = ATTRIBUTE_EXTRACTION_PROMPT.format(
        name=name,
        description=description,
        category=category,
    )
    messages = [
        {"role": "system", "content": "Return only valid JSON. No explanations."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = await llm_adapter.complete_chat(
            messages=messages,
            temperature=0.0,
            max_tokens=200,
            timeout=15.0,
            chat_template_kwargs={"enable_thinking": False},
        )
        if not raw:
            return {}

        cleaned = _clean_json_response(raw)
        parsed = json.loads(cleaned)

        if not isinstance(parsed, dict):
            return {}

        # Whitelist: only keep allowed attribute keys
        filtered = {
            k: v for k, v in parsed.items()
            if k in ALLOWED_ATTR_KEYS and v is not None
        }
        return filtered

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed for '{name[:40]}': {e} — raw: {raw[:100] if raw else '(empty)'}")
        return {}
    except Exception as e:
        logger.warning(f"Attribute extraction failed for '{name[:40]}': {e}")
        return {}


def _merge_attributes(existing: dict | None, new_attrs: dict) -> dict:
    """
    Merge new LLM-extracted attributes into existing attributes.
    Preserves service-specific keys (appointment_required, home_service_available, etc.)
    and never overwrites them with LLM output.
    """
    merged = dict(existing or {})
    for k, v in new_attrs.items():
        if k in SERVICE_ATTR_KEYS:
            continue  # Never overwrite service keys
        merged[k] = v
    return merged


async def run_extraction(
    limit: Optional[int] = None,
    batch_size: int = 20,
    concurrency: int = 10,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    logger.info(
        f"Starting attribute extraction (limit={limit}, batch_size={batch_size}, "
        f"concurrency={concurrency}, force={force}, dry_run={dry_run})"
    )

    async with async_session() as db:
        stmt = select(GlobalItem, Category).outerjoin(
            Category, GlobalItem.category_id == Category.id
        )
        if not force:
            # Only process items with empty attributes (no LLM-extracted keys)
            # Items with only service keys are still considered "empty" for products
            stmt = stmt.where(
                (GlobalItem.attributes.is_(None))
                | (GlobalItem.attributes == {})
            )
        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        rows = result.unique().all()
        total_items = len(rows)
        logger.info(f"Found {total_items} items to process.")

        if total_items == 0:
            print("No items need attribute extraction. Use --force to re-extract all.")
            return

        if dry_run:
            # Dry run: process first 10 items and display results
            preview_count = min(10, total_items)
            print(f"\n{'='*80}")
            print(f"DRY RUN — Extracting attributes for first {preview_count} products")
            print(f"{'='*80}\n")

            semaphore = asyncio.Semaphore(concurrency)

            async def _extract_one(item: GlobalItem, cat: Optional[Category]) -> tuple:
                async with semaphore:
                    name_val = item.name_ar or item.name or ""
                    desc_val = item.description_ar or item.description or ""
                    cat_name = cat.name if cat else ""
                    new_attrs = await extract_attributes_for_product(name_val, desc_val, cat_name)
                    merged = _merge_attributes(item.attributes, new_attrs)
                    return item, name_val, new_attrs, merged

            tasks = [
                _extract_one(item, cat)
                for item, cat in rows[:preview_count]
            ]
            results = await asyncio.gather(*tasks)

            for i, (item, name_val, new_attrs, merged) in enumerate(results, 1):
                existing = item.attributes or {}
                print(f"[{i}] {name_val}")
                print(f"    listing_type: {item.listing_type}")
                print(f"    existing attrs: {json.dumps(existing, ensure_ascii=False)}")
                print(f"    LLM extracted:  {json.dumps(new_attrs, ensure_ascii=False)}")
                print(f"    merged result:  {json.dumps(merged, ensure_ascii=False)}")
                print()

            print(f"{'='*80}")
            print(f"DRY RUN complete. No changes saved. Run without --dry-run to apply.")
            print(f"{'='*80}")
            return

        # Full run: process all items in batches
        semaphore = asyncio.Semaphore(concurrency)
        updated_count = 0
        skipped_count = 0

        async def _process_item(idx: int, item: GlobalItem, cat: Optional[Category]):
            nonlocal updated_count, skipped_count
            async with semaphore:
                name_val = item.name_ar or item.name or ""
                desc_val = item.description_ar or item.description or ""
                cat_name = cat.name if cat else ""

                new_attrs = await extract_attributes_for_product(name_val, desc_val, cat_name)
                if new_attrs:
                    item.attributes = _merge_attributes(item.attributes, new_attrs)
                    updated_count += 1
                    logger.info(
                        f"[{idx+1}/{total_items}] ✓ '{name_val[:50]}' → "
                        f"{json.dumps(new_attrs, ensure_ascii=False)}"
                    )
                else:
                    skipped_count += 1
                    logger.debug(f"[{idx+1}/{total_items}] - '{name_val[:50]}' → no attributes extracted")

        for i in range(0, total_items, batch_size):
            chunk = rows[i : i + batch_size]
            tasks = [_process_item(i + j, item, cat) for j, (item, cat) in enumerate(chunk)]
            await asyncio.gather(*tasks)
            await db.commit()
            logger.info(
                f"Committed batch: {min(i + batch_size, total_items)}/{total_items} "
                f"(updated={updated_count}, skipped={skipped_count})"
            )

        await db.commit()
        logger.info(
            f"Attribute extraction complete! "
            f"Updated: {updated_count}/{total_items}, Skipped: {skipped_count}"
        )


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Extract structured product attributes using LLM"
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to process")
    parser.add_argument("--batch-size", type=int, default=20, help="Commit batch size (default 20)")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent LLM requests (default 10)")
    parser.add_argument("--force", action="store_true", help="Re-extract all products, even if attributes exist")
    parser.add_argument("--dry-run", action="store_true", help="Preview first 10 extractions without saving")
    args = parser.parse_args()

    asyncio.run(
        run_extraction(
            limit=args.limit,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            force=args.force,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
