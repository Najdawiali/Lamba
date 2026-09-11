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
  POST /api/v1/merchant/items/upload-csv/{market_id}  — Bulk ingest/link via CSV
  GET  /api/v1/merchant/market/stats/value    — Total inventory assets value
"""

import os
import uuid
import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import Annotated, List, Optional

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
from app.models.offer import Offer
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
from app.schemas.offer import OfferCreate, OfferUpdate, OfferResponse
from app.schemas.market_profile import MarketProfileUpdate, EmployeesUpdate, MarketProfileResponse
from app.services.embedding import embedding_service
from app.services.alert_service import check_and_trigger_stock_alerts
from app.services.storage import storage_service

from app.config import settings
from app.services.auth import create_access_token

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


async def get_user_market(user: User, db: AsyncSession) -> Market:
    """Retrieve the physical market profile for a user or 404."""
    result = await db.execute(
        select(Market).where(Market.merchant_id == user.id).order_by(Market.created_at.desc())
    )
    market = result.scalars().first()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found. Complete onboarding first.",
        )
    return market


# ── GET /market ─────────────────────────────────────────────────
@router.get("/market", response_model=MarketResponse)
async def get_market(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the user's physical market profile if initialized, or 404 if not found."""
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
        name_ar=getattr(market, 'name_ar', None),
        address=market.address,
        address_ar=getattr(market, 'address_ar', None),
        latitude=float(lat),
        longitude=float(lng),
        business_nature=market.business_nature,
        operating_hours=market.operating_hours,
        employee_directory=market.employee_directory,
        phone=market.phone,
        contact_phone=market.contact_phone,
        contact_email=market.contact_email,
        employees=market.employees or [],
        profile_edited_at=market.profile_edited_at,
        name_edited_at=market.name_edited_at,
        address_edited_at=market.address_edited_at,
        is_name_locked=market.name_edited_at is not None,
        is_address_locked=market.address_edited_at is not None,
        is_profile_locked=(market.name_edited_at is not None and market.address_edited_at is not None),
        is_currently_open=market.is_currently_open,
        is_manual_override=market.is_manual_override,
        override_set_at=market.override_set_at,
        created_at=market.created_at,
    )


# ── POST /market ────────────────────────────────────────────────
@router.post("/market", response_model=MarketResponse, status_code=201)
async def create_market(
    data: MarketCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initialize a physical market profile (PostGIS point integration) and upgrade user to merchant."""
    # Check if a market is already initialized with the exact same name for this user
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
    
    # Upgrade user to merchant if they were a customer
    if user.user_type != "merchant":
        user.user_type = "merchant"
    if data.phone and not user.phone_number:
        user.phone_number = data.phone

    market = Market(
        merchant_id=user.id,
        name=data.name,
        address=data.address,
        business_nature=data.business_nature,
        operating_hours=data.operating_hours,
        employee_directory=data.employee_directory,
        phone=data.phone,
        location=WKTElement(f"POINT({data.longitude} {data.latitude})", srid=4326),
        is_currently_open=data.is_currently_open if data.is_currently_open is not None else True,
    )
    db.add(market)
    await db.flush()
    await db.commit()

    # Generate fresh JWT token with upgraded 'merchant' role
    new_token = create_access_token(user.id, "merchant")
    
    return MarketResponse(
        id=market.id,
        merchant_id=market.merchant_id,
        name=market.name,
        name_ar=getattr(market, 'name_ar', None),
        address=market.address,
        address_ar=getattr(market, 'address_ar', None),
        latitude=data.latitude,
        longitude=data.longitude,
        business_nature=market.business_nature,
        operating_hours=market.operating_hours,
        employee_directory=market.employee_directory,
        phone=market.phone,
        contact_phone=market.contact_phone,
        contact_email=market.contact_email,
        employees=market.employees or [],
        profile_edited_at=market.profile_edited_at,
        name_edited_at=market.name_edited_at,
        address_edited_at=market.address_edited_at,
        is_name_locked=market.name_edited_at is not None,
        is_address_locked=market.address_edited_at is not None,
        is_profile_locked=(market.name_edited_at is not None and market.address_edited_at is not None),
        is_currently_open=market.is_currently_open,
        is_manual_override=market.is_manual_override,
        override_set_at=market.override_set_at,
        created_at=market.created_at,
        access_token=new_token,
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
    await db.refresh(market)
    
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
        name_ar=getattr(market, 'name_ar', None),
        address=market.address,
        address_ar=getattr(market, 'address_ar', None),
        latitude=float(lat),
        longitude=float(lng),
        business_nature=market.business_nature,
        operating_hours=market.operating_hours,
        employee_directory=market.employee_directory,
        phone=market.phone,
        contact_phone=market.contact_phone,
        contact_email=market.contact_email,
        employees=market.employees or [],
        profile_edited_at=market.profile_edited_at,
        name_edited_at=market.name_edited_at,
        address_edited_at=market.address_edited_at,
        is_name_locked=market.name_edited_at is not None,
        is_address_locked=market.address_edited_at is not None,
        is_profile_locked=(market.name_edited_at is not None and market.address_edited_at is not None),
        is_currently_open=market.is_currently_open,
        is_manual_override=market.is_manual_override,
        override_set_at=market.override_set_at,
        created_at=market.created_at,
    )


# ── Market Profile & Employee Management ─────────────────────────
@router.patch("/market/profile", response_model=MarketProfileResponse)
async def update_market_profile(
    payload: MarketProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    market = await get_user_market(current_user, db)
    update_data = payload.model_dump(exclude_unset=True)

    # Separate name fields, address fields, and contact fields
    name_fields = {'name', 'name_ar'}
    address_fields = {'address', 'address_ar'}
    has_name_changes = bool(name_fields & set(update_data.keys()))
    has_address_changes = bool(address_fields & set(update_data.keys()))

    # Check independent locks
    if has_name_changes and market.name_edited_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Store name can only be edited once. Contact support for further changes."
        )

    if has_address_changes and market.address_edited_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Store address can only be edited once. Contact support for further changes."
        )

    # Apply all updates
    for field, value in update_data.items():
        if hasattr(market, field):
            setattr(market, field, value)

    # Lock name if changed
    if has_name_changes:
        market.name_edited_at = datetime.now(timezone.utc)

    # Lock address if changed
    if has_address_changes:
        market.address_edited_at = datetime.now(timezone.utc)

    # Keep profile_edited_at updated if any identity field changed
    if has_name_changes or has_address_changes:
        market.profile_edited_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(market)

    return MarketProfileResponse(
        name=market.name,
        name_ar=getattr(market, 'name_ar', None),
        address=market.address,
        address_ar=getattr(market, 'address_ar', None),
        contact_phone=market.contact_phone,
        contact_email=market.contact_email,
        employees=market.employees or [],
        profile_edited_at=market.profile_edited_at,
        name_edited_at=market.name_edited_at,
        address_edited_at=market.address_edited_at,
        is_name_locked=market.name_edited_at is not None,
        is_address_locked=market.address_edited_at is not None,
        is_profile_locked=(market.name_edited_at is not None and market.address_edited_at is not None),
    )


@router.put("/market/employees", response_model=MarketProfileResponse)
async def update_employees(
    payload: EmployeesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    market = await get_user_market(current_user, db)
    market.employees = payload.employees
    await db.commit()
    await db.refresh(market)

    return MarketProfileResponse(
        name=market.name,
        name_ar=getattr(market, 'name_ar', None),
        address=market.address,
        address_ar=getattr(market, 'address_ar', None),
        contact_phone=market.contact_phone,
        contact_email=market.contact_email,
        employees=market.employees or [],
        profile_edited_at=market.profile_edited_at,
        name_edited_at=market.name_edited_at,
        address_edited_at=market.address_edited_at,
        is_name_locked=market.name_edited_at is not None,
        is_address_locked=market.address_edited_at is not None,
        is_profile_locked=(market.name_edited_at is not None and market.address_edited_at is not None),
    )


@router.get("/market/profile", response_model=MarketProfileResponse)
async def get_market_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    market = await get_user_market(current_user, db)

    return MarketProfileResponse(
        name=market.name,
        name_ar=getattr(market, 'name_ar', None),
        address=market.address,
        address_ar=getattr(market, 'address_ar', None),
        contact_phone=market.contact_phone,
        contact_email=market.contact_email,
        employees=market.employees or [],
        profile_edited_at=market.profile_edited_at,
        name_edited_at=market.name_edited_at,
        address_edited_at=market.address_edited_at,
        is_name_locked=market.name_edited_at is not None,
        is_address_locked=market.address_edited_at is not None,
        is_profile_locked=(market.name_edited_at is not None and market.address_edited_at is not None),
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


# ── GET /market/stats/value ─────────────────────────────────────
@router.get("/market/stats/value")
async def get_market_inventory_value(
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Total inventory assets value = Σ (price * stock_count) for merchant's items."""
    result = await db.execute(
        select(
            func.coalesce(
                func.sum(MarketItem.price * MarketItem.stock_count), 0.0
            ).label("total_value")
        )
        .join(Market, MarketItem.market_id == Market.id)
        .where(Market.merchant_id == user.id)
    )
    total = float(result.scalar() or 0.0)
    return {"total_value": round(total, 2)}


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
    
    name_changed = False
    if data.name is not None and data.name.strip() and data.name.strip() != gi.name:
        gi.name = data.name.strip()
        name_changed = True

    if data.stock_count is not None:
        mi.stock_count = data.stock_count
        # Auto-update status based on stock count
        if data.stock_count == 0:
            mi.status = False
        else:
            mi.status = True

    if data.price is not None:
        mi.price = data.price

    # Re-compute embeddings ONLY if name actually changed
    if name_changed:
        try:
            combined_text = gi.name
            if gi.description:
                combined_text = f"{gi.name}. {gi.description}"
            # Re-generate text vector and image vector
            text_vec = (await embedding_service.encode_text_async(combined_text)).tolist()
            image_vec = (await embedding_service.encode_product_async(gi.name, gi.description)).tolist()
            gi.text_embedding = text_vec
            gi.image_embedding = image_vec
        except Exception as e:
            logger.warning(f"Re-embedding for item {gi.id} skipped due to error: {e}")

    await db.flush()
    if mi.status:
        try:
            await check_and_trigger_stock_alerts(db, mi.id)
        except Exception as alert_err:
            logger.warning(f"Stock alert check failed: {alert_err}")
    await db.commit()

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
    # Escape LIKE wildcards so user-supplied % and _ are matched literally, not as glob chars
    escaped = (
        data.item_name
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    result = await db.execute(
        select(GlobalItem)
        .where(GlobalItem.name.ilike(f"%{escaped}%", escape="\\"))
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
    
    return ItemLinkResponse(
        success=True,
        message=message,
        market_item_id=mi.id,
        stock_count=mi.stock_count
    )


# ── POST /items/new ─────────────────────────────────────────────
OFFICIAL_CATEGORIES = [
    "Fruits & Vegetables", "Dairy & Eggs", "Meat & Poultry", "Beverages",
    "Snacks", "Bakery", "Frozen Food", "Cleaning & Detergents",
    "Beauty & Personal Care", "Cooking Essentials", "Mobiles & Tech",
    "Cookware & Kitchenware", "Electronics",
    "Beauty & Personal Care Services", "Vehicle Maintenance & Care",
    "Home & Maintenance Services", "Education & Tutoring",
]


def _classify_category_heuristic(name: str, description: str | None) -> str:
    """Heuristic categorizer parsing product name and description into official categories."""
    text = (name + " " + (description or "")).lower()
    
    # Services heuristic
    if any(k in text for k in ["درس", "مدرسة", "تعليم", "توتور", "تدرس", "tutor", "school", "french", "math"]):
        return "Education & Tutoring"
    if any(k in text for k in ["غسيل سيار", "تلميع سيار", "صيانة سيار", "ميكانيك", "car wash", "oil change"]):
        return "Vehicle Maintenance & Care"
    if any(k in text for k in ["سباكة", "كهرباء منزل", "تنظيف منزل", "plumbing", "cleaning"]):
        return "Home & Maintenance Services"
    if any(k in text for k in ["حلاقة", "تجميل", "مساج", "علاج طبيعي", "barber", "salon"]):
        return "Beauty & Personal Care Services"

    # Products heuristic
    if any(k in text for k in ["fruit", "vegetable", "tomato", "banana", "apple", "orange", "lemon", "potato", "onion", "mint", "lettuce", "garlic", "cucumber"]):
        return "Fruits & Vegetables"
    if any(k in text for k in ["milk", "egg", "eggs", "cheese", "yogurt", "butter", "dairy", "cream"]):
        return "Dairy & Eggs"
    if any(k in text for k in ["chicken", "meat", "beef", "lamb", "poultry", "turkey", "steak", "sausage"]):
        return "Meat & Poultry"
    if any(k in text for k in ["tea", "coffee", "espresso", "juice", "soda", "water", "drink", "beverage", "cola", "nescafe"]):
        return "Beverages"
    if any(k in text for k in ["snack", "chips", "chocolate", "biscuit", "cookie", "crisps", "nut", "nuts", "candy", "sweet"]):
        return "Snacks"
    if any(k in text for k in ["bread", "bakery", "croissant", "muffin", "cake", "toast", "bun"]):
        return "Bakery"
    if any(k in text for k in ["frozen", "ice cream", "nuggets"]):
        return "Frozen Food"
    if any(k in text for k in ["clean", "detergent", "soap", "dishwash", "laundry", "bleach", "shampoo"]):
        return "Cleaning & Detergents"
    if any(k in text for k in ["beauty", "personal care", "cream", "lotion", "cosmetic", "makeup", "perfume", "oil"]):
        if "essential oil" in text or "skin" in text or "face" in text or "hair" in text:
            return "Beauty & Personal Care"
    if any(k in text for k in ["oil", "olive oil", "spice", "spices", "honey", "seed", "seeds", "salt", "sugar", "flour", "vinegar", "saffron", "turmeric", "cardamom", "spread", "peanut butter"]):
        return "Cooking Essentials"
    if any(k in text for k in ["phone", "mobile", "charger", "headphone", "earbuds", "cable", "screen protector"]):
        return "Mobiles & Tech"
    if any(k in text for k in ["pot", "pan", "cookware", "kitchenware", "plate", "spoon", "fork", "knife", "cup", "mug"]):
        return "Cookware & Kitchenware"
    if any(k in text for k in ["electric", "vacuum", "oven", "tv", "refrigerator", "fridge", "microwave", "appliance"]):
        return "Electronics"
        
    return "Cooking Essentials"


async def _classify_category(name: str, description: str | None) -> str:
    """Classify item/service using LLMAdapter with heuristic fallback (Gemma 4 31B offline model)."""
    from app.services.llm import llm_adapter
    from app.config import settings

    product_text = f"Name: {name}\nDescription: {description or ''}"
    sys_prompt = (
        "You are an expert catalog item and service categorizer. "
        "Choose EXACTLY ONE category from this list that best fits the item/service:\n"
        + ", ".join(OFFICIAL_CATEGORIES)
        + "\nReturn ONLY the exact category name, with no punctuation, extra words, or markdown."
    )
    try:
        res = await llm_adapter.generate(
            system_prompt=sys_prompt,
            user_prompt=f"Classify this product:\n{product_text}",
            model=settings.offline_llm_model,  # Uses Gemma 4 31B — runs once per product creation
            enable_thinking=False,
            max_tokens=50,
        )
        if res:
            clean_res = res.strip().strip('"').strip("'")
            for cat in OFFICIAL_CATEGORIES:
                if cat.lower() == clean_res.lower():
                    return cat
    except Exception as e:
        logger.warning(f"LLM category classification failed: {e}")

    return _classify_category_heuristic(name, description)



@router.post("/items/new", response_model=ItemLinkResponse)
async def create_new_item(
    market_id: uuid.UUID = Form(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    barcode: Optional[str] = Form(None),
    stock_count: int = Form(0),
    price: Optional[float] = Form(None),
    category_id: Optional[uuid.UUID] = Form(None),
    listing_type: Optional[str] = Form("product"),
    attributes: Optional[str] = Form(None),
    image: UploadFile = File(...),
    secondary_images: List[UploadFile] = File(default=[]),
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a brand-new catalog product or service utilizing local CLIP/MiniLM/Qwen embedding models."""
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

    # Parse attributes if passed as JSON string
    parsed_attributes = {}
    if attributes:
        try:
            parsed_attributes = json.loads(attributes) if isinstance(attributes, str) else attributes
        except Exception:
            parsed_attributes = {}
    
    # Save Primary Upload Image (local or cloud, based on STORAGE_BACKEND)
    image_bytes = await image.read()
    primary_image_url = await storage_service.upload(
        file_bytes=image_bytes,
        original_filename=image.filename or "photo.jpg",
        subfolder="products",
    )

    # Save Secondary Upload Images
    secondary_urls = []
    for sec_file in secondary_images:
        if sec_file.filename:
            sec_bytes = await sec_file.read()
            sec_url = await storage_service.upload(
                file_bytes=sec_bytes,
                original_filename=sec_file.filename,
                subfolder="products",
            )
            secondary_urls.append(sec_url)
    
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
        # Honor explicit category selection from the merchant when provided
        cat: Category | None = None
        if category_id is not None:
            cat_result = await db.execute(
                select(Category).where(Category.id == category_id)
            )
            cat = cat_result.scalar_one_or_none()
        if cat is None:
            # Fallback to Heuristic NLP Classification
            category_name = await _classify_category(name, description)
            cat_result = await db.execute(
                select(Category).where(Category.name == category_name)
            )
            cat = cat_result.scalar_one_or_none()
            if not cat:
                cat = Category(name=category_name, listing_type=listing_type or "product")
                db.add(cat)
                await db.flush()
    else:
        cat_result = await db.execute(select(Category).where(Category.name == category_name))
        cat = cat_result.scalar_one_or_none()
        if not cat:
            cat = Category(name=category_name, listing_type=listing_type or "product")
            db.add(cat)
            await db.flush()
    
    # Generate 512-d image vector (CLIP)
    image_vector = None
    try:
        image_vector = embedding_service.encode_image_bytes(image_bytes)
    except Exception as e:
        logger.error(f"CLIP encoding failed: {e}")
        
    # Save GlobalItem (preserves original inputs for display, uses VLM/translated vectors)
    effective_barcode = barcode if (listing_type == "product" and barcode) else None
    gi = GlobalItem(
        name=name,
        description=description,
        barcode=effective_barcode,
        listing_type=listing_type or "product",
        attributes=parsed_attributes,
        category_id=cat.id,
        text_embedding=None,
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
        stock_count=stock_count if listing_type == "product" else 99,
        price=price,
        status=True
    )
    db.add(mi)
    await db.flush()
    await check_and_trigger_stock_alerts(db, mi.id)
    
    # Auto-enrich search terms & vector embedding on creation
    try:
        from app.services.arabic_norm import normalize_arabic
        norm_name = normalize_arabic(gi.name)
        terms = [norm_name] if norm_name else [gi.name]
        try:
            from scripts.enrich_search_terms import enrich_product
            enriched_terms = await enrich_product(gi.name, gi.description, getattr(cat, "name", None))
            if enriched_terms:
                terms.append(enriched_terms)
        except Exception as e:
            logger.warning(f"LLM search terms enrichment skipped: {e}")

        gi.search_terms = ", ".join([t for t in terms if t])
        
        # Build dense document text for Qwen3 / MiniLM
        doc_text = f"{gi.name} {gi.description or ''} {gi.search_terms or ''}".strip()
        doc_embedding = await embedding_service.encode_text_async(doc_text, text_type="document")
        gi.text_embedding = doc_embedding.tolist()
        gi.embedding_status = "completed"
        gi.embedded_at = datetime.now(timezone.utc)
        
        await db.commit()
    except Exception as e:
        logger.warning(f"Auto-enrich/embed failed for item {gi.id}: {e}")
        await db.commit()

    return ItemLinkResponse(
        success=True,
        message=f"Brand-new {listing_type} ingested via AI pipeline and added to stock.",
        market_item_id=mi.id,
        stock_count=mi.stock_count
    )


# ── POST /items/upload-csv/{market_id} ──────────────────────────
@router.post("/items/upload-csv/{market_id}")
async def upload_items_csv(
    market_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk ingest/link inventory via CSV. Required header: name. Optional: barcode,
        description, stock_count, price. Rows are matched to existing catalog items
    by barcode first, then by case-insensitive name; unmatched rows create new
    GlobalItems (heuristic categorization + MiniLM/CLIP embeddings).
    """
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

    content = await file.read()
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1", errors="ignore")

    reader = csv.DictReader(io.StringIO(text_content))
    if not reader.fieldnames or "name" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV must include a 'name' column. Optional: barcode, description, stock_count, price.",
        )

    created_count = 0
    linked_count = 0
    es_indexed = 0

    for idx, row in enumerate(reader, start=2):
        def _get(key: str) -> str:
            return (row.get(key) or row.get(key.lower()) or row.get(key.title()) or "").strip()

        row_name = _get("name")
        if not row_name:
            continue

        barcode_val = _get("barcode") or None
        description_val = _get("description") or None
        try:
            stock_count = int(_get("stock_count") or 0)
        except ValueError:
            stock_count = 0
        try:
            price_val = float(_get("price")) if _get("price") else None
        except ValueError:
            price_val = None

        gi: GlobalItem | None = None

        # Match by barcode first
        if barcode_val:
            gi_result = await db.execute(
                select(GlobalItem).where(GlobalItem.barcode == barcode_val)
            )
            gi = gi_result.unique().scalar_one_or_none()

        # Fall back to a name match
        if gi is None:
            gi_result = await db.execute(
                select(GlobalItem).where(func.lower(GlobalItem.name) == row_name.lower())
            )
            gi = gi_result.unique().scalar_one_or_none()

        if gi is None:
            # Create a new catalog item with heuristic classification + text/image embeddings
            category_name = await _classify_category(row_name, description_val)
            cat_result = await db.execute(
                select(Category).where(Category.name == category_name)
            )
            cat = cat_result.scalar_one_or_none()
            if not cat:
                cat = Category(name=category_name)
                db.add(cat)
                await db.flush()

            text_vector = None
            try:
                text = row_name
                if description_val:
                    text = f"{row_name}. {description_val}"
                text_vector = embedding_service.encode_text_384(text)
            except Exception as e:
                logger.error(f"MiniLM encoding failed for CSV row {idx}: {e}")

            image_vector = None
            try:
                image_vector = embedding_service.encode_product(row_name, description_val)
            except Exception as e:
                logger.error(f"CLIP encoding failed for CSV row {idx}: {e}")

            gi = GlobalItem(
                name=row_name,
                description=description_val,
                barcode=barcode_val,
                category_id=cat.id,
                text_embedding=text_vector.tolist() if text_vector is not None else None,
                image_embedding=image_vector.tolist() if image_vector is not None else None,
                created_by=user.id,
            )
            db.add(gi)
            await db.flush()
            created_count += 1
        else:
            linked_count += 1

        # Check existing MarketItem linkage for this market
        existing_mi_result = await db.execute(
            select(MarketItem).where(
                MarketItem.market_id == market_id,
                MarketItem.item_id == gi.id,
            )
        )
        mi = existing_mi_result.scalar_one_or_none()
        if mi:
            mi.stock_count += stock_count
            if stock_count > 0:
                mi.status = True
            if price_val is not None:
                mi.price = price_val
        else:
            mi = MarketItem(
                market_id=market_id,
                item_id=gi.id,
                stock_count=stock_count,
                price=price_val,
                status=stock_count > 0,
            )
            db.add(mi)
            await db.flush()

        if mi.status:
            await check_and_trigger_stock_alerts(db, mi.id)

    await db.commit()

    return {
        "success": True,
        "created": created_count,
        "linked": linked_count,
        "indexed": es_indexed,
        "message": (
            f"CSV import complete: {created_count} new item(s) created, "
            f"{linked_count} existing item(s) linked, {es_indexed} indexed to search."
        ),
    }


# ── POST /offers ────────────────────────────────────────────────
@router.post("/offers", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
async def create_offer(
    payload: OfferCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market = await get_user_market(current_user, db)

    # Verify the market_item belongs to this market
    result = await db.execute(
        select(MarketItem, GlobalItem)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .where(
            MarketItem.id == payload.market_item_id,
            MarketItem.market_id == market.id,
        )
    )
    row = result.unique().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found in your store")

    item, global_item = row[0], row[1]

    offer = Offer(
        market_id=market.id,
        market_item_id=payload.market_item_id,
        offer_type=payload.offer_type,
        config=payload.config,
        description=payload.description,
        expires_at=payload.expires_at,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)

    return OfferResponse(
        **{c.name: getattr(offer, c.name) for c in offer.__table__.columns},
        item_name=global_item.name if global_item else getattr(item, 'name', None),
        item_name_ar=getattr(global_item, 'name_ar', None) if global_item else getattr(item, 'name_ar', None),
        item_price=item.price,
        item_image_url=getattr(global_item, 'image_url', None) if global_item else getattr(item, 'image_url', None),
    )


# ── GET /offers ─────────────────────────────────────────────────
@router.get("/offers", response_model=List[OfferResponse])
async def list_offers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market = await get_user_market(current_user, db)
    result = await db.execute(
        select(Offer, MarketItem, GlobalItem)
        .join(MarketItem, Offer.market_item_id == MarketItem.id)
        .outerjoin(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .where(Offer.market_id == market.id)
        .order_by(Offer.created_at.desc())
    )
    rows = result.unique().all()
    return [
        OfferResponse(
            **{c.name: getattr(offer, c.name) for c in offer.__table__.columns},
            item_name=global_item.name if global_item else getattr(item, 'name', None),
            item_name_ar=getattr(global_item, 'name_ar', None) if global_item else getattr(item, 'name_ar', None),
            item_price=item.price,
            item_image_url=getattr(global_item, 'image_url', None) if global_item else getattr(item, 'image_url', None),
        )
        for offer, item, global_item in rows
    ]


# ── PATCH /offers/{offer_id} ────────────────────────────────────
@router.patch("/offers/{offer_id}", response_model=OfferResponse)
async def update_offer(
    offer_id: uuid.UUID,
    payload: OfferUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market = await get_user_market(current_user, db)
    result = await db.execute(
        select(Offer, MarketItem, GlobalItem)
        .join(MarketItem, Offer.market_item_id == MarketItem.id)
        .outerjoin(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .where(Offer.id == offer_id, Offer.market_id == market.id)
    )
    row = result.unique().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    offer, item, global_item = row[0], row[1], row[2]
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(offer, field, value)

    await db.commit()
    await db.refresh(offer)

    return OfferResponse(
        **{c.name: getattr(offer, c.name) for c in offer.__table__.columns},
        item_name=global_item.name if global_item else getattr(item, 'name', None),
        item_name_ar=getattr(global_item, 'name_ar', None) if global_item else getattr(item, 'name_ar', None),
        item_price=item.price,
        item_image_url=getattr(global_item, 'image_url', None) if global_item else getattr(item, 'image_url', None),
    )


# ── DELETE /offers/{offer_id} ───────────────────────────────────
@router.delete("/offers/{offer_id}", status_code=status.HTTP_200_OK)
async def delete_offer(
    offer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market = await get_user_market(current_user, db)
    result = await db.execute(
        select(Offer).where(Offer.id == offer_id, Offer.market_id == market.id)
    )
    offer = result.unique().scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    await db.delete(offer)
    await db.commit()
    return {"deleted": True}



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


