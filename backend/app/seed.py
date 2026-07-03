"""
Seed Data Script — Populates the database with sample markets and products using the new multi-branch and structured categories.

Run: python -m app.seed
(from the backend/ directory with all services running)
"""

import asyncio
import uuid
import logging
from datetime import datetime, timezone

from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.database import async_session, engine, Base
from app.models.user import User
from app.models.market import Market
from app.models.category import Category
from app.models.global_item import GlobalItem
from app.models.product_image import ProductImage
from app.models.market_item import MarketItem
from app.services.auth import hash_password
from app.services.embedding import embedding_service
from app.services.indexer import IndexerService
from app.es_client import init_es_client, close_es_client
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Merchant Accounts (22 merchants, one per market) ────────────
MERCHANTS = [
    {"email": f"merchant{i}@shop.com", "password": "merchant123"}
    for i in range(1, 23)
]

CUSTOMERS = [
    {"email": "customer@lamba.com", "password": "customer123"},
]

# ── 22 Markets in the As-Salt / Balqa region, Jordan ────────────
MARKETS = [
    {
        "merchant_email": "merchant1@shop.com",
        "name": "Ali's Corner Market",
        "business_nature": "Roastery",
        "address": "Sport City, As-Salt, Balqa, Jordan",
        "latitude": 32.0385, "longitude": 35.7275,
        "phone": "+962-79-123-4567",
        "operating_hours": {"Mon-Thu": "08:00-22:00", "Fri": "13:00-23:00", "Sat-Sun": "08:00-22:00"},
        "employee_directory": [{"name": "Ahmad", "role": "Manager", "contact": "+962-79-111-2222"}],
    },
    {
        "merchant_email": "merchant2@shop.com",
        "name": "Sara's Organic Garden",
        "business_nature": "Grocery",
        "address": "University Street, As-Salt, Balqa, Jordan",
        "latitude": 32.0240, "longitude": 35.7168,
        "phone": "+962-79-987-6543",
        "operating_hours": {"Mon-Thu": "09:00-21:00", "Fri": "10:00-22:00", "Sat": "09:00-21:00", "Sun": "Closed"},
        "employee_directory": [{"name": "Rania", "role": "Store Specialist", "contact": "+962-79-555-6666"}],
    },
    {
        "merchant_email": "merchant3@shop.com",
        "name": "بقالة الحي القديم",
        "business_nature": "Grocery",
        "address": "Old Town, As-Salt, Balqa, Jordan",
        "latitude": 32.0392, "longitude": 35.7261,
        "phone": "+962-79-200-0001",
        "operating_hours": {"Mon-Sat": "07:00-23:00", "Sun": "08:00-20:00"},
        "employee_directory": [{"name": "خالد", "role": "صاحب المحل", "contact": "+962-79-200-0002"}],
    },
    {
        "merchant_email": "merchant4@shop.com",
        "name": "سوبرماركت الأمل",
        "business_nature": "Supermarket",
        "address": "Al-Amal Street, As-Salt, Balqa, Jordan",
        "latitude": 32.0320, "longitude": 35.7330,
        "phone": "+962-79-300-0001",
        "operating_hours": {"Mon-Sat": "08:00-22:00", "Sun": "10:00-18:00"},
        "employee_directory": [{"name": "محمد", "role": "مدير", "contact": "+962-79-300-0002"}],
    },
    {
        "merchant_email": "merchant5@shop.com",
        "name": "Fresh Valley Market",
        "business_nature": "Grocery",
        "address": "Valley Road, As-Salt, Balqa, Jordan",
        "latitude": 32.0410, "longitude": 35.7200,
        "phone": "+962-79-400-0001",
        "operating_hours": {"Mon-Sat": "07:30-21:30", "Sun": "09:00-19:00"},
        "employee_directory": [{"name": "Omar", "role": "Manager", "contact": "+962-79-400-0002"}],
    },
    {
        "merchant_email": "merchant6@shop.com",
        "name": "محمصة النكهة الذهبية",
        "business_nature": "Roastery",
        "address": "Al-Manara Circle, As-Salt, Balqa, Jordan",
        "latitude": 32.0365, "longitude": 35.7310,
        "phone": "+962-79-500-0001",
        "operating_hours": {"Mon-Sat": "06:00-22:00", "Sun": "08:00-20:00"},
        "employee_directory": [{"name": "يوسف", "role": "محمّص", "contact": "+962-79-500-0002"}],
    },
    {
        "merchant_email": "merchant7@shop.com",
        "name": "Herbal Essence Shop",
        "business_nature": "Health Store",
        "address": "Green Hill, As-Salt, Balqa, Jordan",
        "latitude": 32.0280, "longitude": 35.7140,
        "phone": "+962-79-600-0001",
        "operating_hours": {"Mon-Fri": "09:00-20:00", "Sat": "10:00-18:00", "Sun": "Closed"},
        "employee_directory": [{"name": "Layla", "role": "Herbalist", "contact": "+962-79-600-0002"}],
    },
    {
        "merchant_email": "merchant8@shop.com",
        "name": "دكان أبو سمير",
        "business_nature": "Grocery",
        "address": "Al-Khader Street, As-Salt, Balqa, Jordan",
        "latitude": 32.0345, "longitude": 35.7250,
        "phone": "+962-79-700-0001",
        "operating_hours": {"Mon-Sun": "06:00-00:00"},
        "employee_directory": [{"name": "سمير", "role": "صاحب", "contact": "+962-79-700-0002"}],
    },
    {
        "merchant_email": "merchant9@shop.com",
        "name": "Spice Route Bazaar",
        "business_nature": "Spice Shop",
        "address": "Ottoman Quarter, As-Salt, Balqa, Jordan",
        "latitude": 32.0398, "longitude": 35.7270,
        "phone": "+962-79-800-0001",
        "operating_hours": {"Mon-Sat": "08:00-21:00", "Sun": "10:00-17:00"},
        "employee_directory": [{"name": "Tariq", "role": "Owner", "contact": "+962-79-800-0002"}],
    },
    {
        "merchant_email": "merchant10@shop.com",
        "name": "مركز السلطي للتسوق",
        "business_nature": "Supermarket",
        "address": "Main Street, As-Salt, Balqa, Jordan",
        "latitude": 32.0370, "longitude": 35.7290,
        "phone": "+962-79-900-0001",
        "operating_hours": {"Mon-Sat": "07:00-23:00", "Sun": "09:00-21:00"},
        "employee_directory": [{"name": "عبدالله", "role": "مدير عام", "contact": "+962-79-900-0002"}],
    },
    {
        "merchant_email": "merchant11@shop.com",
        "name": "Golden Harvest Store",
        "business_nature": "Grocery",
        "address": "Harvest Lane, As-Salt, Balqa, Jordan",
        "latitude": 32.0300, "longitude": 35.7180,
        "phone": "+962-79-101-0001",
        "operating_hours": {"Mon-Sat": "08:00-22:00", "Sun": "09:00-20:00"},
        "employee_directory": [{"name": "Nadia", "role": "Manager", "contact": "+962-79-101-0002"}],
    },
    {
        "merchant_email": "merchant12@shop.com",
        "name": "بيت العطارة",
        "business_nature": "Herbalist",
        "address": "Al-Hamam Street, As-Salt, Balqa, Jordan",
        "latitude": 32.0388, "longitude": 35.7255,
        "phone": "+962-79-102-0001",
        "operating_hours": {"Mon-Sat": "09:00-21:00", "Sun": "10:00-18:00"},
        "employee_directory": [{"name": "أبو نبيل", "role": "عطّار", "contact": "+962-79-102-0002"}],
    },
    {
        "merchant_email": "merchant13@shop.com",
        "name": "Mediterranean Delights",
        "business_nature": "Gourmet",
        "address": "Citadel Hill, As-Salt, Balqa, Jordan",
        "latitude": 32.0402, "longitude": 35.7268,
        "phone": "+962-79-103-0001",
        "operating_hours": {"Mon-Sat": "10:00-22:00", "Sun": "12:00-20:00"},
        "employee_directory": [{"name": "Georges", "role": "Chef-Owner", "contact": "+962-79-103-0002"}],
    },
    {
        "merchant_email": "merchant14@shop.com",
        "name": "تموينات الخير",
        "business_nature": "Grocery",
        "address": "Al-Khair District, As-Salt, Balqa, Jordan",
        "latitude": 32.0335, "longitude": 35.7320,
        "phone": "+962-79-104-0001",
        "operating_hours": {"Mon-Sat": "07:00-22:00", "Sun": "08:00-20:00"},
        "employee_directory": [{"name": "حسن", "role": "مدير", "contact": "+962-79-104-0002"}],
    },
    {
        "merchant_email": "merchant15@shop.com",
        "name": "Olive Tree Market",
        "business_nature": "Organic",
        "address": "Olive Hill Road, As-Salt, Balqa, Jordan",
        "latitude": 32.0290, "longitude": 35.7150,
        "phone": "+962-79-105-0001",
        "operating_hours": {"Mon-Sat": "08:00-20:00", "Sun": "10:00-18:00"},
        "employee_directory": [{"name": "Hana", "role": "Owner", "contact": "+962-79-105-0002"}],
    },
    {
        "merchant_email": "merchant16@shop.com",
        "name": "محل أبو العز للبهارات",
        "business_nature": "Spice Shop",
        "address": "Souk Al-Salt, As-Salt, Balqa, Jordan",
        "latitude": 32.0395, "longitude": 35.7265,
        "phone": "+962-79-106-0001",
        "operating_hours": {"Mon-Sat": "08:00-21:00", "Sun": "09:00-17:00"},
        "employee_directory": [{"name": "أبو العز", "role": "بائع بهارات", "contact": "+962-79-106-0002"}],
    },
    {
        "merchant_email": "merchant17@shop.com",
        "name": "Summit Health Foods",
        "business_nature": "Health Store",
        "address": "Summit Avenue, As-Salt, Balqa, Jordan",
        "latitude": 32.0415, "longitude": 35.7215,
        "phone": "+962-79-107-0001",
        "operating_hours": {"Mon-Fri": "09:00-21:00", "Sat": "10:00-20:00", "Sun": "Closed"},
        "employee_directory": [{"name": "Dana", "role": "Nutritionist", "contact": "+962-79-107-0002"}],
    },
    {
        "merchant_email": "merchant18@shop.com",
        "name": "سوبرماركت الوادي",
        "business_nature": "Supermarket",
        "address": "Wadi Shu'aib, As-Salt, Balqa, Jordan",
        "latitude": 32.0260, "longitude": 35.7135,
        "phone": "+962-79-108-0001",
        "operating_hours": {"Mon-Sat": "07:00-23:00", "Sun": "08:00-22:00"},
        "employee_directory": [{"name": "فراس", "role": "مدير", "contact": "+962-79-108-0002"}],
    },
    {
        "merchant_email": "merchant19@shop.com",
        "name": "Royal Roastery",
        "business_nature": "Roastery",
        "address": "King Hussein Street, As-Salt, Balqa, Jordan",
        "latitude": 32.0380, "longitude": 35.7280,
        "phone": "+962-79-109-0001",
        "operating_hours": {"Mon-Sat": "06:00-22:00", "Sun": "07:00-20:00"},
        "employee_directory": [{"name": "Zaid", "role": "Head Roaster", "contact": "+962-79-109-0002"}],
    },
    {
        "merchant_email": "merchant20@shop.com",
        "name": "مخبز ومعجنات السلط",
        "business_nature": "Bakery",
        "address": "Al-Maydan, As-Salt, Balqa, Jordan",
        "latitude": 32.0372, "longitude": 35.7295,
        "phone": "+962-79-110-0001",
        "operating_hours": {"Mon-Sat": "05:00-21:00", "Sun": "06:00-18:00"},
        "employee_directory": [{"name": "أبو بكر", "role": "خباز", "contact": "+962-79-110-0002"}],
    },
    {
        "merchant_email": "merchant21@shop.com",
        "name": "Cedar Valley Provisions",
        "business_nature": "Grocery",
        "address": "Cedar Street, As-Salt, Balqa, Jordan",
        "latitude": 32.0310, "longitude": 35.7190,
        "phone": "+962-79-111-0001",
        "operating_hours": {"Mon-Sat": "08:00-22:00", "Sun": "09:00-20:00"},
        "employee_directory": [{"name": "Sami", "role": "Manager", "contact": "+962-79-111-0002"}],
    },
    {
        "merchant_email": "merchant22@shop.com",
        "name": "محل العسل الطبيعي",
        "business_nature": "Specialty",
        "address": "Honey Lane, As-Salt, Balqa, Jordan",
        "latitude": 32.0355, "longitude": 35.7240,
        "phone": "+962-79-112-0001",
        "operating_hours": {"Mon-Sat": "09:00-20:00", "Sun": "10:00-17:00"},
        "employee_directory": [{"name": "ماجد", "role": "صاحب", "contact": "+962-79-112-0002"}],
    },
]

# ── Product Catalog: 25 products per market (550 total MarketItems) ──
# Products mix Arabic and English names to test bilingual search.
# Shared global items appear across multiple markets with different prices/stock.

def _build_products():
    """Build a comprehensive product catalog with 25 products per market."""
    all_products = []

    # ── Market 1: Ali's Corner Market (Roastery) ──────────────
    m1 = "Ali's Corner Market"
    all_products += [
        {"market_name": m1, "name": "Green Tea - Matcha Organic", "description": "Premium Japanese matcha green tea powder, ceremonial grade.", "price": 45.00, "category": "Tea", "in_stock": True, "stock_count": 15},
        {"market_name": m1, "name": "Arabic Coffee - Dark Roast", "description": "Traditional Saudi Arabic coffee, dark roasted with cardamom.", "price": 35.00, "category": "Coffee", "in_stock": True, "stock_count": 22},
        {"market_name": m1, "name": "Honey - Sidr Premium", "description": "Pure Yemeni Sidr honey, raw and unfiltered.", "price": 120.00, "category": "Honey", "in_stock": True, "stock_count": 8},
        {"market_name": m1, "name": "Dates - Medjool Premium", "description": "Large, soft Medjool dates from Al-Madinah.", "price": 55.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 30},
        {"market_name": m1, "name": "Olive Oil - Extra Virgin", "description": "Cold-pressed extra virgin olive oil from Jordan.", "price": 40.00, "category": "Oils", "in_stock": False, "stock_count": 0},
        {"market_name": m1, "name": "Saffron - Iranian Grade 1", "description": "Premium Iranian saffron threads, intense aroma.", "price": 85.00, "category": "Spices", "in_stock": True, "stock_count": 12},
        {"market_name": m1, "name": "شاي أخضر صيني", "description": "شاي أخضر فاخر من الصين، طعم منعش وخفيف", "price": 18.00, "category": "Tea", "in_stock": True, "stock_count": 25},
        {"market_name": m1, "name": "قهوة تركية فاخرة", "description": "قهوة تركية محمصة بعناية، ناعمة ومميزة", "price": 28.00, "category": "Coffee", "in_stock": True, "stock_count": 18},
        {"market_name": m1, "name": "Turkish Coffee - Medium", "description": "Medium roast Turkish coffee, finely ground.", "price": 25.00, "category": "Coffee", "in_stock": True, "stock_count": 20},
        {"market_name": m1, "name": "Earl Grey Tea", "description": "Classic Earl Grey with bergamot essence.", "price": 22.00, "category": "Tea", "in_stock": True, "stock_count": 30},
        {"market_name": m1, "name": "بهارات مشكلة", "description": "خلطة بهارات مشكلة للطبخ العربي التقليدي", "price": 12.00, "category": "Spices", "in_stock": True, "stock_count": 40},
        {"market_name": m1, "name": "Cardamom Pods - Green", "description": "Whole green cardamom pods from Guatemala.", "price": 48.00, "category": "Spices", "in_stock": True, "stock_count": 10},
        {"market_name": m1, "name": "هيل أخضر", "description": "هيل أخضر ممتاز، نكهة قوية وعطرة", "price": 50.00, "category": "Spices", "in_stock": True, "stock_count": 8},
        {"market_name": m1, "name": "Pistachios - Roasted Salted", "description": "Premium Antep pistachios, roasted and salted.", "price": 65.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 14},
        {"market_name": m1, "name": "فستق حلبي محمص", "description": "فستق حلبي محمص بالملح، حبات كبيرة ولذيذة", "price": 70.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 11},
        {"market_name": m1, "name": "Cashews - Raw Organic", "description": "Organic raw cashews, perfect for snacking.", "price": 42.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 20},
        {"market_name": m1, "name": "عسل ربيعي", "description": "عسل ربيعي طبيعي من الأردن، صافي 100%", "price": 75.00, "category": "Honey", "in_stock": True, "stock_count": 6},
        {"market_name": m1, "name": "Black Seed Oil", "description": "Pure cold-pressed black seed oil (Nigella sativa).", "price": 38.00, "category": "Oils", "in_stock": True, "stock_count": 16},
        {"market_name": m1, "name": "زيت حبة البركة", "description": "زيت حبة البركة الأصلي، معصور على البارد", "price": 40.00, "category": "Oils", "in_stock": True, "stock_count": 12},
        {"market_name": m1, "name": "Cinnamon Sticks - Ceylon", "description": "True Ceylon cinnamon sticks, delicate and sweet.", "price": 30.00, "category": "Spices", "in_stock": True, "stock_count": 22},
        {"market_name": m1, "name": "قرفة سيلانية", "description": "عيدان قرفة سيلانية أصلية، نكهة حلوة ورائعة", "price": 32.00, "category": "Spices", "in_stock": True, "stock_count": 18},
        {"market_name": m1, "name": "Sumac - Ground", "description": "Ground sumac with tangy lemony flavor.", "price": 15.00, "category": "Spices", "in_stock": True, "stock_count": 35},
        {"market_name": m1, "name": "سماق مطحون", "description": "سماق مطحون طازج للسلطات والمشاوي", "price": 14.00, "category": "Spices", "in_stock": True, "stock_count": 30},
        {"market_name": m1, "name": "Tahini - Sesame Paste", "description": "Pure sesame tahini, smooth and creamy.", "price": 20.00, "category": "Spreads", "in_stock": True, "stock_count": 25},
        {"market_name": m1, "name": "طحينة فاخرة", "description": "طحينة سمسم فاخرة، ناعمة ولذيذة", "price": 18.00, "category": "Spreads", "in_stock": True, "stock_count": 28},
    ]

    # ── Market 2: Sara's Organic Garden ───────────────────────
    m2 = "Sara's Organic Garden"
    all_products += [
        {"market_name": m2, "name": "Chamomile Tea - Organic", "description": "Soothing organic chamomile herbal tea.", "price": 28.00, "category": "Tea", "in_stock": True, "stock_count": 20},
        {"market_name": m2, "name": "Lavender Essential Oil", "description": "Pure lavender essential oil for aromatherapy.", "price": 35.00, "category": "Essential Oils", "in_stock": True, "stock_count": 14},
        {"market_name": m2, "name": "Chia Seeds - Organic", "description": "Organic chia seeds, high in omega-3 and fiber.", "price": 22.00, "category": "Seeds", "in_stock": True, "stock_count": 40},
        {"market_name": m2, "name": "Coconut Oil - Raw Virgin", "description": "Cold-pressed raw virgin coconut oil.", "price": 30.00, "category": "Oils", "in_stock": True, "stock_count": 18},
        {"market_name": m2, "name": "Turmeric Powder - Organic", "description": "Ground organic turmeric with high curcumin.", "price": 18.00, "category": "Spices", "in_stock": True, "stock_count": 25},
        {"market_name": m2, "name": "Almond Butter - Raw", "description": "Raw organic almond butter, no added sugar.", "price": 42.00, "category": "Spreads", "in_stock": False, "stock_count": 0},
        {"market_name": m2, "name": "شاي بابونج عضوي", "description": "شاي بابونج عضوي مهدئ للأعصاب", "price": 25.00, "category": "Tea", "in_stock": True, "stock_count": 22},
        {"market_name": m2, "name": "بذور كتان عضوية", "description": "بذور كتان عضوية غنية بالأوميغا-3", "price": 15.00, "category": "Seeds", "in_stock": True, "stock_count": 35},
        {"market_name": m2, "name": "Flax Seeds - Golden", "description": "Golden flax seeds, rich in fiber and lignans.", "price": 16.00, "category": "Seeds", "in_stock": True, "stock_count": 30},
        {"market_name": m2, "name": "Hemp Seeds - Organic", "description": "Organic hemp hearts, complete protein source.", "price": 28.00, "category": "Seeds", "in_stock": True, "stock_count": 20},
        {"market_name": m2, "name": "زيت جوز هند بكر", "description": "زيت جوز هند بكر عضوي للطبخ والعناية بالبشرة", "price": 32.00, "category": "Oils", "in_stock": True, "stock_count": 15},
        {"market_name": m2, "name": "Avocado Oil - Cold Pressed", "description": "Cold-pressed avocado oil, rich in oleic acid.", "price": 38.00, "category": "Oils", "in_stock": True, "stock_count": 12},
        {"market_name": m2, "name": "كركم عضوي مطحون", "description": "كركم عضوي مطحون مضاد للالتهابات", "price": 20.00, "category": "Spices", "in_stock": True, "stock_count": 28},
        {"market_name": m2, "name": "Matcha Powder - Culinary", "description": "Culinary grade matcha for lattes and baking.", "price": 35.00, "category": "Tea", "in_stock": True, "stock_count": 16},
        {"market_name": m2, "name": "شاي أعشاب مهدئ", "description": "خلطة شاي أعشاب مهدئة للنوم والاسترخاء", "price": 20.00, "category": "Tea", "in_stock": True, "stock_count": 18},
        {"market_name": m2, "name": "Pumpkin Seeds - Raw", "description": "Raw pumpkin seeds, rich in zinc and magnesium.", "price": 14.00, "category": "Seeds", "in_stock": True, "stock_count": 45},
        {"market_name": m2, "name": "زبدة لوز عضوية", "description": "زبدة لوز عضوية بدون سكر مضاف", "price": 44.00, "category": "Spreads", "in_stock": True, "stock_count": 10},
        {"market_name": m2, "name": "Peanut Butter - Natural", "description": "Natural peanut butter with no additives.", "price": 18.00, "category": "Spreads", "in_stock": True, "stock_count": 30},
        {"market_name": m2, "name": "Tea Tree Essential Oil", "description": "Pure tea tree oil for skin and cleaning.", "price": 25.00, "category": "Essential Oils", "in_stock": True, "stock_count": 16},
        {"market_name": m2, "name": "زيت لافندر أصلي", "description": "زيت لافندر طبيعي للاسترخاء والعلاج العطري", "price": 38.00, "category": "Essential Oils", "in_stock": True, "stock_count": 10},
        {"market_name": m2, "name": "Rosemary Essential Oil", "description": "Pure rosemary oil for hair and focus.", "price": 22.00, "category": "Essential Oils", "in_stock": True, "stock_count": 14},
        {"market_name": m2, "name": "Honey - Wildflower Raw", "description": "Raw wildflower honey, unprocessed.", "price": 55.00, "category": "Honey", "in_stock": True, "stock_count": 12},
        {"market_name": m2, "name": "عسل أزهار برية", "description": "عسل أزهار برية طبيعي غير معالج", "price": 58.00, "category": "Honey", "in_stock": True, "stock_count": 9},
        {"market_name": m2, "name": "Spirulina Powder", "description": "Organic spirulina superfood powder.", "price": 32.00, "category": "Seeds", "in_stock": True, "stock_count": 14},
        {"market_name": m2, "name": "Quinoa - White Organic", "description": "Organic white quinoa, complete protein grain.", "price": 24.00, "category": "Seeds", "in_stock": True, "stock_count": 20},
    ]

    # ── Market 3: بقالة الحي القديم ────────────────────────────
    m3 = "بقالة الحي القديم"
    all_products += [
        {"market_name": m3, "name": "شاي أحمر تركي", "description": "شاي أحمر تركي أصلي بنكهة قوية ومميزة", "price": 15.00, "category": "Tea", "in_stock": True, "stock_count": 50},
        {"market_name": m3, "name": "قهوة عربية بالهيل", "description": "قهوة عربية تقليدية مع هيل طازج", "price": 30.00, "category": "Coffee", "in_stock": True, "stock_count": 25},
        {"market_name": m3, "name": "عسل جبلي أردني", "description": "عسل جبلي طبيعي من جبال عجلون", "price": 90.00, "category": "Honey", "in_stock": True, "stock_count": 5},
        {"market_name": m3, "name": "تمر عجوة المدينة", "description": "تمر عجوة المدينة المنورة الفاخر", "price": 80.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 15},
        {"market_name": m3, "name": "زيت زيتون بلدي", "description": "زيت زيتون بلدي معصور على البارد من الأردن", "price": 35.00, "category": "Oils", "in_stock": True, "stock_count": 20},
        {"market_name": m3, "name": "زعتر بلدي", "description": "خلطة زعتر بلدي أردني مع السمسم وزيت الزيتون", "price": 10.00, "category": "Spices", "in_stock": True, "stock_count": 60},
        {"market_name": m3, "name": "حلاوة طحينية", "description": "حلاوة طحينية بالفستق الحلبي", "price": 25.00, "category": "Spreads", "in_stock": True, "stock_count": 18},
        {"market_name": m3, "name": "مكسرات مشكلة", "description": "خلطة مكسرات مشكلة محمصة ومملحة", "price": 55.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 22},
        {"market_name": m3, "name": "لوز أخضر طازج", "description": "لوز أخضر طازج موسمي من فلسطين", "price": 40.00, "category": "Dried Fruits", "in_stock": False, "stock_count": 0},
        {"market_name": m3, "name": "ماء ورد", "description": "ماء ورد طبيعي للطبخ والحلويات", "price": 8.00, "category": "Essential Oils", "in_stock": True, "stock_count": 30},
        {"market_name": m3, "name": "ماء زهر", "description": "ماء زهر طبيعي للحلويات والمشروبات", "price": 8.00, "category": "Essential Oils", "in_stock": True, "stock_count": 28},
        {"market_name": m3, "name": "Black Tea - Ceylon", "description": "Premium Ceylon black tea, full-bodied flavor.", "price": 18.00, "category": "Tea", "in_stock": True, "stock_count": 35},
        {"market_name": m3, "name": "Instant Coffee - Nescafe", "description": "Nescafe Gold instant coffee, smooth blend.", "price": 22.00, "category": "Coffee", "in_stock": True, "stock_count": 40},
        {"market_name": m3, "name": "شاي ميرامية", "description": "شاي ميرامية (مريمية) بلدي طازج", "price": 12.00, "category": "Tea", "in_stock": True, "stock_count": 25},
        {"market_name": m3, "name": "فلفل أسود حب", "description": "فلفل أسود حب كامل، نكهة حارة ممتازة", "price": 18.00, "category": "Spices", "in_stock": True, "stock_count": 30},
        {"market_name": m3, "name": "كمون مطحون", "description": "كمون مطحون طازج للطبخ اليومي", "price": 8.00, "category": "Spices", "in_stock": True, "stock_count": 45},
        {"market_name": m3, "name": "بابريكا حلوة", "description": "بابريكا حلوة مجرية مدخنة", "price": 14.00, "category": "Spices", "in_stock": True, "stock_count": 20},
        {"market_name": m3, "name": "سمسم أبيض", "description": "سمسم أبيض محمص للزعتر والخبز", "price": 10.00, "category": "Seeds", "in_stock": True, "stock_count": 50},
        {"market_name": m3, "name": "دبس رمان", "description": "دبس رمان طبيعي كثيف للسلطات والمقبلات", "price": 15.00, "category": "Spreads", "in_stock": True, "stock_count": 20},
        {"market_name": m3, "name": "دبس تمر", "description": "دبس تمر طبيعي حلو ومغذي", "price": 12.00, "category": "Spreads", "in_stock": True, "stock_count": 25},
        {"market_name": m3, "name": "زنجبيل مطحون", "description": "زنجبيل مطحون طازج للشاي والطبخ", "price": 10.00, "category": "Spices", "in_stock": True, "stock_count": 35},
        {"market_name": m3, "name": "عسل سدر يمني", "description": "عسل سدر يمني أصلي فاخر", "price": 150.00, "category": "Honey", "in_stock": True, "stock_count": 3},
        {"market_name": m3, "name": "Sage Tea - Dried", "description": "Dried sage leaves for traditional herbal tea.", "price": 14.00, "category": "Tea", "in_stock": True, "stock_count": 20},
        {"market_name": m3, "name": "جوز هند مبشور", "description": "جوز هند مبشور ناعم للحلويات", "price": 8.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 30},
        {"market_name": m3, "name": "كاجو محمص", "description": "كاجو محمص ومملح، وجبة خفيفة لذيذة", "price": 45.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 16},
    ]

    # ── Market 4: سوبرماركت الأمل ──────────────────────────────
    m4 = "سوبرماركت الأمل"
    all_products += [
        {"market_name": m4, "name": "شاي ليبتون أصفر", "description": "شاي ليبتون الأصفر الكلاسيكي", "price": 12.00, "category": "Tea", "in_stock": True, "stock_count": 80},
        {"market_name": m4, "name": "Lipton Yellow Label Tea", "description": "Classic Lipton yellow label tea bags.", "price": 13.00, "category": "Tea", "in_stock": True, "stock_count": 70},
        {"market_name": m4, "name": "Nescafe Classic", "description": "Nescafe Classic instant coffee.", "price": 20.00, "category": "Coffee", "in_stock": True, "stock_count": 50},
        {"market_name": m4, "name": "نسكافيه كلاسيك", "description": "قهوة نسكافيه كلاسيك سريعة التحضير", "price": 20.00, "category": "Coffee", "in_stock": True, "stock_count": 45},
        {"market_name": m4, "name": "سكر أبيض", "description": "سكر أبيض ناعم للشاي والقهوة", "price": 5.00, "category": "Grocery", "in_stock": True, "stock_count": 100},
        {"market_name": m4, "name": "White Sugar", "description": "Fine white granulated sugar.", "price": 5.00, "category": "Grocery", "in_stock": True, "stock_count": 90},
        {"market_name": m4, "name": "أرز بسمتي", "description": "أرز بسمتي هندي فاخر طويل الحبة", "price": 18.00, "category": "Grocery", "in_stock": True, "stock_count": 60},
        {"market_name": m4, "name": "Basmati Rice - Premium", "description": "Premium long-grain Indian basmati rice.", "price": 19.00, "category": "Grocery", "in_stock": True, "stock_count": 55},
        {"market_name": m4, "name": "طحين أبيض", "description": "طحين أبيض متعدد الاستخدامات للخبز والمعجنات", "price": 4.00, "category": "Grocery", "in_stock": True, "stock_count": 80},
        {"market_name": m4, "name": "All-Purpose Flour", "description": "White all-purpose flour for baking.", "price": 4.50, "category": "Grocery", "in_stock": True, "stock_count": 75},
        {"market_name": m4, "name": "زيت دوار الشمس", "description": "زيت دوار الشمس النقي للقلي والطبخ", "price": 8.00, "category": "Oils", "in_stock": True, "stock_count": 40},
        {"market_name": m4, "name": "Sunflower Oil", "description": "Pure sunflower cooking oil.", "price": 8.50, "category": "Oils", "in_stock": True, "stock_count": 38},
        {"market_name": m4, "name": "حليب بودرة", "description": "حليب بودرة كامل الدسم", "price": 15.00, "category": "Grocery", "in_stock": True, "stock_count": 30},
        {"market_name": m4, "name": "Powdered Milk - Full Fat", "description": "Full fat powdered milk for drinks and cooking.", "price": 16.00, "category": "Grocery", "in_stock": True, "stock_count": 28},
        {"market_name": m4, "name": "عدس أحمر", "description": "عدس أحمر مجروش للشوربات والطبخ", "price": 6.00, "category": "Grocery", "in_stock": True, "stock_count": 50},
        {"market_name": m4, "name": "Red Lentils", "description": "Split red lentils for soups and dals.", "price": 6.50, "category": "Grocery", "in_stock": True, "stock_count": 48},
        {"market_name": m4, "name": "معكرونة سباغيتي", "description": "معكرونة سباغيتي إيطالية", "price": 4.00, "category": "Grocery", "in_stock": True, "stock_count": 70},
        {"market_name": m4, "name": "Spaghetti Pasta", "description": "Italian spaghetti pasta, durum wheat.", "price": 4.50, "category": "Grocery", "in_stock": True, "stock_count": 65},
        {"market_name": m4, "name": "صلصة طماطم", "description": "صلصة طماطم مركزة جاهزة للطبخ", "price": 3.00, "category": "Grocery", "in_stock": True, "stock_count": 60},
        {"market_name": m4, "name": "Tomato Paste", "description": "Concentrated tomato paste for cooking.", "price": 3.50, "category": "Grocery", "in_stock": True, "stock_count": 55},
        {"market_name": m4, "name": "خل تفاح طبيعي", "description": "خل تفاح طبيعي غير مفلتر مع الأم", "price": 12.00, "category": "Grocery", "in_stock": True, "stock_count": 20},
        {"market_name": m4, "name": "Apple Cider Vinegar", "description": "Organic raw apple cider vinegar with mother.", "price": 14.00, "category": "Grocery", "in_stock": True, "stock_count": 18},
        {"market_name": m4, "name": "ملح بحري", "description": "ملح بحري طبيعي خشن", "price": 3.00, "category": "Spices", "in_stock": True, "stock_count": 50},
        {"market_name": m4, "name": "Sea Salt - Coarse", "description": "Natural coarse sea salt.", "price": 3.50, "category": "Spices", "in_stock": True, "stock_count": 45},
        {"market_name": m4, "name": "فول مدمس", "description": "فول مدمس معلب جاهز للأكل", "price": 2.50, "category": "Grocery", "in_stock": True, "stock_count": 90},
    ]

    # ── Market 5: Fresh Valley Market ─────────────────────────
    m5 = "Fresh Valley Market"
    all_products += [
        {"market_name": m5, "name": "Green Tea - Jasmine", "description": "Jasmine-scented green tea leaves.", "price": 20.00, "category": "Tea", "in_stock": True, "stock_count": 30},
        {"market_name": m5, "name": "Colombian Coffee Beans", "description": "Single-origin Colombian Arabica beans.", "price": 48.00, "category": "Coffee", "in_stock": True, "stock_count": 15},
        {"market_name": m5, "name": "Manuka Honey - UMF 10+", "description": "New Zealand Manuka honey, UMF 10+.", "price": 180.00, "category": "Honey", "in_stock": True, "stock_count": 4},
        {"market_name": m5, "name": "Dried Apricots", "description": "Turkish dried apricots, naturally sweet.", "price": 22.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 25},
        {"market_name": m5, "name": "مشمش مجفف", "description": "مشمش مجفف تركي طبيعي حلو المذاق", "price": 24.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 20},
        {"market_name": m5, "name": "Walnut Halves", "description": "Premium walnut halves, California grown.", "price": 38.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 18},
        {"market_name": m5, "name": "جوز كامل", "description": "جوز كامل فاخر، غني بالأوميغا", "price": 40.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 14},
        {"market_name": m5, "name": "Olive Oil - Palestinian", "description": "Traditional Palestinian extra virgin olive oil.", "price": 50.00, "category": "Oils", "in_stock": True, "stock_count": 10},
        {"market_name": m5, "name": "زيت زيتون فلسطيني", "description": "زيت زيتون فلسطيني بكر ممتاز أصلي", "price": 52.00, "category": "Oils", "in_stock": True, "stock_count": 8},
        {"market_name": m5, "name": "Sesame Oil", "description": "Toasted sesame oil for Asian cuisine.", "price": 18.00, "category": "Oils", "in_stock": True, "stock_count": 22},
        {"market_name": m5, "name": "شاي نعناع طازج", "description": "شاي نعناع أخضر طازج منعش", "price": 10.00, "category": "Tea", "in_stock": True, "stock_count": 40},
        {"market_name": m5, "name": "Peppermint Tea", "description": "Fresh peppermint herbal tea, caffeine-free.", "price": 12.00, "category": "Tea", "in_stock": True, "stock_count": 35},
        {"market_name": m5, "name": "Ethiopian Coffee - Light Roast", "description": "Ethiopian Yirgacheffe light roast coffee.", "price": 52.00, "category": "Coffee", "in_stock": True, "stock_count": 10},
        {"market_name": m5, "name": "قهوة إثيوبية", "description": "قهوة إثيوبية يرغاشيف محمصة خفيفة", "price": 55.00, "category": "Coffee", "in_stock": True, "stock_count": 8},
        {"market_name": m5, "name": "Dried Cranberries", "description": "Sweetened dried cranberries for snacking.", "price": 18.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 30},
        {"market_name": m5, "name": "Macadamia Nuts", "description": "Raw macadamia nuts from Hawaii.", "price": 85.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 6},
        {"market_name": m5, "name": "Cumin Seeds - Whole", "description": "Whole cumin seeds for tempering.", "price": 12.00, "category": "Spices", "in_stock": True, "stock_count": 35},
        {"market_name": m5, "name": "كزبرة مطحونة", "description": "كزبرة مطحونة طازجة للطبخ", "price": 8.00, "category": "Spices", "in_stock": True, "stock_count": 40},
        {"market_name": m5, "name": "Sunflower Seeds - Roasted", "description": "Roasted salted sunflower seeds.", "price": 8.00, "category": "Seeds", "in_stock": True, "stock_count": 50},
        {"market_name": m5, "name": "بذور عباد الشمس", "description": "بذور عباد الشمس المحمصة والمملحة", "price": 7.00, "category": "Seeds", "in_stock": True, "stock_count": 55},
        {"market_name": m5, "name": "Peanut Butter - Crunchy", "description": "Crunchy peanut butter with peanut pieces.", "price": 16.00, "category": "Spreads", "in_stock": True, "stock_count": 25},
        {"market_name": m5, "name": "عسل زهور ربيعية", "description": "عسل زهور ربيعية طبيعي من الأردن", "price": 65.00, "category": "Honey", "in_stock": True, "stock_count": 7},
        {"market_name": m5, "name": "Nutella", "description": "Hazelnut chocolate spread.", "price": 22.00, "category": "Spreads", "in_stock": True, "stock_count": 35},
        {"market_name": m5, "name": "شاي يانسون", "description": "شاي يانسون عشبي دافئ ومهدئ", "price": 10.00, "category": "Tea", "in_stock": True, "stock_count": 28},
        {"market_name": m5, "name": "شاي الغزالين سيلاني", "description": "شاي الغزالين سيلاني فاخر كلاسيكي طعم رائع ورائحة زكية", "price": 15.00, "category": "Tea", "in_stock": True, "stock_count": 30},
        {"market_name": m5, "name": "Alghazaleen Black Tea", "description": "Premium Alghazaleen Ceylon black tea bags with rich flavor and aroma", "price": 14.00, "category": "Tea", "in_stock": True, "stock_count": 35},
        {"market_name": m5, "name": "Clove - Whole", "description": "Whole dried cloves for cooking and tea.", "price": 20.00, "category": "Spices", "in_stock": True, "stock_count": 25},
    ]

    # ── Market 6: محمصة النكهة الذهبية ─────────────────────────
    m6 = "محمصة النكهة الذهبية"
    all_products += [
        {"market_name": m6, "name": "قهوة عربية فاتحة", "description": "قهوة عربية محمصة فاتحة مع هيل وزعفران", "price": 40.00, "category": "Coffee", "in_stock": True, "stock_count": 20},
        {"market_name": m6, "name": "قهوة عربية غامقة", "description": "قهوة عربية محمصة غامقة بالهيل", "price": 38.00, "category": "Coffee", "in_stock": True, "stock_count": 22},
        {"market_name": m6, "name": "قهوة تركية وسط", "description": "قهوة تركية محمصة وسط ناعمة", "price": 30.00, "category": "Coffee", "in_stock": True, "stock_count": 25},
        {"market_name": m6, "name": "بن برازيلي", "description": "بن برازيلي أصلي محمص طازج", "price": 45.00, "category": "Coffee", "in_stock": True, "stock_count": 15},
        {"market_name": m6, "name": "Brazilian Coffee Beans", "description": "Fresh roasted Brazilian Santos coffee beans.", "price": 48.00, "category": "Coffee", "in_stock": True, "stock_count": 12},
        {"market_name": m6, "name": "Espresso Blend", "description": "Italian-style espresso blend, bold and rich.", "price": 42.00, "category": "Coffee", "in_stock": True, "stock_count": 18},
        {"market_name": m6, "name": "قهوة كولومبية فاخرة", "description": "قهوة كولومبية أصلية أحادية المصدر", "price": 55.00, "category": "Coffee", "in_stock": True, "stock_count": 8},
        {"market_name": m6, "name": "هيل أخضر فاخر", "description": "هيل أخضر هندي فاخر للقهوة العربية", "price": 55.00, "category": "Spices", "in_stock": True, "stock_count": 10},
        {"market_name": m6, "name": "Green Cardamom - Premium", "description": "Premium Indian green cardamom for Arabic coffee.", "price": 52.00, "category": "Spices", "in_stock": True, "stock_count": 12},
        {"market_name": m6, "name": "زعفران إيراني", "description": "زعفران إيراني أصلي درجة أولى", "price": 90.00, "category": "Spices", "in_stock": True, "stock_count": 5},
        {"market_name": m6, "name": "Saffron Threads - Super Negin", "description": "Super Negin grade Iranian saffron.", "price": 95.00, "category": "Spices", "in_stock": True, "stock_count": 4},
        {"market_name": m6, "name": "شاي أحمر إنجليزي", "description": "شاي أحمر إنجليزي فاخر بنكهة قوية", "price": 22.00, "category": "Tea", "in_stock": True, "stock_count": 30},
        {"market_name": m6, "name": "English Breakfast Tea", "description": "Classic English breakfast tea blend.", "price": 24.00, "category": "Tea", "in_stock": True, "stock_count": 28},
        {"market_name": m6, "name": "شاي الشاي الأخضر بالنعناع", "description": "شاي أخضر بالنعناع المغربي التقليدي", "price": 18.00, "category": "Tea", "in_stock": True, "stock_count": 25},
        {"market_name": m6, "name": "Moroccan Mint Green Tea", "description": "Traditional Moroccan mint green tea blend.", "price": 20.00, "category": "Tea", "in_stock": True, "stock_count": 22},
        {"market_name": m6, "name": "فستق حلبي خام", "description": "فستق حلبي خام غير محمص", "price": 75.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 8},
        {"market_name": m6, "name": "لوز محمص بالملح", "description": "لوز كاليفورني محمص ومملح", "price": 45.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 15},
        {"market_name": m6, "name": "Almonds - Roasted", "description": "California almonds, dry roasted.", "price": 42.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 18},
        {"market_name": m6, "name": "تمر سكري سعودي", "description": "تمر سكري سعودي حلو ولذيذ", "price": 60.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 20},
        {"market_name": m6, "name": "Medjool Dates - Jumbo", "description": "Jumbo Medjool dates, extra soft.", "price": 65.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 16},
        {"market_name": m6, "name": "عسل أكاسيا", "description": "عسل أكاسيا صافي بنكهة خفيفة", "price": 70.00, "category": "Honey", "in_stock": True, "stock_count": 7},
        {"market_name": m6, "name": "Acacia Honey - Raw", "description": "Raw acacia honey, light and delicate.", "price": 72.00, "category": "Honey", "in_stock": True, "stock_count": 6},
        {"market_name": m6, "name": "قرنفل حب", "description": "قرنفل حب كامل عطري", "price": 22.00, "category": "Spices", "in_stock": True, "stock_count": 20},
        {"market_name": m6, "name": "Clove - Ground", "description": "Freshly ground cloves for baking.", "price": 18.00, "category": "Spices", "in_stock": True, "stock_count": 25},
        {"market_name": m6, "name": "Decaf Coffee - Swiss Water", "description": "Swiss water process decaf coffee beans.", "price": 50.00, "category": "Coffee", "in_stock": True, "stock_count": 10},
    ]

    # ── Markets 7-22: Bulk generation with diverse product mixes ──
    # Each market gets 25 unique products mixing AR/EN names

    # Market 7: Herbal Essence Shop
    m7 = "Herbal Essence Shop"
    all_products += [
        {"market_name": m7, "name": "Chamomile Herbal Tea", "description": "Pure dried chamomile flowers for herbal tea.", "price": 18.00, "category": "Tea", "in_stock": True, "stock_count": 30},
        {"market_name": m7, "name": "شاي زنجبيل وليمون", "description": "شاي زنجبيل وليمون طبيعي دافئ", "price": 15.00, "category": "Tea", "in_stock": True, "stock_count": 35},
        {"market_name": m7, "name": "Ginger Lemon Tea", "description": "Natural ginger and lemon herbal tea.", "price": 16.00, "category": "Tea", "in_stock": True, "stock_count": 30},
        {"market_name": m7, "name": "شاي كركديه", "description": "شاي كركديه (هيبسكس) مجفف طبيعي", "price": 14.00, "category": "Tea", "in_stock": True, "stock_count": 40},
        {"market_name": m7, "name": "Hibiscus Tea", "description": "Dried hibiscus flowers for tart herbal tea.", "price": 15.00, "category": "Tea", "in_stock": True, "stock_count": 38},
        {"market_name": m7, "name": "Eucalyptus Essential Oil", "description": "Pure eucalyptus oil for respiratory relief.", "price": 20.00, "category": "Essential Oils", "in_stock": True, "stock_count": 15},
        {"market_name": m7, "name": "زيت شجرة الشاي", "description": "زيت شجرة الشاي النقي للبشرة والشعر", "price": 28.00, "category": "Essential Oils", "in_stock": True, "stock_count": 12},
        {"market_name": m7, "name": "Peppermint Essential Oil", "description": "Pure peppermint oil for headaches and focus.", "price": 18.00, "category": "Essential Oils", "in_stock": True, "stock_count": 16},
        {"market_name": m7, "name": "زيت إكليل الجبل", "description": "زيت إكليل الجبل (روزماري) لتقوية الشعر", "price": 24.00, "category": "Essential Oils", "in_stock": True, "stock_count": 14},
        {"market_name": m7, "name": "Frankincense Essential Oil", "description": "Pure frankincense oil for meditation.", "price": 35.00, "category": "Essential Oils", "in_stock": True, "stock_count": 8},
        {"market_name": m7, "name": "زيت اللبان", "description": "زيت اللبان (الكندر) للتأمل والاسترخاء", "price": 38.00, "category": "Essential Oils", "in_stock": True, "stock_count": 6},
        {"market_name": m7, "name": "Turmeric Latte Mix", "description": "Golden turmeric latte spice blend.", "price": 22.00, "category": "Tea", "in_stock": True, "stock_count": 20},
        {"market_name": m7, "name": "مورينغا مطحونة", "description": "أوراق مورينغا مطحونة عضوية", "price": 25.00, "category": "Tea", "in_stock": True, "stock_count": 15},
        {"market_name": m7, "name": "Moringa Powder", "description": "Organic moringa leaf powder superfood.", "price": 28.00, "category": "Tea", "in_stock": True, "stock_count": 12},
        {"market_name": m7, "name": "عسل مانوكا", "description": "عسل مانوكا نيوزيلندي UMF 5+", "price": 120.00, "category": "Honey", "in_stock": True, "stock_count": 3},
        {"market_name": m7, "name": "Raw Forest Honey", "description": "Wild raw forest honey, unprocessed.", "price": 60.00, "category": "Honey", "in_stock": True, "stock_count": 8},
        {"market_name": m7, "name": "بذور شيا عضوية", "description": "بذور شيا عضوية غنية بالألياف", "price": 24.00, "category": "Seeds", "in_stock": True, "stock_count": 25},
        {"market_name": m7, "name": "Ashwagandha Powder", "description": "Organic ashwagandha root powder for stress.", "price": 30.00, "category": "Seeds", "in_stock": True, "stock_count": 10},
        {"market_name": m7, "name": "حبة البركة", "description": "حبة البركة (الحبة السوداء) العضوية", "price": 15.00, "category": "Seeds", "in_stock": True, "stock_count": 30},
        {"market_name": m7, "name": "Black Seed - Whole", "description": "Whole black seeds (Nigella sativa).", "price": 16.00, "category": "Seeds", "in_stock": True, "stock_count": 28},
        {"market_name": m7, "name": "زيت حبة البركة عضوي", "description": "زيت حبة البركة العضوي المعصور على البارد", "price": 42.00, "category": "Oils", "in_stock": True, "stock_count": 10},
        {"market_name": m7, "name": "Coconut MCT Oil", "description": "Pure MCT oil from coconuts for energy.", "price": 35.00, "category": "Oils", "in_stock": True, "stock_count": 14},
        {"market_name": m7, "name": "زيت أرغان للطبخ", "description": "زيت أرغان مغربي أصلي للطبخ", "price": 55.00, "category": "Oils", "in_stock": True, "stock_count": 6},
        {"market_name": m7, "name": "Argan Oil - Culinary", "description": "Moroccan culinary argan oil, nutty flavor.", "price": 58.00, "category": "Oils", "in_stock": True, "stock_count": 5},
        {"market_name": m7, "name": "Rooibos Tea - South African", "description": "Caffeine-free South African rooibos tea.", "price": 20.00, "category": "Tea", "in_stock": True, "stock_count": 18},
    ]

    # Market 8: دكان أبو سمير
    m8 = "دكان أبو سمير"
    all_products += [
        {"market_name": m8, "name": "شاي أحمر بالحليب", "description": "شاي أحمر كرك بالحليب والهيل والزعفران", "price": 20.00, "category": "Tea", "in_stock": True, "stock_count": 30},
        {"market_name": m8, "name": "Karak Tea Mix", "description": "Pre-mixed karak tea with milk powder and spices.", "price": 22.00, "category": "Tea", "in_stock": True, "stock_count": 25},
        {"market_name": m8, "name": "قهوة بالبندق", "description": "قهوة محمصة بنكهة البندق الطبيعية", "price": 35.00, "category": "Coffee", "in_stock": True, "stock_count": 15},
        {"market_name": m8, "name": "Hazelnut Coffee", "description": "Hazelnut flavored roasted coffee.", "price": 38.00, "category": "Coffee", "in_stock": True, "stock_count": 12},
        {"market_name": m8, "name": "حمص مطحون", "description": "حمص مطحون جاهز للحمص والفلافل", "price": 8.00, "category": "Grocery", "in_stock": True, "stock_count": 45},
        {"market_name": m8, "name": "Chickpea Flour", "description": "Ground chickpea flour for hummus and falafel.", "price": 9.00, "category": "Grocery", "in_stock": True, "stock_count": 40},
        {"market_name": m8, "name": "برغل ناعم", "description": "برغل ناعم للكبة والتبولة", "price": 6.00, "category": "Grocery", "in_stock": True, "stock_count": 50},
        {"market_name": m8, "name": "Fine Bulgur Wheat", "description": "Fine bulgur wheat for kibbeh and tabbouleh.", "price": 7.00, "category": "Grocery", "in_stock": True, "stock_count": 45},
        {"market_name": m8, "name": "فريكة خضراء", "description": "فريكة خضراء مدخنة للطبخ التقليدي", "price": 14.00, "category": "Grocery", "in_stock": True, "stock_count": 20},
        {"market_name": m8, "name": "Green Freekeh", "description": "Smoked green freekeh for traditional dishes.", "price": 16.00, "category": "Grocery", "in_stock": True, "stock_count": 18},
        {"market_name": m8, "name": "زعتر فلسطيني", "description": "زعتر فلسطيني أخضر طازج مع سمسم", "price": 12.00, "category": "Spices", "in_stock": True, "stock_count": 35},
        {"market_name": m8, "name": "Palestinian Za'atar", "description": "Fresh Palestinian za'atar with sesame.", "price": 14.00, "category": "Spices", "in_stock": True, "stock_count": 30},
        {"market_name": m8, "name": "مربى تين", "description": "مربى تين بلدي محلي الصنع", "price": 15.00, "category": "Spreads", "in_stock": True, "stock_count": 14},
        {"market_name": m8, "name": "Fig Jam - Homemade", "description": "Homemade fig jam, traditional recipe.", "price": 18.00, "category": "Spreads", "in_stock": True, "stock_count": 10},
        {"market_name": m8, "name": "لبنة بلدية", "description": "لبنة بلدية كثيفة طازجة", "price": 8.00, "category": "Grocery", "in_stock": True, "stock_count": 20},
        {"market_name": m8, "name": "عسل ربيعي بلدي", "description": "عسل ربيعي بلدي من الأردن", "price": 80.00, "category": "Honey", "in_stock": True, "stock_count": 5},
        {"market_name": m8, "name": "Spring Honey - Local", "description": "Local Jordanian spring blossom honey.", "price": 85.00, "category": "Honey", "in_stock": True, "stock_count": 4},
        {"market_name": m8, "name": "زيتون أخضر مخلل", "description": "زيتون أخضر مخلل بلدي أردني", "price": 10.00, "category": "Grocery", "in_stock": True, "stock_count": 30},
        {"market_name": m8, "name": "Green Olives - Pickled", "description": "Pickled Jordanian green olives.", "price": 12.00, "category": "Grocery", "in_stock": True, "stock_count": 25},
        {"market_name": m8, "name": "تمر خلاص سعودي", "description": "تمر خلاص سعودي ذهبي ممتاز", "price": 50.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 18},
        {"market_name": m8, "name": "Khalas Dates - Saudi", "description": "Golden Saudi Khalas dates, premium.", "price": 52.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 15},
        {"market_name": m8, "name": "زبيب أسود", "description": "زبيب أسود طبيعي مجفف", "price": 12.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 25},
        {"market_name": m8, "name": "Black Raisins", "description": "Natural dried black raisins.", "price": 14.00, "category": "Dried Fruits", "in_stock": True, "stock_count": 22},
        {"market_name": m8, "name": "حلبة مطحونة", "description": "حلبة مطحونة للطبخ والمشروبات الصحية", "price": 8.00, "category": "Spices", "in_stock": True, "stock_count": 30},
        {"market_name": m8, "name": "Fenugreek - Ground", "description": "Ground fenugreek for cooking and health drinks.", "price": 10.00, "category": "Spices", "in_stock": True, "stock_count": 25},
    ]

    # ── Markets 9-22: Generate 25 products each ──────────────
    # Using helper to create diverse product sets

    market_product_sets = {
        "Spice Route Bazaar": [
            ("Turmeric Root - Whole", "Whole turmeric root, fresh and aromatic.", "Spices", 14.00, True, 30),
            ("كركم جذور كامل", "كركم جذور كامل طازج وعطري", "Spices", 15.00, True, 28),
            ("Star Anise - Whole", "Whole star anise pods for cooking.", "Spices", 18.00, True, 20),
            ("يانسون نجمي", "يانسون نجمي كامل للطبخ والشاي", "Spices", 20.00, True, 18),
            ("Nutmeg - Whole", "Whole nutmeg for freshly grating.", "Spices", 25.00, True, 15),
            ("جوزة الطيب", "جوزة الطيب كاملة طازجة", "Spices", 28.00, True, 12),
            ("Paprika - Smoked Spanish", "Smoked Spanish paprika (pimentón).", "Spices", 16.00, True, 25),
            ("بابريكا مدخنة إسبانية", "بابريكا مدخنة إسبانية أصلية", "Spices", 18.00, True, 22),
            ("Mustard Seeds - Yellow", "Yellow mustard seeds for pickling.", "Spices", 8.00, True, 40),
            ("حبوب خردل أصفر", "حبوب خردل أصفر للمخللات والطبخ", "Spices", 9.00, True, 35),
            ("Oregano - Dried", "Dried Mediterranean oregano.", "Spices", 10.00, True, 30),
            ("زعتر بري مجفف", "زعتر بري مجفف من الجبال", "Spices", 12.00, True, 25),
            ("Bay Leaves - Dried", "Dried bay leaves for stews.", "Spices", 8.00, True, 35),
            ("ورق غار مجفف", "ورق غار (لورا) مجفف للطبخ", "Spices", 9.00, True, 30),
            ("Curry Powder - Madras", "Hot Madras curry powder blend.", "Spices", 14.00, True, 22),
            ("كاري ماداراس حار", "خلطة كاري ماداراس حارة هندية", "Spices", 16.00, True, 18),
            ("Garam Masala", "Authentic Indian garam masala blend.", "Spices", 18.00, True, 20),
            ("بهارات هندية مشكلة", "جارام ماسالا هندية أصلية", "Spices", 20.00, True, 16),
            ("Black Pepper - Ground", "Freshly ground black pepper.", "Spices", 12.00, True, 35),
            ("فلفل أسود مطحون", "فلفل أسود مطحون طازج", "Spices", 14.00, True, 30),
            ("Dried Chili Flakes", "Crushed red chili pepper flakes.", "Spices", 10.00, True, 40),
            ("رقائق فلفل حار", "رقائق فلفل أحمر حار مجروش", "Spices", 12.00, True, 35),
            ("Vanilla Beans - Madagascar", "Whole Madagascar vanilla beans.", "Spices", 45.00, True, 5),
            ("فانيلا مدغشقر", "أعواد فانيلا مدغشقر أصلية", "Spices", 48.00, True, 4),
            ("Mixed Spice Gift Box", "Curated gift box of 8 premium spices.", "Spices", 85.00, True, 8),
        ],
        "مركز السلطي للتسوق": [
            ("شاي أخضر ياباني", "شاي أخضر ياباني سينشا فاخر", "Tea", 28.00, True, 20),
            ("Japanese Sencha Green Tea", "Premium Japanese sencha green tea.", "Tea", 30.00, True, 18),
            ("قهوة فرنسية فانيلا", "قهوة محمصة بنكهة الفانيلا الفرنسية", "Coffee", 35.00, True, 15),
            ("French Vanilla Coffee", "French vanilla flavored roast coffee.", "Coffee", 38.00, True, 12),
            ("حليب مكثف محلى", "حليب مكثف محلى للحلويات", "Grocery", 6.00, True, 50),
            ("Condensed Milk - Sweetened", "Sweetened condensed milk for desserts.", "Grocery", 7.00, True, 45),
            ("خبز تورتيلا", "خبز تورتيلا طحين كامل", "Grocery", 5.00, True, 30),
            ("Tortilla Wraps - Whole Wheat", "Whole wheat tortilla wraps.", "Grocery", 6.00, True, 28),
            ("صويا صوص", "صلصة صويا يابانية طبيعية", "Grocery", 8.00, True, 35),
            ("Soy Sauce - Japanese", "Naturally brewed Japanese soy sauce.", "Grocery", 9.00, True, 30),
            ("طحين ذرة", "طحين ذرة ناعم للخبز والطبخ", "Grocery", 4.00, True, 40),
            ("Cornmeal - Fine", "Fine cornmeal for baking and polenta.", "Grocery", 5.00, True, 35),
            ("شعيرية", "شعيرية رفيعة للشوربات والأرز", "Grocery", 3.00, True, 60),
            ("Vermicelli Noodles", "Thin vermicelli for soups and rice.", "Grocery", 3.50, True, 55),
            ("جبنة حلوم", "جبنة حلوم قبرصية أصلية للشوي", "Grocery", 18.00, True, 15),
            ("Halloumi Cheese", "Authentic Cypriot halloumi for grilling.", "Grocery", 20.00, True, 12),
            ("مكسرات برازيلية", "مكسرات برازيلية خام غنية بالسيلينيوم", "Dried Fruits", 50.00, True, 10),
            ("Brazil Nuts - Raw", "Raw Brazil nuts, rich in selenium.", "Dried Fruits", 52.00, True, 8),
            ("تين مجفف", "تين مجفف تركي طبيعي حلو", "Dried Fruits", 20.00, True, 20),
            ("Dried Figs - Turkish", "Turkish dried figs, naturally sweet.", "Dried Fruits", 22.00, True, 18),
            ("زبدة فستق", "زبدة فستق حلبي فاخرة", "Spreads", 55.00, True, 6),
            ("Pistachio Butter", "Premium pistachio nut butter.", "Spreads", 58.00, True, 5),
            ("عسل طبيعي مع جوز", "عسل طبيعي مخلوط مع قطع الجوز", "Honey", 65.00, True, 8),
            ("Honey with Walnuts", "Raw honey infused with walnut pieces.", "Honey", 68.00, True, 6),
            ("شاي ماتشا ياباني", "شاي ماتشا ياباني عضوي فاخر", "Tea", 50.00, True, 8),
        ],
        "Golden Harvest Store": [
            ("Organic Brown Rice", "Whole grain organic brown rice.", "Grocery", 14.00, True, 40),
            ("أرز بني عضوي", "أرز بني عضوي كامل الحبة", "Grocery", 15.00, True, 35),
            ("Oat Flakes - Rolled", "Rolled oat flakes for porridge.", "Grocery", 8.00, True, 50),
            ("شوفان ملفوف", "شوفان ملفوف كامل للفطور", "Grocery", 9.00, True, 45),
            ("Buckwheat Groats", "Raw buckwheat groats, gluten-free.", "Grocery", 12.00, True, 25),
            ("حنطة سوداء", "حنطة سوداء خام خالية من الغلوتين", "Grocery", 14.00, True, 20),
            ("Millet - Whole Grain", "Whole grain millet for cooking.", "Grocery", 10.00, True, 30),
            ("دخن كامل الحبة", "دخن كامل الحبة للطبخ الصحي", "Grocery", 12.00, True, 25),
            ("Dried Mango", "Dried mango slices, no sugar added.", "Dried Fruits", 20.00, True, 18),
            ("مانجو مجففة", "شرائح مانجو مجففة بدون سكر مضاف", "Dried Fruits", 22.00, True, 15),
            ("Goji Berries", "Organic dried goji berries.", "Dried Fruits", 28.00, True, 12),
            ("توت غوجي", "توت غوجي عضوي مجفف", "Dried Fruits", 30.00, True, 10),
            ("Hazelnut Butter", "Creamy hazelnut butter, no additives.", "Spreads", 35.00, True, 14),
            ("زبدة بندق", "زبدة بندق صافية بدون إضافات", "Spreads", 38.00, True, 12),
            ("Cashew Butter", "Smooth cashew nut butter.", "Spreads", 40.00, True, 10),
            ("زبدة كاجو", "زبدة كاجو ناعمة وصحية", "Spreads", 42.00, True, 8),
            ("Matcha Latte Powder", "Instant matcha latte mix with milk.", "Tea", 25.00, True, 20),
            ("شاي ماتشا لاتيه", "خلطة ماتشا لاتيه سريعة التحضير", "Tea", 28.00, True, 18),
            ("Rooibos Vanilla Tea", "Vanilla flavored rooibos tea.", "Tea", 18.00, True, 22),
            ("شاي رويبوس بالفانيلا", "شاي رويبوس جنوب أفريقي بالفانيلا", "Tea", 20.00, True, 20),
            ("Walnut Oil", "Cold-pressed walnut oil for salads.", "Oils", 35.00, True, 10),
            ("زيت جوز", "زيت جوز معصور على البارد للسلطات", "Oils", 38.00, True, 8),
            ("Flaxseed Oil", "Organic cold-pressed flaxseed oil.", "Oils", 25.00, True, 15),
            ("زيت بذور الكتان", "زيت بذور كتان عضوي معصور على البارد", "Oils", 28.00, True, 12),
            ("Bee Pollen Granules", "Raw bee pollen granules superfood.", "Honey", 35.00, True, 10),
        ],
        "بيت العطارة": [
            ("لبان ذكر", "لبان ذكر عماني أصلي فاخر", "Spices", 30.00, True, 15),
            ("Frankincense - Omani", "Premium Omani frankincense resin.", "Spices", 32.00, True, 12),
            ("مسك أبيض", "مسك أبيض طبيعي للتعطير", "Essential Oils", 40.00, True, 8),
            ("White Musk - Natural", "Natural white musk for fragrance.", "Essential Oils", 42.00, True, 6),
            ("حناء طبيعية", "حناء طبيعية هندية للشعر والجسم", "Essential Oils", 15.00, True, 25),
            ("Henna Powder - Natural", "Natural Indian henna powder.", "Essential Oils", 16.00, True, 22),
            ("مر بطارخ", "مر بطارخ أصلي للبخور والعلاج", "Spices", 35.00, True, 10),
            ("Myrrh Resin", "Authentic myrrh resin for incense.", "Spices", 38.00, True, 8),
            ("عود هندي", "عود هندي فاخر للبخور", "Spices", 80.00, True, 4),
            ("Oud Wood - Indian", "Premium Indian oud wood chips.", "Spices", 85.00, True, 3),
            ("بخور مشكل", "خلطة بخور مشكلة فاخرة", "Spices", 25.00, True, 15),
            ("Mixed Incense Blend", "Premium mixed incense blend.", "Spices", 28.00, True, 12),
            ("شاي أعشاب للمعدة", "خلطة أعشاب مهدئة للمعدة والهضم", "Tea", 15.00, True, 20),
            ("Digestive Herbal Tea", "Herbal tea blend for digestion.", "Tea", 18.00, True, 18),
            ("خلطة أعشاب للسعال", "خلطة أعشاب طبيعية لعلاج السعال", "Tea", 14.00, True, 22),
            ("Cough Relief Herbal Tea", "Natural herbal blend for cough relief.", "Tea", 16.00, True, 20),
            ("زيت سمسم بلدي", "زيت سمسم بلدي معصور طازج", "Oils", 20.00, True, 18),
            ("Sesame Oil - Traditional", "Traditional cold-pressed sesame oil.", "Oils", 22.00, True, 15),
            ("حبة حلوة", "حبة حلوة (يانسون) للمشروبات الساخنة", "Spices", 10.00, True, 30),
            ("Anise Seeds - Whole", "Whole anise seeds for drinks and baking.", "Spices", 12.00, True, 25),
            ("محلب", "محلب حب كامل للمعمول والحلويات", "Spices", 18.00, True, 15),
            ("Mahlab Seeds", "Whole mahlab seeds for Arabic pastries.", "Spices", 20.00, True, 12),
            ("مستكة", "مستكة يونانية أصلية للحلويات والمشروبات", "Spices", 45.00, True, 6),
            ("Mastic Gum - Greek", "Authentic Greek mastic gum.", "Spices", 48.00, True, 5),
            ("عسل سمر يمني", "عسل سمر يمني أصلي فاخر", "Honey", 160.00, True, 2),
        ],
        "Mediterranean Delights": [
            ("Extra Virgin Olive Oil - Greek", "Premium Greek Kalamata olive oil.", "Oils", 45.00, True, 15),
            ("زيت زيتون يوناني", "زيت زيتون يوناني بكر ممتاز من كالاماتا", "Oils", 48.00, True, 12),
            ("Balsamic Vinegar - Modena", "Aged balsamic vinegar from Modena.", "Grocery", 35.00, True, 10),
            ("خل بلسمي إيطالي", "خل بلسمي معتق من مودينا الإيطالية", "Grocery", 38.00, True, 8),
            ("Pesto Sauce - Basil", "Classic Italian basil pesto sauce.", "Grocery", 22.00, True, 18),
            ("صلصة بيستو ريحان", "صلصة بيستو ريحان إيطالية كلاسيكية", "Grocery", 25.00, True, 15),
            ("Kalamata Olives", "Greek Kalamata olives in brine.", "Grocery", 18.00, True, 20),
            ("زيتون كالاماتا يوناني", "زيتون كالاماتا يوناني في محلول ملحي", "Grocery", 20.00, True, 18),
            ("Sun-Dried Tomatoes", "Italian sun-dried tomatoes in oil.", "Grocery", 28.00, True, 14),
            ("طماطم مجففة بالشمس", "طماطم مجففة بالشمس إيطالية في الزيت", "Grocery", 30.00, True, 12),
            ("Pine Nuts", "Mediterranean pine nuts for pesto and salads.", "Dried Fruits", 60.00, True, 8),
            ("صنوبر", "حبوب صنوبر متوسطية فاخرة", "Dried Fruits", 65.00, True, 6),
            ("Artichoke Hearts", "Marinated artichoke hearts in oil.", "Grocery", 16.00, True, 15),
            ("قلوب أرضي شوكي", "قلوب أرضي شوكي متبلة في الزيت", "Grocery", 18.00, True, 12),
            ("Truffle Oil", "Black truffle infused olive oil.", "Oils", 55.00, True, 5),
            ("زيت كمأة (ترافل)", "زيت زيتون بنكهة الكمأة السوداء", "Oils", 58.00, True, 4),
            ("Feta Cheese - Greek", "Authentic Greek feta in brine.", "Grocery", 22.00, True, 12),
            ("جبنة فيتا يونانية", "جبنة فيتا يونانية أصلية في محلول ملحي", "Grocery", 25.00, True, 10),
            ("Orzo Pasta", "Mediterranean orzo rice-shaped pasta.", "Grocery", 8.00, True, 30),
            ("معكرونة أورزو", "معكرونة أورزو على شكل حبات أرز", "Grocery", 9.00, True, 28),
            ("Capers in Salt", "Mediterranean capers preserved in salt.", "Grocery", 14.00, True, 18),
            ("كبر مملح", "كبر متوسطي محفوظ في الملح", "Grocery", 16.00, True, 15),
            ("Tahini - Premium", "Premium stone-ground sesame tahini.", "Spreads", 25.00, True, 15),
            ("طحينة حجرية فاخرة", "طحينة مطحونة على الحجر فاخرة", "Spreads", 28.00, True, 12),
            ("Harissa Paste", "North African harissa chili paste.", "Spices", 14.00, True, 20),
        ],
        "تموينات الخير": [
            ("أرز مصري", "أرز مصري قصير الحبة للأرز بالشعيرية", "Grocery", 10.00, True, 60),
            ("Egyptian Rice - Short Grain", "Short grain Egyptian rice.", "Grocery", 11.00, True, 55),
            ("سمنة بلدية", "سمنة بلدية حيوانية للطبخ التقليدي", "Oils", 25.00, True, 15),
            ("Ghee - Traditional", "Traditional animal ghee for cooking.", "Oils", 28.00, True, 12),
            ("شاي كرك مسحوق", "شاي كرك جاهز بالحليب والتوابل", "Tea", 18.00, True, 30),
            ("Karak Tea Powder", "Ready-mix karak tea with spices and milk.", "Tea", 20.00, True, 25),
            ("مربى مشمش", "مربى مشمش بلدي طبيعي", "Spreads", 12.00, True, 20),
            ("Apricot Jam - Natural", "Natural homemade apricot jam.", "Spreads", 14.00, True, 18),
            ("حمص حب كامل", "حمص حب كامل مجفف للطبخ", "Grocery", 6.00, True, 50),
            ("Chickpeas - Dried Whole", "Dried whole chickpeas for cooking.", "Grocery", 7.00, True, 45),
            ("عدس أسود", "عدس أسود كامل (بيلوغا)", "Grocery", 10.00, True, 30),
            ("Black Lentils - Beluga", "Whole black beluga lentils.", "Grocery", 12.00, True, 25),
            ("فاصوليا بيضاء", "فاصوليا بيضاء مجففة للطبخ", "Grocery", 7.00, True, 40),
            ("White Beans - Dried", "Dried white navy beans.", "Grocery", 8.00, True, 35),
            ("حلبة حب", "حلبة حب كاملة للشاي والطبخ", "Spices", 6.00, True, 35),
            ("Fenugreek Seeds - Whole", "Whole fenugreek seeds.", "Spices", 7.00, True, 30),
            ("شاي أعشاب بالزنجبيل", "شاي أعشاب بالزنجبيل والقرفة", "Tea", 14.00, True, 25),
            ("Ginger Cinnamon Tea", "Herbal tea with ginger and cinnamon.", "Tea", 16.00, True, 22),
            ("دبس خروب", "دبس خروب طبيعي حلو ومغذي", "Spreads", 10.00, True, 20),
            ("Carob Molasses", "Natural sweet carob molasses.", "Spreads", 12.00, True, 18),
            ("عسل جبلي عضوي", "عسل جبلي عضوي من المرتفعات الأردنية", "Honey", 100.00, True, 5),
            ("Organic Mountain Honey", "Organic mountain honey from Jordan highlands.", "Honey", 105.00, True, 4),
            ("تمر عنبرة", "تمر عنبرة مدني فاخر", "Dried Fruits", 70.00, True, 10),
            ("Amber Dates - Madinah", "Premium Madinah amber dates.", "Dried Fruits", 75.00, True, 8),
            ("زيت زيتون بلدي أردني", "زيت زيتون بلدي أردني معصور على البارد", "Oils", 38.00, True, 15),
        ],
        "Olive Tree Market": [
            ("Olive Oil - Jordanian Premium", "Award-winning Jordanian olive oil.", "Oils", 55.00, True, 12),
            ("زيت زيتون أردني فاخر", "زيت زيتون أردني فاخر حائز على جوائز", "Oils", 58.00, True, 10),
            ("Olive Soap - Nablus", "Traditional Nablus olive oil soap.", "Grocery", 5.00, True, 50),
            ("صابون نابلسي", "صابون نابلسي تقليدي من زيت الزيتون", "Grocery", 6.00, True, 45),
            ("Olive Tapenade", "Black olive tapenade spread.", "Spreads", 18.00, True, 15),
            ("معجون زيتون أسود", "معجون زيتون أسود للمقبلات", "Spreads", 20.00, True, 12),
            ("Green Olives - Stuffed", "Green olives stuffed with almonds.", "Grocery", 15.00, True, 20),
            ("زيتون أخضر محشي لوز", "زيتون أخضر محشي باللوز", "Grocery", 18.00, True, 15),
            ("Olive Leaf Tea", "Dried olive leaves for herbal tea.", "Tea", 12.00, True, 25),
            ("شاي أوراق الزيتون", "شاي أوراق زيتون مجففة عشبي", "Tea", 14.00, True, 22),
            ("Olive Oil - Infused Chili", "Chili-infused extra virgin olive oil.", "Oils", 30.00, True, 10),
            ("زيت زيتون بالفلفل الحار", "زيت زيتون بكر بنكهة الفلفل الحار", "Oils", 32.00, True, 8),
            ("Olive Oil - Lemon Infused", "Lemon-infused olive oil for fish.", "Oils", 28.00, True, 12),
            ("زيت زيتون بالليمون", "زيت زيتون بكر بنكهة الليمون للسمك", "Oils", 30.00, True, 10),
            ("Dried Thyme - Wild", "Wild dried thyme from Jordan mountains.", "Spices", 14.00, True, 25),
            ("زعتر بري جبلي", "زعتر بري مجفف من جبال الأردن", "Spices", 16.00, True, 22),
            ("Raw Honey - Olive Blossom", "Raw honey from olive tree blossoms.", "Honey", 80.00, True, 6),
            ("عسل أزهار الزيتون", "عسل أزهار زيتون طبيعي خام", "Honey", 85.00, True, 5),
            ("Mixed Olives - Marinated", "Mixed marinated olives with herbs.", "Grocery", 16.00, True, 18),
            ("زيتون مشكل متبل", "زيتون مشكل متبل بالأعشاب", "Grocery", 18.00, True, 15),
            ("شاي أخضر بالزيتون", "شاي أخضر مع مستخلص أوراق الزيتون", "Tea", 18.00, True, 15),
            ("Green Tea with Olive Leaf", "Green tea blended with olive leaf extract.", "Tea", 20.00, True, 12),
            ("Olive Wood Honey Dipper", "Handcrafted olive wood honey dipper.", "Grocery", 8.00, True, 20),
            ("ملعقة عسل من خشب الزيتون", "ملعقة عسل مصنوعة يدوياً من خشب الزيتون", "Grocery", 10.00, True, 15),
            ("Zaatar Oil", "Olive oil infused with wild zaatar.", "Oils", 25.00, True, 14),
        ],
        "محل أبو العز للبهارات": [
            ("بهارات كبسة", "خلطة بهارات كبسة سعودية أصلية", "Spices", 15.00, True, 30),
            ("Kabsa Spice Mix", "Authentic Saudi kabsa spice blend.", "Spices", 18.00, True, 25),
            ("بهارات مشاوي", "خلطة بهارات خاصة للمشاوي والشوي", "Spices", 12.00, True, 35),
            ("BBQ Spice Rub", "Special BBQ and grilling spice rub.", "Spices", 14.00, True, 30),
            ("بهارات مكبوس", "خلطة بهارات مكبوس خليجية", "Spices", 16.00, True, 25),
            ("Machboos Spice Mix", "Gulf-style machboos spice blend.", "Spices", 18.00, True, 22),
            ("بزار عماني", "بزار عماني مشكل فاخر", "Spices", 20.00, True, 18),
            ("Omani Bzar Mix", "Traditional Omani bzar spice blend.", "Spices", 22.00, True, 15),
            ("بهارات فلافل", "خلطة بهارات فلافل خاصة", "Spices", 10.00, True, 40),
            ("Falafel Spice Mix", "Special falafel seasoning blend.", "Spices", 12.00, True, 35),
            ("بهارات شاورما", "خلطة بهارات شاورما أصلية", "Spices", 14.00, True, 30),
            ("Shawarma Spice Mix", "Authentic shawarma seasoning blend.", "Spices", 16.00, True, 25),
            ("حب هال أخضر مطحون", "هيل أخضر مطحون طازج", "Spices", 48.00, True, 8),
            ("Ground Green Cardamom", "Freshly ground green cardamom.", "Spices", 50.00, True, 6),
            ("قرفة مطحونة", "قرفة مطحونة ناعمة للحلويات", "Spices", 12.00, True, 30),
            ("Ground Cinnamon - Fine", "Fine ground cinnamon for desserts.", "Spices", 14.00, True, 25),
            ("فلفل أبيض مطحون", "فلفل أبيض مطحون للطبخ الراقي", "Spices", 15.00, True, 20),
            ("White Pepper - Ground", "Ground white pepper for fine cooking.", "Spices", 16.00, True, 18),
            ("ثوم مطحون", "ثوم مطحون مجفف عالي الجودة", "Spices", 10.00, True, 35),
            ("Garlic Powder", "High-quality dried garlic powder.", "Spices", 12.00, True, 30),
            ("بصل مطحون", "بصل مطحون مجفف للتتبيلات", "Spices", 8.00, True, 40),
            ("Onion Powder", "Dried onion powder for marinades.", "Spices", 10.00, True, 35),
            ("سبع بهارات", "خلطة سبع بهارات لبنانية تقليدية", "Spices", 14.00, True, 25),
            ("Seven Spice - Lebanese", "Traditional Lebanese seven spice blend.", "Spices", 16.00, True, 22),
            ("خلطة بهارات هندية", "خلطة بهارات هندية متنوعة فاخرة", "Spices", 20.00, True, 15),
        ],
        "Summit Health Foods": [
            ("Whey Protein - Vanilla", "Vanilla whey protein isolate.", "Grocery", 85.00, True, 10),
            ("بروتين مصل اللبن فانيلا", "بروتين مصل اللبن عزل بنكهة الفانيلا", "Grocery", 88.00, True, 8),
            ("Collagen Peptides", "Hydrolyzed collagen peptides powder.", "Grocery", 65.00, True, 12),
            ("كولاجين ببتيدات", "مسحوق ببتيدات الكولاجين المحلل", "Grocery", 68.00, True, 10),
            ("MCT Oil Powder", "Powdered MCT oil for keto diet.", "Oils", 45.00, True, 14),
            ("مسحوق زيت MCT", "مسحوق زيت MCT لنظام الكيتو", "Oils", 48.00, True, 12),
            ("Green Superfood Powder", "Organic greens blend superfood.", "Seeds", 55.00, True, 8),
            ("مسحوق خضروات فائقة", "خلطة خضروات عضوية فائقة الجودة", "Seeds", 58.00, True, 6),
            ("Vitamin C Powder", "Pure ascorbic acid vitamin C.", "Grocery", 25.00, True, 20),
            ("فيتامين سي مسحوق", "مسحوق فيتامين سي (حمض الأسكوربيك)", "Grocery", 28.00, True, 18),
            ("Electrolyte Mix", "Sugar-free electrolyte replenisher.", "Grocery", 18.00, True, 25),
            ("خلطة إلكتروليت", "خلطة إلكتروليت بدون سكر", "Grocery", 20.00, True, 22),
            ("Matcha Green Tea Powder", "Ceremonial grade matcha for focus.", "Tea", 48.00, True, 8),
            ("شاي ماتشا احتفالي", "شاي ماتشا ياباني درجة احتفالية للتركيز", "Tea", 50.00, True, 6),
            ("Yerba Mate - Organic", "Organic yerba mate for sustained energy.", "Tea", 22.00, True, 18),
            ("يربا ماتي عضوية", "يربا ماتي عضوية لطاقة مستدامة", "Tea", 24.00, True, 15),
            ("Hemp Protein Powder", "Organic hemp protein powder.", "Seeds", 40.00, True, 12),
            ("بروتين قنب عضوي", "مسحوق بروتين القنب العضوي", "Seeds", 42.00, True, 10),
            ("Chlorella Tablets", "Organic chlorella detox tablets.", "Seeds", 35.00, True, 14),
            ("أقراص كلوريلا عضوية", "أقراص كلوريلا عضوية لإزالة السموم", "Seeds", 38.00, True, 12),
            ("Raw Honey - Propolis Blend", "Raw honey infused with bee propolis.", "Honey", 75.00, True, 6),
            ("عسل بالعكبر", "عسل طبيعي ممزوج ببروبوليس النحل", "Honey", 78.00, True, 5),
            ("Coconut Cream Powder", "Organic coconut cream powder.", "Grocery", 20.00, True, 18),
            ("مسحوق كريمة جوز الهند", "مسحوق كريمة جوز هند عضوي", "Grocery", 22.00, True, 15),
            ("Acai Berry Powder", "Freeze-dried organic acai powder.", "Seeds", 45.00, True, 8),
        ],
        "سوبرماركت الوادي": [
            ("شاي أحمر فاخر", "شاي أحمر فاخر سيلاني أصلي", "Tea", 20.00, True, 40),
            ("Premium Black Tea", "Premium Ceylon black tea leaves.", "Tea", 22.00, True, 35),
            ("قهوة سريعة التحضير", "قهوة سريعة التحضير 3 في 1", "Coffee", 15.00, True, 60),
            ("3-in-1 Instant Coffee", "Instant coffee mix with milk and sugar.", "Coffee", 16.00, True, 55),
            ("سكر بني", "سكر بني طبيعي ناعم", "Grocery", 8.00, True, 45),
            ("Brown Sugar - Natural", "Natural soft brown sugar.", "Grocery", 9.00, True, 40),
            ("خل أبيض", "خل أبيض طبيعي للتنظيف والطبخ", "Grocery", 4.00, True, 50),
            ("White Vinegar", "Natural white vinegar for cooking.", "Grocery", 5.00, True, 45),
            ("نشاء ذرة", "نشاء ذرة ناعم للصلصات والحلويات", "Grocery", 3.00, True, 60),
            ("Cornstarch", "Fine cornstarch for sauces and desserts.", "Grocery", 4.00, True, 55),
            ("خميرة فورية", "خميرة فورية جافة للخبز", "Grocery", 2.00, True, 80),
            ("Instant Dry Yeast", "Instant dry yeast for baking bread.", "Grocery", 2.50, True, 75),
            ("بيكنغ باودر", "بيكنغ باودر للكيك والمعجنات", "Grocery", 3.00, True, 50),
            ("Baking Powder", "Baking powder for cakes and pastries.", "Grocery", 3.50, True, 45),
            ("فانيلا سائلة", "خلاصة فانيلا سائلة للحلويات", "Grocery", 5.00, True, 30),
            ("Vanilla Extract - Pure", "Pure vanilla extract for desserts.", "Grocery", 12.00, True, 15),
            ("كاكاو بودرة", "كاكاو بودرة هولندي للحلويات والمشروبات", "Grocery", 14.00, True, 25),
            ("Cocoa Powder - Dutch", "Dutch process cocoa powder.", "Grocery", 16.00, True, 22),
            ("شوكولاتة طبخ", "شوكولاتة طبخ غامقة للحلويات", "Grocery", 10.00, True, 30),
            ("Cooking Chocolate - Dark", "Dark cooking chocolate for desserts.", "Grocery", 12.00, True, 25),
            ("ماء ورد", "ماء ورد طبيعي للحلويات", "Essential Oils", 6.00, True, 35),
            ("Rose Water - Natural", "Natural rose water for desserts.", "Essential Oils", 7.00, True, 30),
            ("جيلاتين بودرة", "جيلاتين بودرة حلال للحلويات", "Grocery", 5.00, True, 35),
            ("Gelatin Powder - Halal", "Halal gelatin powder for desserts.", "Grocery", 6.00, True, 30),
            ("قشطة معلبة", "قشطة معلبة كثيفة للحلويات", "Grocery", 4.00, True, 50),
        ],
        "Royal Roastery": [
            ("Yemen Mocha Coffee", "Authentic Yemeni mocha coffee beans.", "Coffee", 65.00, True, 8),
            ("قهوة يمنية موكا", "بن يمني موكا أصلي فاخر", "Coffee", 68.00, True, 6),
            ("Costa Rican Coffee", "Single-origin Costa Rican beans.", "Coffee", 50.00, True, 12),
            ("قهوة كوستاريكية", "بن كوستاريكي أحادي المصدر", "Coffee", 52.00, True, 10),
            ("Kenyan AA Coffee", "Kenyan AA grade coffee beans.", "Coffee", 55.00, True, 10),
            ("قهوة كينية AA", "بن كيني درجة AA فاخر", "Coffee", 58.00, True, 8),
            ("Guatemala Antigua Coffee", "Guatemala Antigua estate coffee.", "Coffee", 48.00, True, 14),
            ("قهوة غواتيمالا أنتيغوا", "بن غواتيمالا أنتيغوا الفاخر", "Coffee", 50.00, True, 12),
            ("Jamaica Blue Mountain", "Rare Jamaica Blue Mountain coffee.", "Coffee", 120.00, True, 3),
            ("قهوة جامايكا الجبل الأزرق", "بن جامايكا الجبل الأزرق النادر", "Coffee", 125.00, True, 2),
            ("Cold Brew Blend", "Special cold brew coffee blend.", "Coffee", 42.00, True, 15),
            ("خلطة قهوة باردة", "خلطة بن خاصة للقهوة الباردة", "Coffee", 45.00, True, 12),
            ("Cappuccino Mix", "Instant cappuccino mix with foam.", "Coffee", 25.00, True, 25),
            ("كابتشينو جاهز", "خلطة كابتشينو فورية مع رغوة", "Coffee", 28.00, True, 22),
            ("Coffee Grinder Spice Set", "Coffee companion spice set.", "Spices", 35.00, True, 10),
            ("طقم بهارات القهوة", "مجموعة بهارات مرافقة للقهوة", "Spices", 38.00, True, 8),
            ("Robusta Coffee Beans", "Strong Indonesian robusta beans.", "Coffee", 32.00, True, 20),
            ("بن روبوستا إندونيسي", "بن روبوستا إندونيسي قوي", "Coffee", 35.00, True, 18),
            ("Coffee Filter Paper", "Unbleached coffee filter papers.", "Grocery", 8.00, True, 40),
            ("أوراق فلتر قهوة", "أوراق فلتر قهوة غير مبيضة", "Grocery", 9.00, True, 35),
            ("شاي تشاي هندي", "شاي تشاي هندي بالتوابل والحليب", "Tea", 18.00, True, 20),
            ("Indian Chai Tea", "Spiced Indian chai tea blend.", "Tea", 20.00, True, 18),
            ("عسل مع قرفة", "عسل طبيعي ممزوج بالقرفة السيلانية", "Honey", 55.00, True, 8),
            ("Cinnamon Honey", "Raw honey infused with Ceylon cinnamon.", "Honey", 58.00, True, 6),
            ("Espresso Cups - Arabic Style", "Traditional Arabic coffee cups set.", "Grocery", 25.00, True, 12),
        ],
        "مخبز ومعجنات السلط": [
            ("طحين خبز أبيض", "طحين خبز أبيض عالي البروتين", "Grocery", 5.00, True, 80),
            ("Bread Flour - Strong", "High protein strong bread flour.", "Grocery", 6.00, True, 70),
            ("طحين قمح كامل", "طحين قمح كامل عضوي", "Grocery", 7.00, True, 50),
            ("Whole Wheat Flour", "Organic whole wheat flour.", "Grocery", 8.00, True, 45),
            ("سميد ناعم", "سميد ناعم للحلويات والمعمول", "Grocery", 5.00, True, 60),
            ("Semolina - Fine", "Fine semolina for sweets and maamoul.", "Grocery", 6.00, True, 55),
            ("خميرة طازجة", "خميرة طازجة للخبز والمعجنات", "Grocery", 3.00, True, 40),
            ("Fresh Yeast", "Fresh baker's yeast for bread.", "Grocery", 4.00, True, 35),
            ("سمسم للخبز", "سمسم أبيض خام لتزيين الخبز", "Seeds", 8.00, True, 45),
            ("Sesame Seeds - White", "White sesame seeds for bread topping.", "Seeds", 9.00, True, 40),
            ("حبة بركة للخبز", "حبة البركة لتزيين الخبز والمعجنات", "Seeds", 10.00, True, 35),
            ("Black Seeds for Bread", "Black seeds for bread decoration.", "Seeds", 12.00, True, 30),
            ("بذور كتان للخبز", "بذور كتان ذهبية للخبز الصحي", "Seeds", 12.00, True, 30),
            ("Flaxseed for Baking", "Golden flaxseeds for healthy bread.", "Seeds", 14.00, True, 25),
            ("ماء زهر للمعمول", "ماء زهر طبيعي لعمل المعمول", "Essential Oils", 7.00, True, 30),
            ("Orange Blossom Water", "Natural orange blossom water for pastry.", "Essential Oils", 8.00, True, 25),
            ("تمر لحشوة المعمول", "عجينة تمر جاهزة لحشوة المعمول", "Dried Fruits", 15.00, True, 25),
            ("Date Paste for Maamoul", "Ready date paste filling for maamoul.", "Dried Fruits", 18.00, True, 20),
            ("فستق مطحون", "فستق حلبي مطحون للحلويات", "Dried Fruits", 55.00, True, 8),
            ("Ground Pistachios", "Ground pistachios for pastries.", "Dried Fruits", 58.00, True, 6),
            ("جوز مطحون", "جوز مطحون للحلويات والكيك", "Dried Fruits", 35.00, True, 12),
            ("Ground Walnuts", "Ground walnuts for sweets and cakes.", "Dried Fruits", 38.00, True, 10),
            ("عسل للمعجنات", "عسل طبيعي خفيف للمعجنات والحلويات", "Honey", 45.00, True, 10),
            ("Baking Honey - Light", "Light honey for baking and pastries.", "Honey", 48.00, True, 8),
            ("شاي بالقرفة", "شاي أسود بالقرفة الدافئة", "Tea", 14.00, True, 25),
        ],
        "Cedar Valley Provisions": [
            ("Lebanese Coffee - Fine", "Finely ground Lebanese coffee.", "Coffee", 30.00, True, 20),
            ("قهوة لبنانية ناعمة", "قهوة لبنانية مطحونة ناعمة", "Coffee", 32.00, True, 18),
            ("Cedar Honey - Lebanese", "Lebanese cedar mountain honey.", "Honey", 95.00, True, 5),
            ("عسل أرز لبناني", "عسل جبال الأرز اللبناني", "Honey", 100.00, True, 4),
            ("Pomegranate Molasses", "Traditional pomegranate molasses.", "Spreads", 14.00, True, 20),
            ("دبس رمان لبناني", "دبس رمان لبناني تقليدي أصلي", "Spreads", 16.00, True, 18),
            ("Mixed Nuts - Lebanese", "Lebanese style mixed nuts, roasted.", "Dried Fruits", 48.00, True, 15),
            ("مكسرات لبنانية مشكلة", "مكسرات مشكلة على الطريقة اللبنانية", "Dried Fruits", 50.00, True, 12),
            ("شاي أخضر بالهيل", "شاي أخضر مع الهيل والنعناع", "Tea", 18.00, True, 22),
            ("Green Tea with Cardamom", "Green tea infused with cardamom.", "Tea", 20.00, True, 20),
            ("Labneh Spread", "Thick strained yogurt spread.", "Spreads", 10.00, True, 25),
            ("لبنة مصفاة كثيفة", "لبنة مصفاة كثيفة للفطور", "Spreads", 12.00, True, 22),
            ("Grape Molasses", "Traditional grape molasses.", "Spreads", 12.00, True, 18),
            ("دبس عنب", "دبس عنب تقليدي حلو", "Spreads", 14.00, True, 15),
            ("Bulgur Wheat - Coarse", "Coarse bulgur for pilaf and salads.", "Grocery", 8.00, True, 35),
            ("برغل خشن", "برغل خشن للمجدرة والسلطات", "Grocery", 9.00, True, 30),
            ("Green Lentils", "Whole green lentils for cooking.", "Grocery", 8.00, True, 40),
            ("عدس أخضر", "عدس أخضر كامل للطبخ والمجدرة", "Grocery", 9.00, True, 35),
            ("Rose Petal Jam", "Delicate rose petal preserve.", "Spreads", 20.00, True, 10),
            ("مربى وردة", "مربى بتلات الورد الرقيق", "Spreads", 22.00, True, 8),
            ("Orange Blossom Honey", "Honey from orange tree blossoms.", "Honey", 70.00, True, 6),
            ("عسل أزهار البرتقال", "عسل أزهار شجر البرتقال الطبيعي", "Honey", 75.00, True, 5),
            ("شاي ميرامية بلدي", "شاي ميرامية بلدي من الجبال اللبنانية", "Tea", 15.00, True, 20),
            ("Wild Sage Tea - Mountain", "Mountain wild sage herbal tea.", "Tea", 18.00, True, 16),
            ("Sumac - Premium", "Premium ground sumac.", "Spices", 16.00, True, 22),
        ],
        "محل العسل الطبيعي": [
            ("عسل سدر حضرمي", "عسل سدر حضرمي يمني فاخر", "Honey", 200.00, True, 3),
            ("Hadrami Sidr Honey", "Premium Hadrami Yemeni Sidr honey.", "Honey", 210.00, True, 2),
            ("عسل سمرة", "عسل سمرة يمني داكن فاخر", "Honey", 140.00, True, 4),
            ("Sumra Honey - Dark", "Dark Yemeni Sumra honey, premium.", "Honey", 145.00, True, 3),
            ("عسل طلح", "عسل طلح سعودي من المنطقة الجنوبية", "Honey", 110.00, True, 5),
            ("Talh Honey - Saudi", "Saudi Talh acacia honey.", "Honey", 115.00, True, 4),
            ("عسل مجرى", "عسل مجرى طبيعي ذهبي", "Honey", 80.00, True, 8),
            ("Hungarian Acacia Honey", "Natural golden Hungarian acacia honey.", "Honey", 85.00, True, 6),
            ("عسل كشميري", "عسل كشميري طبيعي نادر", "Honey", 130.00, True, 3),
            ("Kashmiri Honey - Rare", "Rare natural Kashmiri honey.", "Honey", 135.00, True, 2),
            ("عسل مانوكا UMF 15+", "عسل مانوكا نيوزيلندي UMF 15+", "Honey", 250.00, True, 2),
            ("Manuka Honey UMF 15+", "New Zealand Manuka honey UMF 15+.", "Honey", 260.00, True, 2),
            ("عسل مانوكا UMF 20+", "عسل مانوكا نيوزيلندي UMF 20+", "Honey", 350.00, True, 1),
            ("Manuka Honey UMF 20+", "New Zealand Manuka honey UMF 20+.", "Honey", 360.00, True, 1),
            ("غذاء ملكات النحل", "غذاء ملكات النحل الطازج المجمد", "Honey", 90.00, True, 5),
            ("Royal Jelly - Fresh Frozen", "Fresh frozen royal jelly.", "Honey", 95.00, True, 4),
            ("حبوب لقاح النحل", "حبوب لقاح النحل الطبيعية", "Honey", 40.00, True, 10),
            ("Bee Pollen - Raw", "Raw natural bee pollen granules.", "Honey", 45.00, True, 8),
            ("عكبر (بروبوليس)", "عكبر النحل الطبيعي المستخلص", "Honey", 60.00, True, 6),
            ("Propolis Extract", "Natural bee propolis extract.", "Honey", 65.00, True, 5),
            ("شمع عسل طبيعي", "شمع عسل طبيعي مع العسل", "Honey", 50.00, True, 8),
            ("Honeycomb - Raw", "Raw natural honeycomb.", "Honey", 55.00, True, 6),
            ("عسل بالزنجبيل", "عسل طبيعي ممزوج بالزنجبيل الطازج", "Honey", 55.00, True, 7),
            ("Ginger Honey", "Raw honey infused with fresh ginger.", "Honey", 58.00, True, 6),
            ("عسل أسود (عسل الغابة)", "عسل الغابة الأسود الكثيف والمغذي", "Honey", 120.00, True, 3),
        ],
    }

    for market_name, products in market_product_sets.items():
        for p in products:
            all_products.append({
                "market_name": market_name,
                "name": p[0],
                "description": p[1],
                "category": p[2],
                "price": p[3],
                "in_stock": p[4],
                "stock_count": p[5],
            })

    return all_products


PRODUCTS = _build_products()


async def seed(reset: bool = False):
    """Populate the database and Elasticsearch with sample data.

    By default this is now NON-destructive: it relies on idempotent upserts
    (the existing ``existing = select(...)`` checks) so re-running the seeder
    no longer wipes real users, ratings, chats, and search history.

    Pass ``reset=True`` (or ``--reset`` on the CLI) to recreate the schema —
    only intended for fresh dev databases.
    """

    if reset:
        async with engine.begin() as conn:
            logger.info("Reset mode: dropping existing database tables...")
            await conn.run_sync(Base.metadata.drop_all)
            logger.info("Recreating database tables...")
            await conn.run_sync(Base.metadata.create_all)
    else:
        # Ensure the schema exists (idempotent) without wiping existing data
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Load embedding models
    embedding_service.load_model()

    # Init Elasticsearch
    es = init_es_client()
    
    # Drop index if it exists
    if await es.indices.exists(index=settings.elasticsearch_index):
        logger.info(f"Deleting existing Elasticsearch index: {settings.elasticsearch_index}")
        await es.indices.delete(index=settings.elasticsearch_index)
        
    indexer = IndexerService(es)
    await indexer.ensure_index()

    async with async_session() as db:
        # ── Create Categories ───────────────────────────────
        root_food = Category(name="Food & Beverages")
        root_care = Category(name="Home & Personal Care")
        root_tech = Category(name="Electronics & Tech")
        root_kitchen = Category(name="Home & Kitchen")
        db.add_all([root_food, root_care, root_tech, root_kitchen])
        await db.flush()

        subcategories = [
            ("Fruits & Vegetables", root_food.id),
            ("Cooking Essentials", root_food.id),
            ("Dairy & Eggs", root_food.id),
            ("Meat & Poultry", root_food.id),
            ("Beverages", root_food.id),
            ("Snacks", root_food.id),
            ("Bakery", root_food.id),
            ("Frozen Food", root_food.id),
            ("Cleaning & Detergents", root_care.id),
            ("Beauty & Personal Care", root_care.id),
            ("Electronics", root_tech.id),
            ("Mobiles & Tech", root_tech.id),
            ("Cookware & Kitchenware", root_kitchen.id),
        ]

        cat_map = {}
        for name, parent_id in subcategories:
            sub = Category(name=name, parent_category_id=parent_id)
            db.add(sub)
            await db.flush()
            cat_map[name] = sub

        # ── Create Merchants ────────────────────────────────
        user_map = {}
        for m in MERCHANTS:
            existing = await db.execute(select(User).where(User.email == m["email"]))
            user = existing.scalar_one_or_none()
            if user is None:
                user = User(
                    email=m["email"],
                    password_hash=hash_password(m["password"]),
                    user_type="merchant",
                    verified=True,
                )
                db.add(user)
                await db.flush()
                logger.info(f"Created merchant: {m['email']}")
            user_map[m["email"]] = user

        # ── Create Customers ────────────────────────────────
        for c in CUSTOMERS:
            existing = await db.execute(select(User).where(User.email == c["email"]))
            user = existing.scalar_one_or_none()
            if user is None:
                user = User(
                    email=c["email"],
                    password_hash=hash_password(c["password"]),
                    user_type="customer",
                    verified=True,
                )
                db.add(user)
                await db.flush()
                logger.info(f"Created customer: {c['email']}")

        # ── Create Markets ──────────────────────────────────
        market_map = {}
        for s in MARKETS:
            existing = await db.execute(select(Market).where(Market.name == s["name"]))
            market = existing.scalar_one_or_none()
            if market is None:
                owner = user_map[s["merchant_email"]]
                market = Market(
                    merchant_id=owner.id,
                    name=s["name"],
                    business_nature=s["business_nature"],
                    address=s["address"],
                    phone=s.get("phone"),
                    operating_hours=s["operating_hours"],
                    employee_directory=s["employee_directory"],
                    location=WKTElement(f"POINT({s['longitude']} {s['latitude']})", srid=4326),
                )
                db.add(market)
                await db.flush()
                logger.info(f"Created market: {s['name']}")
            market_map[s["name"]] = {"market": market, "lat": s["latitude"], "lng": s["longitude"]}

        # ── Create GlobalItems and MarketItems + Index ──────
        products_to_index = []
        total = len(PRODUCTS)
        for idx, p in enumerate(PRODUCTS, 1):
            market_info = market_map[p["market_name"]]
            market = market_info["market"]

            # Create or get GlobalItem
            existing_gi = await db.execute(
                select(GlobalItem).where(GlobalItem.name == p["name"])
            )
            gi = existing_gi.unique().scalar_one_or_none()
            if gi is None:
                # Generate embeddings
                combined_text = p["name"]
                if p["description"]:
                    combined_text = f"{p['name']}. {p['description']}"
                
                text_vector = embedding_service.encode_text_384(combined_text).tolist()
                image_vector = embedding_service.encode_product(p["name"], p["description"]).tolist()
                
                # Map old category names to new hypermarket taxonomy
                old_category = p["category"]
                category_mapping = {
                    "Tea": "Beverages",
                    "Coffee": "Beverages",
                    "Honey": "Cooking Essentials",
                    "Oils": "Cooking Essentials",
                    "Spices": "Cooking Essentials",
                    "Seeds": "Cooking Essentials",
                    "Spreads": "Cooking Essentials",
                    "Essential Oils": "Beauty & Personal Care",
                    "Grocery": "Cooking Essentials",
                    "Dried Fruits": "Snacks"
                }
                new_category = category_mapping.get(old_category, "Cooking Essentials")
                category_obj = cat_map.get(new_category)
                if not category_obj:
                    category_obj = cat_map.get("Cooking Essentials")
                
                gi = GlobalItem(
                    name=p["name"],
                    description=p["description"],
                    category_id=category_obj.id,
                    barcode=f"628101{str(idx).zfill(7)}",
                    text_embedding=text_vector,
                    image_embedding=image_vector,
                )
                db.add(gi)
                await db.flush()

                # No on-disk mock images are generated, so leave image_url=None to let the
                # React Native app render its placeholder instead of a broken
                # image (the legacy /uploads/mock_*.jpg paths returned 404).
                primary_image = ProductImage(
                    global_item_id=gi.id,
                    image_url=None,
                    is_primary=True
                )
                secondary_image = ProductImage(
                    global_item_id=gi.id,
                    image_url=None,
                    is_primary=False
                )
                db.add_all([primary_image, secondary_image])
                await db.flush()
                
                logger.info(f"[{idx}/{total}] Created global item & images: {p['name']}")
            else:
                logger.info(f"[{idx}/{total}] Reusing existing global item: {p['name']}")

            # Create or get MarketItem link
            existing_mi = await db.execute(
                select(MarketItem).where(
                    MarketItem.market_id == market.id,
                    MarketItem.item_id == gi.id
                )
            )
            mi = existing_mi.scalar_one_or_none()
            if mi is None:
                mi = MarketItem(
                    market_id=market.id,
                    item_id=gi.id,
                    stock_count=p["stock_count"],
                    status=p["in_stock"],
                    price=p["price"],
                )
                db.add(mi)
                await db.flush()
                logger.info(f"  Linked item {p['name']} to market {p['market_name']}")

            # Prepare document for Elasticsearch
            products_to_index.append({
                "product_id": mi.id,
                "shop_id": market.id,
                "name": gi.name,
                "description": gi.description,
                "price": p["price"],
                "category": gi.category,
                "image_url": gi.image_url,
                "in_stock": mi.status,
                "latitude": market_info["lat"],
                "longitude": market_info["lng"],
                "embedding": gi.image_embedding,
            })

        await db.commit()

        # Bulk index all products in Elasticsearch
        indexed = await indexer.bulk_index(products_to_index)
        logger.info(f"Indexed {indexed} items in Elasticsearch")

    await close_es_client()
    logger.info(f"Seed complete! Total products: {total}, Markets: {len(MARKETS)}, Merchants: {len(MERCHANTS)}")


if __name__ == "__main__":
    import sys
    reset = "--reset" in sys.argv
    asyncio.run(seed(reset=reset))
