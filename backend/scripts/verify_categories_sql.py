import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from sqlalchemy import text
from app.database import async_session

async def main():
    async with async_session() as db:
        sql_updates = [
            "UPDATE categories SET name_ar = 'الأغذية والمشروبات' WHERE name = 'Food & Beverages';",
            "UPDATE categories SET name_ar = 'المنزل والمطبخ' WHERE name = 'Home & Kitchen';",
            "UPDATE categories SET name_ar = 'العناية الشخصية والمنزلية' WHERE name = 'Home & Personal Care';",
            "UPDATE categories SET name_ar = 'الإلكترونيات والتقنية' WHERE name = 'Electronics & Tech';",
            "UPDATE categories SET name_ar = 'الخدمات' WHERE name = 'Services';",
            "UPDATE categories SET name_ar = 'الوجبات الخفيفة' WHERE name = 'Snacks';",
            "UPDATE categories SET name_ar = 'منظفات ومعقمات' WHERE name = 'Cleaning & Detergents';",
            "UPDATE categories SET name_ar = 'المخبوزات' WHERE name = 'Bakery';",
            "UPDATE categories SET name_ar = 'الألبان والبيض' WHERE name = 'Dairy & Eggs';",
            "UPDATE categories SET name_ar = 'اللحوم والدواجن' WHERE name = 'Meat & Poultry';",
            "UPDATE categories SET name_ar = 'الخضار والفواكه' WHERE name = 'Fruits & Vegetables';",
            "UPDATE categories SET name_ar = 'مستلزمات الطبخ' WHERE name = 'Cooking Essentials';",
            "UPDATE categories SET name_ar = 'المشروبات' WHERE name = 'Beverages';",
            "UPDATE categories SET name_ar = 'الأطعمة المجمدة' WHERE name = 'Frozen Food';",
            "UPDATE categories SET name_ar = 'أدوات المطبخ' WHERE name = 'Cookware & Kitchenware';",
            "UPDATE categories SET name_ar = 'العناية الشخصية' WHERE name = 'Beauty & Personal Care';",
            "UPDATE categories SET name_ar = 'الهواتف والتقنية' WHERE name = 'Mobiles & Tech';",
            "UPDATE categories SET name_ar = 'الإلكترونيات' WHERE name = 'Electronics';",
            "UPDATE categories SET name_ar = 'خدمات التجميل والعناية الشخصية' WHERE name = 'Beauty & Personal Care Services';",
            "UPDATE categories SET name_ar = 'صيانة وتغسيل السيارات' WHERE name = 'Vehicle Maintenance & Care';",
            "UPDATE categories SET name_ar = 'خدمات وصيانة المنازل' WHERE name = 'Home & Maintenance Services';",
            "UPDATE categories SET name_ar = 'التعليم والدروس الخصوصية' WHERE name = 'Education & Tutoring';",
        ]
        for query in sql_updates:
            await db.execute(text(query))
        await db.commit()

        res = await db.execute(text("SELECT name, name_ar FROM categories WHERE name_ar IS NULL;"))
        nulls = res.all()
        print(f"Remaining categories with NULL name_ar: {len(nulls)}")

        all_res = await db.execute(text("SELECT id, name, name_ar FROM categories ORDER BY name;"))
        print("\nAll categories in DB:")
        for r in all_res.all():
            print(f"  - {r[1]} => {r[2]}")

if __name__ == "__main__":
    asyncio.run(main())
