"""
Lamba taxonomy — the single source of truth for categories and store types.

Code everywhere refers to the stable `slug`, never to display names. Renaming a
category is a one-line edit here followed by `python -m app.taxonomy_sync`.

Rules (checked at import time, see _validate):
- slugs are unique, lowercase snake_case
- the tree is exactly two levels: sections (parent=None) and categories
- every parent slug exists and is a section
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryDef:
    slug: str
    name_ar: str
    name_en: str
    parent: str | None = None  # slug of the parent section; None = section itself
    listing_type: str = "product"  # "product" | "service"
    icon: str | None = None  # Ionicons name, used for sections
    sort_order: int = 0


@dataclass(frozen=True)
class StoreTypeDef:
    slug: str
    name_ar: str
    name_en: str
    listing_type: str  # "product" | "service"
    icon: str


def _section(slug, name_ar, name_en, icon, order, listing_type="product"):
    return CategoryDef(slug, name_ar, name_en, None, listing_type, icon, order)


def _children(parent, listing_type, items):
    return [
        CategoryDef(slug, name_ar, name_en, parent, listing_type, None, (i + 1) * 10)
        for i, (slug, name_ar, name_en) in enumerate(items)
    ]


CATEGORIES: list[CategoryDef] = [
    # ── Sections ──────────────────────────────────────────────────────────
    _section("grocery", "البقالة", "Grocery", "cart-outline", 10),
    _section("beverages", "المشروبات", "Beverages", "cafe-outline", 20),
    _section("sweets_snacks", "الحلويات والتسالي", "Sweets & Snacks", "ice-cream-outline", 30),
    _section("baby", "الأطفال", "Baby", "happy-outline", 40),
    _section("personal_care", "العناية الشخصية", "Personal Care", "sparkles-outline", 50),
    _section("health", "الصحة", "Health", "medkit-outline", 60),
    _section("household", "المنظفات والمنزل", "Household", "home-outline", 70),
    _section("kitchen", "المطبخ والمائدة", "Kitchen & Dining", "restaurant-outline", 80),
    _section("electronics", "الإلكترونيات", "Electronics", "phone-portrait-outline", 90),
    _section("other_retail", "أقسام أخرى", "Other Retail", "pricetag-outline", 100),
    _section("services", "الخدمات", "Services", "construct-outline", 110, listing_type="service"),

    # ── Categories ────────────────────────────────────────────────────────
    *_children("grocery", "product", [
        ("fruits_vegetables", "خضار وفواكه", "Fruits & Vegetables"),
        ("dairy_eggs", "ألبان وأجبان وبيض", "Dairy, Cheese & Eggs"),
        ("meat_poultry_fish", "لحوم ودواجن وأسماك", "Meat, Poultry & Fish"),
        ("bakery", "مخبوزات", "Bakery"),
        ("frozen_food", "مجمدات", "Frozen Food"),
        ("pantry_staples", "مواد تموينية", "Pantry Staples"),
        ("canned_jarred", "معلبات ومحفوظات", "Canned & Jarred"),
        ("spices_sauces", "بهارات وصلصات", "Spices & Sauces"),
    ]),
    *_children("beverages", "product", [
        ("drinks_juices", "مشروبات وعصائر", "Drinks & Juices"),
        ("coffee_tea", "قهوة وشاي", "Coffee & Tea"),
    ]),
    *_children("sweets_snacks", "product", [
        ("chocolate_sweets", "شوكولاتة وحلويات", "Chocolate & Sweets"),
        ("chips_nuts", "شيبس ومكسرات", "Chips & Nuts"),
        ("biscuits_cakes", "بسكويت وكيك", "Biscuits & Cakes"),
    ]),
    *_children("baby", "product", [
        ("diapers_wipes", "حفاضات ومناديل أطفال", "Diapers & Wipes"),
        ("baby_food", "حليب وطعام أطفال", "Formula & Baby Food"),
        ("baby_care", "عناية الطفل", "Baby Care"),
    ]),
    *_children("personal_care", "product", [
        ("hair_care", "العناية بالشعر", "Hair Care"),
        ("oral_care", "العناية بالفم والأسنان", "Oral Care"),
        ("skin_body_care", "العناية بالبشرة والجسم", "Skin & Body Care"),
        ("shaving", "الحلاقة", "Shaving & Grooming"),
        ("makeup_fragrance", "مكياج وعطور", "Makeup & Fragrance"),
        ("feminine_care", "العناية النسائية", "Feminine Care"),
    ]),
    *_children("health", "product", [
        ("health_first_aid", "مستلزمات صحية وإسعافات أولية", "Health & First Aid"),
    ]),
    *_children("household", "product", [
        ("detergents", "منظفات", "Detergents & Cleaners"),
        ("cleaning_tools", "أدوات تنظيف", "Cleaning Tools"),
        ("tissues_paper", "محارم وورقيات", "Tissues & Paper"),
        ("bags_disposables", "أكياس ومستهلكات", "Bags & Disposables"),
        ("insecticides", "مبيدات حشرية", "Insecticides"),
    ]),
    *_children("kitchen", "product", [
        ("cookware", "أواني الطبخ", "Cookware"),
        ("tableware", "أدوات المائدة والتقديم", "Tableware & Serveware"),
        ("home_essentials", "أدوات منزلية", "Home Essentials"),
    ]),
    *_children("electronics", "product", [
        ("mobiles_accessories", "هواتف وإكسسوارات", "Mobiles & Accessories"),
        ("home_appliances", "أجهزة منزلية", "Home Appliances"),
        ("batteries_electrical", "بطاريات وكهربائيات", "Batteries & Electrical"),
    ]),
    *_children("other_retail", "product", [
        ("stationery", "قرطاسية", "Stationery"),
        ("pet_supplies", "مستلزمات الحيوانات الأليفة", "Pet Supplies"),
        ("clothing", "ملابس وأحذية وحقائب", "Clothing, Shoes & Bags"),
        ("building_materials", "مواد بناء وعدد", "Building Materials & Tools"),
        ("auto_parts", "قطع وإكسسوارات السيارات", "Auto Parts & Accessories"),
    ]),
    *_children("services", "service", [
        ("beauty_services", "خدمات التجميل", "Beauty Services"),
        ("car_services", "صيانة السيارات", "Car Maintenance"),
        ("home_services", "خدمات منزلية وصيانة", "Home Services & Repair"),
        ("education", "تعليم ودروس", "Education & Tutoring"),
    ]),
]


STORE_TYPES: list[StoreTypeDef] = [
    StoreTypeDef("supermarket", "سوبرماركت/بقالة", "Supermarket / Grocery", "product", "cart-outline"),
    StoreTypeDef("bakery", "مخبز", "Bakery", "product", "restaurant-outline"),
    StoreTypeDef("butcher", "ملحمة", "Butcher", "product", "flame-outline"),
    StoreTypeDef("greengrocer", "خضار وفواكه", "Fruits & Vegetables", "product", "nutrition-outline"),
    StoreTypeDef("pharmacy", "صيدلية", "Pharmacy", "product", "medkit-outline"),
    StoreTypeDef("phones_electronics", "هواتف وإلكترونيات", "Phones & Electronics", "product", "phone-portrait-outline"),
    StoreTypeDef("housewares", "أدوات منزلية", "Housewares", "product", "home-outline"),
    StoreTypeDef("building_materials", "مواد بناء", "Building Materials", "product", "hammer-outline"),
    StoreTypeDef("clothing", "ملابس", "Clothing", "product", "shirt-outline"),
    StoreTypeDef("auto_parts", "قطع سيارات", "Auto Parts", "product", "cog-outline"),
    StoreTypeDef("beauty_salon", "صالون تجميل", "Beauty Salon", "service", "cut-outline"),
    StoreTypeDef("car_service", "صيانة سيارات", "Car Service", "service", "car-outline"),
    StoreTypeDef("home_services", "خدمات منزلية", "Home Services", "service", "construct-outline"),
    StoreTypeDef("education_center", "مركز تعليمي", "Education Center", "service", "school-outline"),
]


CATEGORY_BY_SLUG: dict[str, CategoryDef] = {c.slug: c for c in CATEGORIES}
STORE_TYPE_BY_SLUG: dict[str, StoreTypeDef] = {s.slug: s for s in STORE_TYPES}
LEAF_CATEGORIES: list[CategoryDef] = [c for c in CATEGORIES if c.parent is not None]


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_LISTING_TYPES = {"product", "service"}


def _validate() -> None:
    errors: list[str] = []

    def check_unique(kind, slugs):
        seen = set()
        for s in slugs:
            if s in seen:
                errors.append(f"duplicate {kind} slug: {s}")
            seen.add(s)

    check_unique("category", [c.slug for c in CATEGORIES])
    check_unique("store type", [s.slug for s in STORE_TYPES])

    for c in CATEGORIES:
        if not _SLUG_RE.match(c.slug):
            errors.append(f"bad category slug: {c.slug!r}")
        if c.listing_type not in _LISTING_TYPES:
            errors.append(f"{c.slug}: bad listing_type {c.listing_type!r}")
        if not c.name_ar.strip() or not c.name_en.strip():
            errors.append(f"{c.slug}: missing name")
        if c.parent is not None:
            parent = CATEGORY_BY_SLUG.get(c.parent)
            if parent is None:
                errors.append(f"{c.slug}: unknown parent {c.parent!r}")
            elif parent.parent is not None:
                errors.append(f"{c.slug}: parent {c.parent!r} is not a section (max two levels)")
            elif parent.listing_type != c.listing_type:
                errors.append(f"{c.slug}: listing_type differs from its section")

    sections_with_children = {c.parent for c in LEAF_CATEGORIES}
    for c in CATEGORIES:
        if c.parent is None and c.slug not in sections_with_children:
            errors.append(f"section {c.slug!r} has no categories")

    for s in STORE_TYPES:
        if not _SLUG_RE.match(s.slug):
            errors.append(f"bad store type slug: {s.slug!r}")
        if s.listing_type not in _LISTING_TYPES:
            errors.append(f"store type {s.slug}: bad listing_type {s.listing_type!r}")

    if errors:
        raise ValueError("Invalid taxonomy:\n  " + "\n  ".join(errors))


_validate()
