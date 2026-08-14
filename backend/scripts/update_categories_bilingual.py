"""
Update all categories in PostgreSQL with proper name_ar, name_en, and listing_type.
"""

import asyncio
from sqlalchemy import select, update, text
from app.database import async_session
from app.models.category import Category

CATEGORY_UPDATES = {
    # Roots
    "Food & Beverages": {
        "name_ar": "الأغذية والمشروبات",
        "name_en": "Food & Beverages",
        "listing_type": "product",
    },
    "Home & Personal Care": {
        "name_ar": "العناية الشخصية والمنزلية",
        "name_en": "Home & Personal Care",
        "listing_type": "product",
    },
    "Electronics & Tech": {
        "name_ar": "الإلكترونيات والتقنية",
        "name_en": "Electronics & Tech",
        "listing_type": "product",
    },
    "Home & Kitchen": {
        "name_ar": "المنزل والمطبخ",
        "name_en": "Home & Kitchen",
        "listing_type": "product",
    },
    "Services": {
        "name_ar": "الخدمات",
        "name_en": "Services",
        "listing_type": "service",
    },
    # Subcategories - Product
    "Fruits & Vegetables": {
        "name_ar": "الخضار والفواكه",
        "name_en": "Fruits & Vegetables",
        "listing_type": "product",
    },
    "Cooking Essentials": {
        "name_ar": "مستلزمات الطبخ",
        "name_en": "Cooking Essentials",
        "listing_type": "product",
    },
    "Dairy & Eggs": {
        "name_ar": "الألبان والبيض",
        "name_en": "Dairy & Eggs",
        "listing_type": "product",
    },
    "Meat & Poultry": {
        "name_ar": "اللحوم والدواجن",
        "name_en": "Meat & Poultry",
        "listing_type": "product",
    },
    "Beverages": {
        "name_ar": "المشروبات",
        "name_en": "Beverages",
        "listing_type": "product",
    },
    "Snacks": {
        "name_ar": "الوجبات الخفيفة",
        "name_en": "Snacks",
        "listing_type": "product",
    },
    "Bakery": {
        "name_ar": "المخبوزات",
        "name_en": "Bakery",
        "listing_type": "product",
    },
    "Frozen Food": {
        "name_ar": "الأطعمة المجمدة",
        "name_en": "Frozen Food",
        "listing_type": "product",
    },
    "Cleaning & Detergents": {
        "name_ar": "منظفات ومعقمات",
        "name_en": "Cleaning & Detergents",
        "listing_type": "product",
    },
    "Beauty & Personal Care": {
        "name_ar": "العناية الشخصية",
        "name_en": "Beauty & Personal Care",
        "listing_type": "product",
    },
    "Electronics": {
        "name_ar": "الإلكترونيات",
        "name_en": "Electronics",
        "listing_type": "product",
    },
    "Mobiles & Tech": {
        "name_ar": "الهواتف والتقنية",
        "name_en": "Mobiles & Tech",
        "listing_type": "product",
    },
    "Cookware & Kitchenware": {
        "name_ar": "أدوات المطبخ",
        "name_en": "Cookware & Kitchenware",
        "listing_type": "product",
    },
    # Subcategories - Service
    "Beauty & Personal Care Services": {
        "name_ar": "خدمات التجميل والعناية الشخصية",
        "name_en": "Beauty & Personal Care Services",
        "listing_type": "service",
    },
    "Vehicle Maintenance & Care": {
        "name_ar": "صيانة وتغسيل السيارات",
        "name_en": "Vehicle Maintenance & Care",
        "listing_type": "service",
    },
    "Home & Maintenance Services": {
        "name_ar": "خدمات وصيانة المنازل",
        "name_en": "Home & Maintenance Services",
        "listing_type": "service",
    },
    "Education & Tutoring": {
        "name_ar": "التعليم والدروس الخصوصية",
        "name_en": "Education & Tutoring",
        "listing_type": "service",
    },
}


async def main():
    async with async_session() as db:
        res = await db.execute(select(Category))
        cats = res.scalars().all()
        print(f"Found {len(cats)} categories in database.")

        updated_count = 0
        for cat in cats:
            info = CATEGORY_UPDATES.get(cat.name)
            if info:
                cat.name_ar = info["name_ar"]
                cat.name_en = info["name_en"]
                cat.listing_type = info["listing_type"]
                updated_count += 1
            else:
                print(f"Unknown category without map: {cat.name}")

        await db.commit()
        print(f"Updated {updated_count} categories.")

        # Check for any remaining NULL name_ar or listing_type
        check_nulls = await db.execute(
            select(Category).where(
                (Category.name_ar.is_(None)) | (Category.listing_type.is_(None))
            )
        )
        null_cats = check_nulls.scalars().all()
        if null_cats:
            print(f"WARNING: {len(null_cats)} categories still have NULL values:")
            for nc in null_cats:
                print(f"  - {nc.name} (name_ar={nc.name_ar}, ltype={nc.listing_type})")
        else:
            print("SUCCESS: 100% of categories now have name_ar, name_en, and listing_type populated!")

        # Verify parent roots
        roots_res = await db.execute(select(Category).where(Category.parent_category_id.is_(None)))
        roots = roots_res.scalars().all()
        print(f"\nRoot Categories ({len(roots)}):")
        for r in roots:
            print(f"  - {r.name} -> {r.name_ar} (type: {r.listing_type})")

        # Verify services
        serv_res = await db.execute(select(Category).where(Category.listing_type == "service"))
        services = serv_res.scalars().all()
        print(f"\nService Categories ({len(services)}):")
        for s in services:
            print(f"  - {s.name} -> {s.name_ar} (parent_id: {s.parent_category_id})")


if __name__ == "__main__":
    asyncio.run(main())
