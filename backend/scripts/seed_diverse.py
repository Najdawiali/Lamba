"""
Lamba — Diverse Product Seeder
==============================

Inserts a small but deliberately DIVERSE catalog spanning the categories a real
general marketplace will carry: electronics, home goods, hardware, personal care,
auto parts, pharmacy, stationery, clothing.

Purpose: the food-only seed catalog cannot test whether the search pipeline
generalizes. This gives the benchmark real cross-domain items to retrieve.

Usage:
    docker exec eagle_api python scripts/seed_diverse.py
    docker exec eagle_api python scripts/seed_diverse.py --clear   # remove them first

Every product gets:
  - bilingual name (name_ar / name_en)
  - a description
  - correct category (created if missing)
  - search_terms enriched with category names (matches existing pipeline)
  - a real Qwen3 text embedding
  - a market_item row in the first available market so it is retrievable
"""

import argparse
import asyncio
import logging
import sys
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import engine
from app.models.global_item import GlobalItem
from app.models.category import Category
from app.models.market_item import MarketItem
from app.models.market import Market
from app.services.embedding import embedding_service

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed_diverse")

# Marker so we can find/remove exactly these rows later
SEED_TAG = "[diverse-seed]"


# ══════════════════════════════════════════════════════════════════
# CATEGORY TAXONOMY — what a real Jordanian marketplace needs
# ══════════════════════════════════════════════════════════════════
CATEGORIES = [
    # (english, arabic, parent_english_or_None, listing_type)
    ("Electronics & Tech",        "الإلكترونيات والتقنية",   None,                  "product"),
    ("Mobile Phones",             "الهواتف المحمولة",         "Electronics & Tech",  "product"),
    ("Home Appliances",           "الأجهزة المنزلية",         "Electronics & Tech",  "product"),

    ("Home & Kitchen",            "المنزل والمطبخ",           None,                  "product"),
    ("Kitchenware & Tableware",   "أدوات المطبخ والمائدة",    "Home & Kitchen",      "product"),
    ("Cleaning Tools",            "أدوات التنظيف",            "Home & Kitchen",      "product"),

    ("Hardware & Building",       "الحدادة ومواد البناء",     None,                  "product"),
    ("Metals & Rebar",            "الحديد والمعادن",          "Hardware & Building", "product"),
    ("Tools",                     "العدد اليدوية",            "Hardware & Building", "product"),

    ("Personal Care",             "العناية الشخصية",          None,                  "product"),
    ("Hair Care",                 "العناية بالشعر",           "Personal Care",       "product"),
    ("Oral Care",                 "العناية بالفم والأسنان",   "Personal Care",       "product"),

    ("Auto Parts & Care",         "قطع غيار وعناية السيارات", None,                  "product"),
    ("Pharmacy & Health",         "الصيدلية والصحة",          None,                  "product"),
    ("Stationery & Office",       "القرطاسية والمكتبية",      None,                  "product"),
    ("Clothing & Bags",           "الملابس والحقائب",         None,                  "product"),
]


# ══════════════════════════════════════════════════════════════════
# PRODUCTS — deliberately varied: brands, conditions, sizes, dialects
# ══════════════════════════════════════════════════════════════════
# (name_ar, name_en, description_ar, category_en, price, barcode)
PRODUCTS = [
    # ── Mobile Phones (used + new, brands, variants) ──────────────
    ("آيفون 13 مستعمل 128 جيجا", "iPhone 13 Used 128GB",
     "هاتف آيفون 13 مستعمل بحالة ممتازة، ذاكرة 128 جيجا، البطارية 89%",
     "Mobile Phones", 320.0, None),
    ("سامسونج جالكسي A54 جديد", "Samsung Galaxy A54 New",
     "هاتف سامسونج جالكسي A54 جديد بالكرتونة، 256 جيجا، ضمان سنة",
     "Mobile Phones", 245.0, None),
    ("تلفون مستعمل شاومي ريدمي", "Xiaomi Redmi Used Phone",
     "تلفون شاومي ريدمي نوت 12 مستعمل، نظيف، مع الشاحن",
     "Mobile Phones", 110.0, None),
    ("شاحن آيفون سريع 20 واط", "iPhone Fast Charger 20W",
     "شاحن أصلي سريع للآيفون بقوة 20 واط مع كيبل",
     "Mobile Phones", 12.0, None),
    ("كفر تلفون سيليكون شفاف", "Clear Silicone Phone Case",
     "كفر حماية سيليكون شفاف لجميع أنواع الهواتف",
     "Mobile Phones", 3.5, None),

    # ── Home Appliances ───────────────────────────────────────────
    ("مكنسة كهربائية 2000 واط", "Vacuum Cleaner 2000W",
     "مكنسة كهربائية قوية 2000 واط مع فلتر هيبا وكيس قابل للغسل",
     "Home Appliances", 89.0, None),
    ("مكنسة شحن لاسلكية", "Cordless Vacuum Cleaner",
     "مكنسة لاسلكية قابلة للشحن، خفيفة الوزن، مناسبة للسيارة والبيت",
     "Home Appliances", 65.0, None),
    ("غسالة أوتوماتيك 7 كيلو", "Automatic Washing Machine 7kg",
     "غسالة ملابس أوتوماتيك سعة 7 كيلو، توفير بالماء والكهرباء",
     "Home Appliances", 295.0, None),
    ("خلاط كهربائي زجاج", "Electric Glass Blender",
     "خلاط كهربائي بوعاء زجاجي 1.5 لتر، 3 سرعات",
     "Home Appliances", 34.0, None),
    ("مروحة عامود 16 انش", "Stand Fan 16 inch",
     "مروحة عامود قابلة للتعديل بالارتفاع، 3 سرعات، هادئة",
     "Home Appliances", 28.0, None),

    # ── Kitchenware & Tableware ───────────────────────────────────
    ("طقم فناجين قهوة 12 قطعة", "Coffee Cup Set 12 Pieces",
     "طقم فناجين قهوة عربية بورسلان 12 قطعة مع الصحون",
     "Kitchenware & Tableware", 18.0, None),
    ("طقم كاسات شاي استكانة", "Tea Glass Set Istikana",
     "طقم كاسات شاي استكانة زجاج 6 قطع مع الصحون الذهبية",
     "Kitchenware & Tableware", 14.0, None),
    ("طقم صحون عشاء 24 قطعة", "Dinner Plate Set 24 Pieces",
     "طقم صحون عشاء بورسلان أبيض 24 قطعة لـ 6 أشخاص",
     "Kitchenware & Tableware", 45.0, None),
    ("قدر ضغط 7 لتر ستانلس", "Pressure Cooker 7L Stainless",
     "قدر ضغط ستانلس ستيل 7 لتر مع صمام أمان",
     "Kitchenware & Tableware", 38.0, None),
    ("مقلاة تيفال غير لاصقة", "Tefal Non-Stick Frying Pan",
     "مقلاة تيفال أصلية 28 سم غير لاصقة مقاومة للخدش",
     "Kitchenware & Tableware", 22.0, None),

    # ── Cleaning Tools ────────────────────────────────────────────
    ("ممسحة أرضيات دوارة", "Spin Mop with Bucket",
     "ممسحة أرضيات دوارة مع دلو عصر، رأسين ميكروفايبر",
     "Cleaning Tools", 19.0, None),
    ("فرشاة تنظيف حمام", "Bathroom Cleaning Brush",
     "فرشاة تنظيف حمام بمقبض طويل وقاعدة",
     "Cleaning Tools", 4.5, None),

    # ── Metals & Rebar (hardware) ─────────────────────────────────
    ("مجرود حديد 12 مم", "Steel Rebar 12mm",
     "مجرود حديد تسليح قطر 12 مم، طول 12 متر، حديد أردني",
     "Metals & Rebar", 9.5, None),
    ("مجرود حديد 16 مم", "Steel Rebar 16mm",
     "مجرود حديد تسليح قطر 16 مم للأساسات والأعمدة",
     "Metals & Rebar", 16.0, None),
    ("مواسير حديد مربعة", "Square Steel Tubes",
     "مواسير حديد مربعة 4×4 سم سماكة 2 مم للاستخدامات الإنشائية",
     "Metals & Rebar", 11.0, None),
    ("صاج حديد مجلفن", "Galvanized Steel Sheet",
     "صاج حديد مجلفن مقاوم للصدأ، سماكة 0.5 مم",
     "Metals & Rebar", 24.0, None),

    # ── Tools ─────────────────────────────────────────────────────
    ("شاكوش حداد 1 كيلو", "Blacksmith Hammer 1kg",
     "شاكوش حداد وزن 1 كيلو بمقبض خشب متين",
     "Tools", 8.0, None),
    ("طقم مفكات 32 قطعة", "Screwdriver Set 32 Pieces",
     "طقم مفكات متنوعة 32 قطعة في علبة بلاستيك",
     "Tools", 15.0, None),
    ("دريل كهربائي 650 واط", "Electric Drill 650W",
     "دريل كهربائي 650 واط مع طقم لقم ومفتاح",
     "Tools", 42.0, None),

    # ── Hair Care (brands!) ───────────────────────────────────────
    ("شامبو هيد اند شولدرز 400 مل", "Head & Shoulders Shampoo 400ml",
     "شامبو هيد اند شولدرز ضد القشرة، 400 مل، للاستخدام اليومي",
     "Hair Care", 5.2, "5410076111121"),
    ("شامبو بانتين مقوي للشعر", "Pantene Strengthening Shampoo",
     "شامبو بانتين برو-في لتقوية الشعر ومنع التقصف، 400 مل",
     "Hair Care", 4.8, None),
    ("بلسم دوف مرطب", "Dove Moisturizing Conditioner",
     "بلسم دوف مرطب للشعر الجاف والتالف، 350 مل",
     "Hair Care", 4.5, None),
    ("زيت شعر أرغان طبيعي", "Natural Argan Hair Oil",
     "زيت أرغان مغربي طبيعي 100% لترطيب وتنعيم الشعر",
     "Hair Care", 7.5, None),

    # ── Oral Care ─────────────────────────────────────────────────
    ("معجون أسنان سيجنال", "Signal Toothpaste",
     "معجون أسنان سيجنال بالفلورايد لحماية الأسنان، 100 مل",
     "Oral Care", 2.1, None),
    ("فرشاة أسنان أورال بي", "Oral-B Toothbrush",
     "فرشاة أسنان أورال بي متوسطة النعومة",
     "Oral Care", 2.5, None),

    # ── Auto Parts ────────────────────────────────────────────────
    ("فلتر زيت تويوتا كورولا", "Toyota Corolla Oil Filter",
     "فلتر زيت أصلي لسيارة تويوتا كورولا موديل 2015-2022",
     "Auto Parts & Care", 6.5, None),
    ("فلتر هواء نيسان صني", "Nissan Sunny Air Filter",
     "فلتر هواء لسيارة نيسان صني، يحسن أداء المحرك",
     "Auto Parts & Care", 8.0, None),
    ("زيت محرك 5W-30 اصطناعي", "Engine Oil 5W-30 Synthetic",
     "زيت محرك اصطناعي بالكامل 5W-30، 4 لتر، لجميع السيارات",
     "Auto Parts & Care", 28.0, None),
    ("بطارية سيارة 70 أمبير", "Car Battery 70Ah",
     "بطارية سيارة 70 أمبير بضمان سنتين",
     "Auto Parts & Care", 65.0, None),
    ("مساحات زجاج أمامي", "Windshield Wipers",
     "طقم مساحات زجاج أمامي مقاس 22 و 20 إنش",
     "Auto Parts & Care", 9.0, None),

    # ── Pharmacy & Health ─────────────────────────────────────────
    ("بنادول اكسترا 24 حبة", "Panadol Extra 24 Tablets",
     "بنادول اكسترا مسكن للصداع وآلام الجسم، 24 حبة",
     "Pharmacy & Health", 3.2, None),
    ("فيتامين سي 1000 ملغ", "Vitamin C 1000mg",
     "أقراص فيتامين سي 1000 ملغ لتقوية المناعة، 30 قرص",
     "Pharmacy & Health", 6.5, None),
    ("كمامات طبية 50 قطعة", "Medical Face Masks 50pcs",
     "كمامات طبية ثلاث طبقات، علبة 50 قطعة",
     "Pharmacy & Health", 3.0, None),
    ("جهاز قياس ضغط رقمي", "Digital Blood Pressure Monitor",
     "جهاز قياس ضغط الدم رقمي أوتوماتيك للذراع",
     "Pharmacy & Health", 32.0, None),

    # ── Stationery & Office ───────────────────────────────────────
    ("دفتر 200 ورقة مسطر", "Notebook 200 Pages Lined",
     "دفتر مدرسي 200 ورقة مسطر بغلاف مقوى",
     "Stationery & Office", 1.8, None),
    ("طقم أقلام حبر أزرق", "Blue Ballpoint Pen Set",
     "طقم أقلام حبر جاف أزرق 10 أقلام",
     "Stationery & Office", 2.0, None),
    ("آلة حاسبة علمية", "Scientific Calculator",
     "آلة حاسبة علمية 240 وظيفة للطلاب والجامعات",
     "Stationery & Office", 12.0, None),
    ("ألوان خشبية 24 لون", "Colored Pencils 24 Colors",
     "علبة ألوان خشبية 24 لون للرسم والتلوين",
     "Stationery & Office", 4.0, None),

    # ── Clothing & Bags ───────────────────────────────────────────
    ("شنطة ظهر أطفال مدرسية", "Kids School Backpack",
     "شنطة ظهر مدرسية للأطفال بتصميم ملون وجيوب متعددة",
     "Clothing & Bags", 14.0, None),
    ("شنطة ظهر لابتوب", "Laptop Backpack",
     "شنطة ظهر لابتوب مقاومة للماء مع جيب مبطن حتى 15.6 إنش",
     "Clothing & Bags", 22.0, None),
    ("جاكيت شتوي رجالي", "Men's Winter Jacket",
     "جاكيت شتوي رجالي مبطن ضد الماء والرياح",
     "Clothing & Bags", 38.0, None),
]


async def get_or_create_categories(session: AsyncSession) -> dict:
    """Create the taxonomy if missing. Returns {english_name: Category}."""
    created = {}

    # Two passes: roots first, then children (so parents exist)
    for pass_num in (1, 2):
        for name_en, name_ar, parent_en, listing_type in CATEGORIES:
            is_root = parent_en is None
            if (pass_num == 1) != is_root:
                continue

            existing = await session.execute(
                select(Category).where(Category.name == name_en)
            )
            cat = existing.scalar_one_or_none()

            if cat is None:
                parent_id = created[parent_en].id if parent_en else None
                cat = Category(
                    name=name_en,
                    name_en=name_en,
                    name_ar=name_ar,
                    parent_category_id=parent_id,
                    listing_type=listing_type,
                )
                session.add(cat)
                await session.flush()
                logger.info(f"  + category: {name_en} / {name_ar}")
            created[name_en] = cat

    return created


async def seed(clear: bool = False):
    async with AsyncSession(engine) as session:
        # ── Optional cleanup ─────────────────────────────────────
        if clear:
            logger.info("Removing previously seeded diverse products...")
            res = await session.execute(
                text("SELECT id FROM global_items WHERE description LIKE :tag"),
                {"tag": f"%{SEED_TAG}%"},
            )
            ids = [row[0] for row in res]
            if ids:
                await session.execute(
                    text("DELETE FROM market_items WHERE item_id = ANY(:ids)"),
                    {"ids": ids},
                )
                await session.execute(
                    text("DELETE FROM product_images WHERE global_item_id = ANY(:ids)"),
                    {"ids": ids},
                )
                await session.execute(
                    text("DELETE FROM global_items WHERE id = ANY(:ids)"),
                    {"ids": ids},
                )
                await session.commit()
            logger.info(f"  removed {len(ids)} products\n")
            if clear:
                return

        # ── Find a market to attach items to ─────────────────────
        market_res = await session.execute(select(Market).limit(1))
        market = market_res.scalar_one_or_none()
        if market is None:
            logger.error("No market found. Run the main seed script first.")
            sys.exit(1)
        logger.info(f"Attaching products to market: {market.name}\n")

        # ── Ensure categories ────────────────────────────────────
        logger.info("Ensuring category taxonomy...")
        cats = await get_or_create_categories(session)
        await session.commit()
        logger.info("")

        # ── Load embedding model ─────────────────────────────────
        logger.info("Loading embedding model...")
        embedding_service.load_model()
        logger.info("")

        # ── Insert products ──────────────────────────────────────
        logger.info(f"Inserting {len(PRODUCTS)} diverse products...")
        inserted = 0
        skipped = 0

        for name_ar, name_en, desc_ar, cat_name, price, barcode in PRODUCTS:
            # Skip if already present
            existing = await session.execute(
                select(GlobalItem).where(GlobalItem.name == name_ar)
            )
            if existing.scalar_one_or_none() is not None:
                skipped += 1
                continue

            cat = cats.get(cat_name)
            if cat is None:
                logger.warning(f"  ! unknown category '{cat_name}' for {name_ar}")
                continue

            # search_terms: name + description + category names
            # (matches the enrichment pattern used elsewhere in the pipeline)
            search_terms = " ".join([
                name_ar, name_en, desc_ar,
                cat.name_ar or "", cat.name_en or "", cat.name,
            ]).strip()

            # Embed the enriched text
            embed_input = f"{name_ar}. {desc_ar}. {cat.name_ar} {cat.name_en}"
            try:
                vec = await embedding_service.encode_text_async(
                    embed_input, text_type="document"
                )
                embedding = vec.tolist() if vec is not None else None
            except Exception as e:
                logger.warning(f"  ! embedding failed for {name_ar}: {e}")
                embedding = None

            gi = GlobalItem(
                name=name_ar,
                name_ar=name_ar,
                name_en=name_en,
                description=f"{desc_ar} {SEED_TAG}",
                description_ar=desc_ar,
                description_en=None,
                barcode=barcode,
                listing_type="product",
                attributes={},
                category_id=cat.id,
                text_embedding=embedding,
                search_terms=search_terms,
            )
            session.add(gi)
            await session.flush()

            mi = MarketItem(
                market_id=market.id,
                item_id=gi.id,
                stock_count=10,
                status=True,
                price=price,
            )
            session.add(mi)
            inserted += 1

            if inserted % 10 == 0:
                await session.commit()
                logger.info(f"  ... {inserted} inserted")

        await session.commit()
        logger.info(f"\nDone. Inserted {inserted}, skipped {skipped} (already existed).")

        # ── Summary by category ──────────────────────────────────
        logger.info("\nCatalog now contains:")
        res = await session.execute(text("""
            SELECT c.name, COUNT(gi.id) AS n
            FROM categories c
            LEFT JOIN global_items gi ON gi.category_id = c.id
            GROUP BY c.name
            HAVING COUNT(gi.id) > 0
            ORDER BY n DESC
        """))
        for row in res:
            logger.info(f"  {row.name:32s} {row.n}")


def main():
    ap = argparse.ArgumentParser(description="Seed diverse products for benchmarking")
    ap.add_argument("--clear", action="store_true",
                    help="Remove previously seeded diverse products and exit")
    args = ap.parse_args()
    asyncio.run(seed(clear=args.clear))


if __name__ == "__main__":
    main()
