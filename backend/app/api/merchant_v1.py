"""
Merchant V1 API — Market initialization, inventory checks, linking, and AI-driven item ingestion.

Endpoints:
  GET  /api/v1/merchant/market              — Check if merchant has a market
  POST /api/v1/merchant/market              — Register physical store parameters (PostGIS)
  GET  /api/v1/merchant/market/items        — Fetch all merchant stocked inventory
  PATCH /api/v1/merchant/market/items/{id}/stock — Toggle stock status
  POST /api/v1/merchant/items/check          — Case-insensitive fuzzy name search
  POST /api/v1/merchant/items/link           — Link catalog item to merchant market
  POST /api/v1/merchant/items/new            — Ingest brand-new item via CLIP/MiniLM AI
"""

import os
import uuid
import logging
from typing import Annotated, List, Optional
import numpy as np

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from geoalchemy2.elements import WKTElement
from geoalchemy2 import Geometry
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.market import Market
from app.models.category import Category
from app.models.global_item import GlobalItem
from app.models.product_image import ProductImage
from app.models.market_item import MarketItem
from app.models.pos_receipt import POSReceipt, POSReceiptItem
from app.api.auth import get_current_user
from app.schemas.merchant_v1 import (
    MarketCreate, MarketResponse, MarketStatusUpdateRequest,
    ItemCheckRequest, ItemCheckResponse, CatalogItemMatch,
    ItemLinkRequest, ItemLinkResponse,
    MarketItemDashboardResponse, StockToggleRequest,
    ItemUpdateRequest, BarcodeLookupResponse, CheckoutRequest
)
from app.schemas.special_offer import (
    SpecialOfferCreate,
    SpecialOfferUpdate,
    SpecialOfferResponse
)
from app.services.embedding import embedding_service
from app.services.indexer import IndexerService
from app.services.alert_service import check_and_trigger_stock_alerts
from app.es_client import get_es_client
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/merchant", tags=["Merchant V1"])


def get_merchant(user: User = Depends(get_current_user)) -> User:
    """Safe check verifying user has merchant privileges (handles both user_type & role)."""
    role = getattr(user, "user_type", None) or getattr(user, "role", None)
    if role != "merchant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant access required",
        )
    return user


# ── GET /market ─────────────────────────────────────────────────
@router.get("/market", response_model=MarketResponse)
async def get_market(
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the merchant's physical market profile, if initialized."""
    result = await db.execute(
        select(
            Market,
            func.ST_Y(Market.location.cast(Geometry)).label("lat"),
            func.ST_X(Market.location.cast(Geometry)).label("lng")
        ).where(Market.merchant_id == user.id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found. Complete onboarding first.",
        )
    
    market, lat, lng = row[0], row[1], row[2]
    
    # Run dynamic schedule update to ensure freshness
    from app.utils.schedule import check_and_update_markets_schedule
    await check_and_update_markets_schedule(db, [market])
    
    return MarketResponse(
        id=market.id,
        merchant_id=market.merchant_id,
        name=market.name,
        address=market.address,
        latitude=float(lat),
        longitude=float(lng),
        business_nature=market.business_nature,
        operating_hours=market.operating_hours,
        employee_directory=market.employee_directory,
        is_currently_open=market.is_currently_open,
        is_manual_override=market.is_manual_override,
        override_set_at=market.override_set_at,
        created_at=market.created_at,
    )


# ── POST /market ────────────────────────────────────────────────
@router.post("/market", response_model=MarketResponse, status_code=201)
async def create_market(
    data: MarketCreate,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Initialize a merchant's physical market profile (PostGIS point integration)."""
    # Check if a market is already initialized with the exact same name for this merchant
    existing = await db.execute(
        select(Market).where(
            Market.merchant_id == user.id,
            Market.name == data.name
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A market with this name is already registered for this merchant.",
        )
    
    market = Market(
        merchant_id=user.id,
        name=data.name,
        address=data.address,
        business_nature=data.business_nature,
        operating_hours=data.operating_hours,
        employee_directory=data.employee_directory,
        location=WKTElement(f"POINT({data.longitude} {data.latitude})", srid=4326),
        is_currently_open=data.is_currently_open if data.is_currently_open is not None else True,
    )
    db.add(market)
    await db.flush()
    
    return MarketResponse(
        id=market.id,
        merchant_id=market.merchant_id,
        name=market.name,
        address=market.address,
        latitude=data.latitude,
        longitude=data.longitude,
        business_nature=market.business_nature,
        operating_hours=market.operating_hours,
        employee_directory=market.employee_directory,
        is_currently_open=market.is_currently_open,
        is_manual_override=market.is_manual_override,
        override_set_at=market.override_set_at,
        created_at=market.created_at,
    )


# ── PATCH /market/status ────────────────────────────────────────
@router.patch("/market/status", response_model=MarketResponse)
async def update_market_status(
    data: MarketStatusUpdateRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Dynamically toggle the merchant's physical market status (Open / Closed or Revert to Auto)."""
    result = await db.execute(
        select(Market).where(Market.merchant_id == user.id)
    )
    market = result.scalar_one_or_none()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found. Complete onboarding first.",
        )
    
    from datetime import datetime, timezone, timedelta
    from app.utils.schedule import calculate_is_open_by_schedule
    
    if data.is_manual_override:
        market.is_manual_override = True
        market.is_currently_open = data.is_currently_open if data.is_currently_open is not None else True
        market.override_set_at = datetime.now(timezone(timedelta(hours=3)))
    else:
        # Revert to schedule
        market.is_manual_override = False
        market.override_set_at = None
        jordan_tz = timezone(timedelta(hours=3))
        now_jordan = datetime.now(jordan_tz)
        market.is_currently_open = calculate_is_open_by_schedule(market.operating_hours, now_jordan)
        
    await db.commit()
    
    # Re-fetch with Lat/Lng coordinates
    result = await db.execute(
        select(
            Market,
            func.ST_Y(Market.location.cast(Geometry)).label("lat"),
            func.ST_X(Market.location.cast(Geometry)).label("lng")
        ).where(Market.id == market.id)
    )
    row = result.first()
    market, lat, lng = row[0], row[1], row[2]
    
    return MarketResponse(
        id=market.id,
        merchant_id=market.merchant_id,
        name=market.name,
        address=market.address,
        latitude=float(lat),
        longitude=float(lng),
        business_nature=market.business_nature,
        operating_hours=market.operating_hours,
        employee_directory=market.employee_directory,
        is_currently_open=market.is_currently_open,
        is_manual_override=market.is_manual_override,
        override_set_at=market.override_set_at,
        created_at=market.created_at,
    )


# ── GET /market/items ───────────────────────────────────────────
@router.get("/market/items", response_model=List[MarketItemDashboardResponse])
async def get_market_items(
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all global items stocked at the merchant's market."""
    result = await db.execute(
        select(MarketItem, GlobalItem)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(Market.merchant_id == user.id)
        .order_by(GlobalItem.name)
    )
    
    items = []
    for row in result.unique().all():
        mi, gi = row[0], row[1]
        items.append(MarketItemDashboardResponse(
            id=mi.id,
            item_id=gi.id,
            name=gi.name,
            description=gi.description,
            category=gi.category,
            image_url=gi.image_url,
            stock_count=mi.stock_count,
            in_stock=mi.status,
            price=mi.price,
        ))
    return items


# ── PATCH /market/items/{item_id}/stock ─────────────────────────
@router.patch("/market/items/{item_id}/stock", response_model=MarketItemDashboardResponse)
async def toggle_stock(
    item_id: uuid.UUID,
    data: StockToggleRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Toggle stock availability status in database and Elasticsearch."""
    result = await db.execute(
        select(MarketItem, GlobalItem)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(MarketItem.id == item_id, Market.merchant_id == user.id)
    )
    row = result.unique().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market item not found.",
        )
    
    mi, gi = row[0], row[1]
    mi.status = data.in_stock
    await db.flush()

    if data.in_stock:
        await check_and_trigger_stock_alerts(db, mi.id)
    
    # Elasticsearch update
    try:
        es_client = get_es_client()
        indexer = IndexerService(es_client)
        await indexer.update_stock(mi.id, data.in_stock)
    except Exception as e:
        logger.error(f"Elasticsearch stock toggle sync failed: {e}")
        
    return MarketItemDashboardResponse(
        id=mi.id,
        item_id=gi.id,
        name=gi.name,
        description=gi.description,
        category=gi.category,
        image_url=gi.image_url,
        stock_count=mi.stock_count,
        in_stock=mi.status,
        price=mi.price,
    )


# ── PATCH /market/items/{item_id} ───────────────────────────────
@router.patch("/market/items/{item_id}", response_model=MarketItemDashboardResponse)
async def update_market_item(
    item_id: uuid.UUID,
    data: ItemUpdateRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Update a market item's stock count, price/cost, or name in DB and Elasticsearch."""
    result = await db.execute(
        select(MarketItem, GlobalItem, Market,
               func.ST_Y(Market.location.cast(Geometry)).label("lat"),
               func.ST_X(Market.location.cast(Geometry)).label("lng"))
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(MarketItem.id == item_id, Market.merchant_id == user.id)
    )
    row = result.unique().first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market item not found.",
        )
    
    mi, gi, market, lat, lng = row[0], row[1], row[2], row[3], row[4]
    
    if data.name is not None:
        gi.name = data.name
    if data.stock_count is not None:
        mi.stock_count = data.stock_count
        # Auto-update status based on stock count
        if data.stock_count == 0:
            mi.status = False
        else:
            mi.status = True
    if data.price is not None:
        mi.price = data.price
        
    await db.flush()
    if mi.status:
        await check_and_trigger_stock_alerts(db, mi.id)
    await db.commit()
    
    # Elasticsearch update
    try:
        es_client = get_es_client()
        indexer = IndexerService(es_client)
        
        # Re-compute embedding if name changed
        embedding = None
        if data.name is not None:
            combined_text = gi.name
            if gi.description:
                combined_text = f"{gi.name}. {gi.description}"
            # Re-generate text vector (MiniLM) and image vector (CLIP)
            text_vec = embedding_service.encode_text_384(combined_text).tolist()
            image_vec = embedding_service.encode_product(gi.name, gi.description).tolist()
            gi.text_embedding = text_vec
            gi.image_embedding = image_vec
            await db.flush()
            await db.commit()
            embedding = np.array(image_vec)
            
        await indexer.index_product(
            product_id=mi.id,
            shop_id=market.id,
            name=gi.name,
            description=gi.description,
            price=float(mi.price) if mi.price is not None else None,
            category=gi.category,
            image_url=gi.image_url,
            in_stock=mi.status,
            latitude=float(lat),
            longitude=float(lng),
            embedding=embedding
        )
    except Exception as e:
        logger.error(f"Elasticsearch update item sync failed: {e}")
        
    return MarketItemDashboardResponse(
        id=mi.id,
        item_id=gi.id,
        name=gi.name,
        description=gi.description,
        category=gi.category,
        image_url=gi.image_url,
        stock_count=mi.stock_count,
        in_stock=mi.status,
        price=mi.price,
    )


# ── POST /items/check ───────────────────────────────────────────
@router.post("/items/check", response_model=ItemCheckResponse)
async def check_item(
    data: ItemCheckRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Search for existing catalog items matching the search string (case-insensitive fuzzy)."""
    result = await db.execute(
        select(GlobalItem)
        .where(GlobalItem.name.ilike(f"%{data.item_name}%"))
        .limit(10)
    )
    matches = result.unique().scalars().all()
    
    return ItemCheckResponse(
        exists=len(matches) > 0,
        matches=[CatalogItemMatch.model_validate(gi) for gi in matches]
    )


# ── POST /items/link ────────────────────────────────────────────
@router.post("/items/link", response_model=ItemLinkResponse)
async def link_item(
    data: ItemLinkRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Link an existing catalog item to the merchant's physical market."""
    # Verify market owner
    market_result = await db.execute(
        select(Market,
               func.ST_Y(Market.location.cast(Geometry)).label("lat"),
               func.ST_X(Market.location.cast(Geometry)).label("lng"))
        .where(Market.id == data.market_id, Market.merchant_id == user.id)
    )
    market_row = market_result.first()
    if not market_row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your market.",
        )
    market, lat, lng = market_row[0], market_row[1], market_row[2]
    
    # Get GlobalItem details
    gi_result = await db.execute(select(GlobalItem).where(GlobalItem.id == data.item_id))
    gi = gi_result.unique().scalar_one_or_none()
    if not gi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catalog item not found.",
        )
        
    # Check if already linked
    existing = await db.execute(
        select(MarketItem).where(
            MarketItem.market_id == data.market_id,
            MarketItem.item_id == data.item_id
        )
    )
    mi = existing.scalar_one_or_none()
    
    if mi:
        mi.stock_count += data.stock_count
        mi.status = True
        message = f"Stock incremented by {data.stock_count} for existing item."
    else:
        mi = MarketItem(
            market_id=data.market_id,
            item_id=data.item_id,
            stock_count=data.stock_count,
            status=True
        )
        db.add(mi)
        message = "New catalog item successfully linked to your market."
        
    await db.flush()
    await check_and_trigger_stock_alerts(db, mi.id)
    
    # Index in Elasticsearch
    try:
        es_client = get_es_client()
        indexer = IndexerService(es_client)
        
        # Format embedding vector
        embedding = gi.image_embedding if gi.image_embedding is not None else gi.text_embedding
        if embedding is not None:
            embedding = np.array(embedding)
        else:
            embedding = embedding_service.encode_product(gi.name, gi.description)
            
        await indexer.index_product(
            product_id=mi.id,
            shop_id=market.id,
            name=gi.name,
            description=gi.description,
            price=None,
            category=gi.category,
            image_url=gi.image_url,
            in_stock=True,
            latitude=float(lat),
            longitude=float(lng),
            embedding=embedding
        )
    except Exception as e:
        logger.error(f"Elasticsearch indexing link failed: {e}")
        
    return ItemLinkResponse(
        success=True,
        message=message,
        market_item_id=mi.id,
        stock_count=mi.stock_count
    )


# ── POST /items/new ─────────────────────────────────────────────
def _classify_category(name: str, description: str | None) -> str:
    """Heuristic categorizer parsing product name and description into the new 13 categories."""
    text = (name + " " + (description or "")).lower()
    
    # 1. Fruits & Vegetables
    if any(k in text for k in ["fruit", "vegetable", "tomato", "banana", "apple", "orange", "lemon", "potato", "onion", "mint", "lettuce", "garlic", "cucumber"]):
        return "Fruits & Vegetables"
    # 2. Dairy & Eggs
    if any(k in text for k in ["milk", "egg", "eggs", "cheese", "yogurt", "butter", "dairy", "cream"]):
        return "Dairy & Eggs"
    # 3. Meat & Poultry
    if any(k in text for k in ["chicken", "meat", "beef", "lamb", "poultry", "turkey", "steak", "sausage"]):
        return "Meat & Poultry"
    # 4. Beverages
    if any(k in text for k in ["tea", "coffee", "espresso", "juice", "soda", "water", "drink", "beverage", "cola", "nescafe"]):
        return "Beverages"
    # 5. Snacks
    if any(k in text for k in ["snack", "chips", "chocolate", "biscuit", "cookie", "crisps", "nut", "nuts", "candy", "sweet"]):
        return "Snacks"
    # 6. Bakery
    if any(k in text for k in ["bread", "bakery", "croissant", "muffin", "cake", "toast", "bun"]):
        return "Bakery"
    # 7. Frozen Food
    if any(k in text for k in ["frozen", "ice cream", "nuggets"]):
        return "Frozen Food"
    # 8. Cleaning & Detergents
    if any(k in text for k in ["clean", "detergent", "soap", "dishwash", "laundry", "bleach", "shampoo"]):
        return "Cleaning & Detergents"
    # 9. Beauty & Personal Care
    if any(k in text for k in ["beauty", "personal care", "cream", "lotion", "cosmetic", "makeup", "perfume", "oil"]):
        if "essential oil" in text or "skin" in text or "face" in text or "hair" in text:
            return "Beauty & Personal Care"
    # 10. Cooking Essentials
    if any(k in text for k in ["oil", "olive oil", "spice", "spices", "honey", "seed", "seeds", "salt", "sugar", "flour", "vinegar", "saffron", "turmeric", "cardamom", "spread", "peanut butter"]):
        return "Cooking Essentials"
    # 11. Mobiles & Tech
    if any(k in text for k in ["phone", "mobile", "charger", "headphone", "earbuds", "cable", "screen protector"]):
        return "Mobiles & Tech"
    # 12. Cookware & Kitchenware
    if any(k in text for k in ["pot", "pan", "cookware", "kitchenware", "plate", "spoon", "fork", "knife", "cup", "mug"]):
        return "Cookware & Kitchenware"
    # 13. Electronics
    if any(k in text for k in ["electric", "vacuum", "oven", "tv", "refrigerator", "fridge", "microwave", "appliance"]):
        return "Electronics"
        
    return "Cooking Essentials"



@router.post("/items/new", response_model=ItemLinkResponse)
async def create_new_item(
    market_id: uuid.UUID = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    barcode: Optional[str] = Form(None),
    stock_count: int = Form(0),
    price: Optional[float] = Form(None),
    image: UploadFile = File(...),
    secondary_images: List[UploadFile] = File(default=[]),
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a brand-new catalog item utilizing local CLIP/MiniLM embedding models."""
    # Verify market ownership
    market_result = await db.execute(
        select(Market,
               func.ST_Y(Market.location.cast(Geometry)).label("lat"),
               func.ST_X(Market.location.cast(Geometry)).label("lng"))
        .where(Market.id == market_id, Market.merchant_id == user.id)
    )
    market_row = market_result.first()
    if not market_row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your market.",
        )
    market, lat, lng = market_row[0], market_row[1], market_row[2]
    
    # Save Primary Upload Image
    os.makedirs(settings.upload_dir, exist_ok=True)
    file_ext = os.path.splitext(image.filename)[1] or ".jpg"
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(settings.upload_dir, unique_filename)
    
    image_bytes = await image.read()
    with open(file_path, "wb") as f:
        f.write(image_bytes)
        
    primary_image_url = f"/uploads/{unique_filename}"
    
    # Save Secondary Upload Images
    secondary_urls = []
    for sec_file in secondary_images:
        if sec_file.filename:
            sec_ext = os.path.splitext(sec_file.filename)[1] or ".jpg"
            sec_unique = f"{uuid.uuid4()}{sec_ext}"
            sec_path = os.path.join(settings.upload_dir, sec_unique)
            sec_bytes = await sec_file.read()
            with open(sec_path, "wb") as f:
                f.write(sec_bytes)
            secondary_urls.append(f"/uploads/{sec_unique}")
    
    # Gemma VLM Extraction: refine name, description and auto-categorize from image
    vlm_details = None
    try:
        vlm_details = embedding_service.extract_product_details_vlm(image_bytes, name, description)
    except Exception as e:
        logger.error(f"Gemma VLM inference failed: {e}")
        
    refined_name = name
    refined_desc = description
    category_name = None
    
    if vlm_details:
        refined_name = vlm_details.get("name", name)
        refined_desc = vlm_details.get("description", description)
        category_name = vlm_details.get("category")
        logger.info(f"VLM successfully extracted product details: name='{refined_name}', category='{category_name}'")
        
    if not category_name:
        # Fallback to Heuristic NLP Classification
        category_name = _classify_category(name, description)
        
    cat_result = await db.execute(select(Category).where(Category.name == category_name))
    cat = cat_result.scalar_one_or_none()
    if not cat:
        cat = Category(name=category_name)
        db.add(cat)
        await db.flush()
    
    # Generate 512-d image vector (CLIP)
    image_vector = None
    try:
        image_vector = embedding_service.encode_image_bytes(image_bytes)
    except Exception as e:
        logger.error(f"CLIP encoding failed: {e}")
        
    # Generate 384-d text vector (MiniLM) using refined VLM/English metadata
    text_vector = None
    try:
        text = refined_name
        if refined_desc:
            text = f"{refined_name}. {refined_desc}"
        text_vector = embedding_service.encode_text_384(text)
    except Exception as e:
        logger.error(f"MiniLM encoding failed: {e}")
        
    # Save GlobalItem (preserves original inputs for display, uses VLM/translated vectors)
    gi = GlobalItem(
        name=name,
        description=description,
        barcode=barcode,
        category_id=cat.id,
        text_embedding=text_vector.tolist() if text_vector is not None else None,
        image_embedding=image_vector.tolist() if image_vector is not None else None,
        created_by=user.id
    )
    db.add(gi)
    await db.flush()

    # Save Primary Image Record
    primary_img = ProductImage(
        global_item_id=gi.id,
        image_url=primary_image_url,
        is_primary=True
    )
    db.add(primary_img)

    # Save Secondary Image Records
    for sec_url in secondary_urls:
        sec_img = ProductImage(
            global_item_id=gi.id,
            image_url=sec_url,
            is_primary=False
        )
        db.add(sec_img)
    
    await db.flush()
    
    # Link MarketItem
    mi = MarketItem(
        market_id=market_id,
        item_id=gi.id,
        stock_count=stock_count,
        price=price,
        status=True
    )
    db.add(mi)
    await db.flush()
    await check_and_trigger_stock_alerts(db, mi.id)
    
    # Index in Elasticsearch (CLIP ViT-B-32 512-d space)
    try:
        es_client = get_es_client()
        indexer = IndexerService(es_client)
        
        embedding = image_vector if image_vector is not None else embedding_service.encode_product(name, description)
        
        await indexer.index_product(
            product_id=mi.id,
            shop_id=market.id,
            name=gi.name,
            description=gi.description,
            price=price,
            category=gi.category,
            image_url=gi.image_url,
            in_stock=True,
            latitude=float(lat),
            longitude=float(lng),
            embedding=embedding
        )
    except Exception as e:
        logger.error(f"Elasticsearch indexing new item failed: {e}")
        
    return ItemLinkResponse(
        success=True,
        message="Brand-new product ingested via AI pipeline and added to stock.",
        market_item_id=mi.id,
        stock_count=mi.stock_count
    )


# ── GET /offers ─────────────────────────────────────────────────
@router.get("/offers", response_model=List[SpecialOfferResponse])
async def get_merchant_offers(
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all special offers for the merchant's physical market."""
    from app.models.special_offer import SpecialOffer
    
    result = await db.execute(
        select(SpecialOffer, MarketItem, GlobalItem)
        .join(MarketItem, SpecialOffer.market_item_id == MarketItem.id)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(Market.merchant_id == user.id)
        .order_by(SpecialOffer.created_at.desc())
    )
    
    offers = []
    for row in result.unique().all():
        so, mi, gi = row[0], row[1], row[2]
        offers.append(
            SpecialOfferResponse(
                id=so.id,
                market_item_id=so.market_item_id,
                offer_type=so.offer_type,
                discount_percentage=so.discount_percentage,
                description=so.description,
                power=so.power,
                is_active=so.is_active,
                created_at=so.created_at,
                name=gi.name,
                category=gi.category,
                image_url=gi.image_url,
                price=mi.price,
                stock_count=mi.stock_count,
            )
        )
    return offers


# ── POST /offers ────────────────────────────────────────────────
@router.post("/offers", response_model=SpecialOfferResponse, status_code=201)
async def create_special_offer(
    data: SpecialOfferCreate,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new special offer for the merchant's physical store."""
    from app.models.special_offer import SpecialOffer

    # Verify that the target market item actually belongs to the merchant
    result = await db.execute(
        select(MarketItem, GlobalItem, Market)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(MarketItem.id == data.market_item_id, Market.merchant_id == user.id)
    )
    row = result.unique().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden. Target market item does not exist or does not belong to your shop.",
        )
    
    mi, gi, market = row[0], row[1], row[2]

    # Calculate inherent power score
    if data.offer_type.upper() == "BOGO":
        power = 100.0
    elif data.offer_type.upper() == "DISCOUNT":
        power = float(data.discount_percentage) if data.discount_percentage is not None else 50.0
    else:
        power = 50.0

    so = SpecialOffer(
        market_item_id=data.market_item_id,
        offer_type=data.offer_type.upper(),
        discount_percentage=data.discount_percentage,
        description=data.description,
        power=power,
        is_active=True,
    )
    db.add(so)
    await db.flush()

    return SpecialOfferResponse(
        id=so.id,
        market_item_id=so.market_item_id,
        offer_type=so.offer_type,
        discount_percentage=so.discount_percentage,
        description=so.description,
        power=so.power,
        is_active=so.is_active,
        created_at=so.created_at,
        name=gi.name,
        category=gi.category,
        image_url=gi.image_url,
        price=mi.price,
        stock_count=mi.stock_count,
    )


# ── PATCH /offers/{offer_id} ────────────────────────────────────
@router.patch("/offers/{offer_id}", response_model=SpecialOfferResponse)
async def update_special_offer(
    offer_id: uuid.UUID,
    data: SpecialOfferUpdate,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Toggle status, modify discount percentage, or edit details of a special offer."""
    from app.models.special_offer import SpecialOffer

    result = await db.execute(
        select(SpecialOffer, MarketItem, GlobalItem, Market)
        .join(MarketItem, SpecialOffer.market_item_id == MarketItem.id)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(SpecialOffer.id == offer_id, Market.merchant_id == user.id)
    )
    row = result.unique().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Special offer not found or does not belong to your shop.",
        )
    
    so, mi, gi, market = row[0], row[1], row[2], row[3]

    if data.is_active is not None:
        so.is_active = data.is_active
    if data.discount_percentage is not None:
        so.discount_percentage = data.discount_percentage
        if so.offer_type.upper() == "DISCOUNT":
            so.power = float(data.discount_percentage)
    if data.description is not None:
        so.description = data.description

    await db.flush()

    return SpecialOfferResponse(
        id=so.id,
        market_item_id=so.market_item_id,
        offer_type=so.offer_type,
        discount_percentage=so.discount_percentage,
        description=so.description,
        power=so.power,
        is_active=so.is_active,
        created_at=so.created_at,
        name=gi.name,
        category=gi.category,
        image_url=gi.image_url,
        price=mi.price,
        stock_count=mi.stock_count,
    )


# ── DELETE /offers/{offer_id} ───────────────────────────────────
@router.delete("/offers/{offer_id}", status_code=200)
async def delete_special_offer(
    offer_id: uuid.UUID,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a special offer."""
    from app.models.special_offer import SpecialOffer

    result = await db.execute(
        select(SpecialOffer)
        .join(MarketItem, SpecialOffer.market_item_id == MarketItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(SpecialOffer.id == offer_id, Market.merchant_id == user.id)
    )
    so = result.scalar_one_or_none()
    if not so:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Special offer not found or does not belong to your shop.",
        )
    
    await db.delete(so)
    await db.flush()
    return {"success": True, "message": "Special offer deleted successfully"}


# ── GET /market/item/barcode/{barcode} ───────────────────────────
@router.get("/market/item/barcode/{barcode}", response_model=BarcodeLookupResponse)
async def lookup_item_by_barcode(
    barcode: str,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Query GlobalItem by barcode, check if linked in merchant's branch, and return details."""
    # Find merchant's market
    market_result = await db.execute(
        select(Market).where(Market.merchant_id == user.id)
    )
    market = market_result.scalar_one_or_none()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found. Complete onboarding first.",
        )

    # Find global item by barcode
    gi_result = await db.execute(
        select(GlobalItem).where(GlobalItem.barcode == barcode)
    )
    gi = gi_result.unique().scalar_one_or_none()
    if gi is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found in global catalog.",
        )

    # Check if a corresponding MarketItem exists for this branch
    mi_result = await db.execute(
        select(MarketItem).where(
            MarketItem.market_id == market.id,
            MarketItem.item_id == gi.id
        )
    )
    mi = mi_result.scalar_one_or_none()

    if mi:
        return BarcodeLookupResponse(
            exists_in_branch=True,
            market_item_id=mi.id,
            global_item_id=gi.id,
            name=gi.name,
            category=gi.category,
            image_url=gi.image_url,
            price=float(mi.price) if mi.price is not None else None,
            stock_count=mi.stock_count,
            barcode=barcode
        )
    else:
        return BarcodeLookupResponse(
            exists_in_branch=False,
            market_item_id=None,
            global_item_id=gi.id,
            name=gi.name,
            category=gi.category,
            image_url=gi.image_url,
            price=None,
            stock_count=None,
            barcode=barcode
        )


@router.post("/checkout")
async def pos_checkout(
    data: CheckoutRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Deduct stock counts, save persistent transaction receipts, and alert merchant on depleted inventory."""
    # Find merchant's market
    market_result = await db.execute(
        select(Market).where(Market.merchant_id == user.id)
    )
    market = market_result.scalar_one_or_none()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found. Complete onboarding first.",
        )

    receipt_items = []
    total_cost = 0.0
    alerts = []
    es_updates = []

    for item in data.items:
        # Fetch the market item
        mi_result = await db.execute(
            select(MarketItem)
            .where(MarketItem.id == item.market_item_id, MarketItem.market_id == market.id)
            .options(selectinload(MarketItem.global_item))
        )
        mi = mi_result.scalar_one_or_none()
        if not mi:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Market item {item.market_item_id} not found in this branch.",
            )

        # Deduct stock
        original_stock = mi.stock_count or 0
        deducted_stock = max(0, original_stock - item.quantity)
        mi.stock_count = deducted_stock

        # Auto-update status based on remaining stock count
        if deducted_stock == 0:
            mi.status = False
            item_name = mi.global_item.name if mi.global_item else "Product"
            # Trigger notification log event
            logger.warning(
                f"[NOTIFICATION ENGINE] MERCHANT ALERT: Store '{market.name}' (owner_id={user.id})! "
                f"Product '{item_name}' (ID: {mi.id}) is OUT OF STOCK. Please replenish inventory."
            )
            alerts.append({
                "type": "out_of_stock",
                "message": f"'{item_name}' is now OUT OF STOCK. Please replenish inventory."
            })
        else:
            mi.status = True
            # Proactively trigger customer search alerts if item returns to positive stock
            await check_and_trigger_stock_alerts(db, mi.id)

        es_updates.append((mi.id, mi.status))

        subtotal = (mi.price or 0.0) * item.quantity
        total_cost += subtotal

        receipt_items.append({
            "name": mi.global_item.name if mi.global_item else "Product",
            "quantity": item.quantity,
            "unit_price": mi.price or 0.0,
            "subtotal": round(subtotal, 2)
        })

    # Save POS Receipt physically inside database
    rounded_total = round(total_cost, 2)
    receipt = POSReceipt(
        market_id=market.id,
        total_cost=rounded_total
    )
    db.add(receipt)
    await db.flush() # Populate receipt.id
    
    # Save corresponding itemizations in receipt items table
    for r_item in receipt_items:
        db.add(
            POSReceiptItem(
                receipt_id=receipt.id,
                name=r_item["name"],
                quantity=r_item["quantity"],
                unit_price=r_item["unit_price"],
                subtotal=r_item["subtotal"]
            )
        )

    await db.commit()

    # Sync availability states to Elasticsearch index in real-time
    try:
        es_client = get_es_client()
        indexer = IndexerService(es_client)
        for mi_id, in_stock in es_updates:
            await indexer.update_stock(mi_id, in_stock)
    except Exception as e:
        logger.error(f"Elasticsearch POS checkout status sync failed: {e}")

    return {
        "success": True,
        "total_cost": rounded_total,
        "items": receipt_items,
        "alerts": alerts
    }


@router.get("/checkout/history")
async def get_checkout_history(
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all POS receipts processed in the last 14 days for this market."""
    # Find merchant's market
    market_result = await db.execute(
        select(Market).where(Market.merchant_id == user.id)
    )
    market = market_result.scalar_one_or_none()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found.",
        )

    from datetime import datetime, timezone, timedelta
    jordan_tz = timezone(timedelta(hours=3))
    fourteen_days_ago = datetime.now(jordan_tz) - timedelta(days=14)

    result = await db.execute(
        select(POSReceipt)
        .where(POSReceipt.market_id == market.id, POSReceipt.created_at >= fourteen_days_ago)
        .order_by(POSReceipt.created_at.desc())
    )
    receipts = result.unique().scalars().all()

    # Format output
    history = []
    for r in receipts:
        history.append({
            "id": str(r.id),
            "total_cost": r.total_cost,
            "created_at": r.created_at.isoformat(),
            "items": [
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "subtotal": item.subtotal
                } for item in r.items
            ]
        })

    return history


