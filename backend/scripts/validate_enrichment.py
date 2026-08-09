"""
Post-enrichment dialect coverage validation and auto-patching script.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import List

from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import async_session
from app.models.global_item import GlobalItem
from app.services.arabic_norm import normalize_arabic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_enrichment")

DIALECT_COVERAGE_CHECKS = {
    "chicken": {
        "product_keywords": ["دجاج", "chicken", "شاورما"],
        "must_include": ["جاج", "فراخ", "دياي", "فروج"],
    },
    "bread": {
        "product_keywords": ["خبز", "bread", "شراك", "صاج"],
        "must_include": ["عيش", "صمون", "كماج", "عيش بلدي"],
    },
    "sugar": {
        "product_keywords": ["سكر", "sugar"],
        "must_include": ["شكر"],
    },
    "tea": {
        "product_keywords": ["شاي", "tea"],
        "must_include": ["چاي", "شاهي"],
    },
    "garlic": {
        "product_keywords": ["ثوم", "garlic"],
        "must_include": ["توم", "تومة"],
    },
    "okra": {
        "product_keywords": ["بامية", "okra"],
        "must_include": ["باميه", "باميا"],
    },
    "knafeh": {
        "product_keywords": ["كنافة", "knafeh", "kunafa"],
        "must_include": ["كنافه", "knafeh", "kunafa"],
    },
    "rice": {
        "product_keywords": ["أرز", "رز", "rice"],
        "must_include": ["رز", "تمن", "ruz", "3riz"],
    },
    "lemon": {
        "product_keywords": ["ليمون", "lemon"],
        "must_include": ["لمون", "laymoon"],
    },
    "tomato": {
        "product_keywords": ["بندورة", "طماطم", "tomato"],
        "must_include": ["بندوره", "طماطم", "اوطة", "طماطة"],
    },
    "soap": {
        "product_keywords": ["صابون", "soap"],
        "must_include": ["صبون"],
    },
}

async def validate_and_fix(fix: bool = False):
    logger.info(f"Running dialect enrichment validation (fix={fix})...")
    
    async with async_session() as db:
        stmt = select(GlobalItem)
        result = await db.execute(stmt)
        items: List[GlobalItem] = result.unique().scalars().all()
        
        total_missing = 0
        fixed_count = 0
        
        for item in items:
            name_norm = normalize_arabic(f"{item.name or ''} {item.name_ar or ''} {item.name_en or ''} {item.description or ''} {item.description_ar or ''}")
            terms_norm = normalize_arabic(item.search_terms or "")
            existing_terms = item.search_terms or ""
            
            item_missing_terms = []
            
            for category_name, rule in DIALECT_COVERAGE_CHECKS.items():
                matches_cat = any(
                    normalize_arabic(kw) in name_norm or normalize_arabic(kw) in terms_norm
                    for kw in rule["product_keywords"]
                )
                if matches_cat:
                    for must_term in rule["must_include"]:
                        must_norm = normalize_arabic(must_term)
                        if must_norm not in terms_norm:
                            item_missing_terms.append(must_term)
            
            if item_missing_terms:
                unique_missing = list(dict.fromkeys(item_missing_terms))
                total_missing += len(unique_missing)
                item_name = item.name_ar or item.name or str(item.id)
                logger.warning(f"Product '{item_name}' missing dialect terms: {unique_missing}")
                
                if fix:
                    if existing_terms.strip():
                        updated_terms = f"{existing_terms}, {', '.join(unique_missing)}"
                    else:
                        updated_terms = ", ".join(unique_missing)
                    item.search_terms = updated_terms
                    fixed_count += 1
        
        if fix and fixed_count > 0:
            await db.commit()
            logger.info(f"Validation completed! Auto-patched {fixed_count} products with {total_missing} missing dialect terms.")
        else:
            logger.info(f"Validation completed! Found {total_missing} missing dialect terms across products (fix={fix}).")

def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        
    parser = argparse.ArgumentParser(description="Validate and auto-patch dialect search terms")
    parser.add_argument("--fix", action="store_true", help="Auto-append missing dialect terms to search_terms")
    args = parser.parse_args()
    
    asyncio.run(validate_and_fix(fix=args.fix))

if __name__ == "__main__":
    main()
