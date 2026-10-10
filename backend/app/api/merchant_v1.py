"""
Merchant V1 API — Market initialization, inventory checks, linking, and AI-driven item ingestion.

Endpoints:
  GET  /api/v1/merchant/market              — Check if merchant has a market
  POST /api/v1/merchant/market              — Register physical store parameters (PostGIS)
  GET  /api/v1/merchant/market/items        — Fetch all merchant stocked inventory
  PATCH /api/v1/merchant/market/items/{id}/stock — Toggle stock status
  POST /api/v1/merchant/items/check          — Case-insensitive fuzzy name search
  POST /api/v1/merchant/items/link           — Link catalog item to merchant market
  POST /api/v1/merchant/items/new            — Create a new catalog item (classified, enriched, embedded)
  POST /api/v1/merchant/items/upload-csv/{market_id}  — Bulk ingest/link via CSV
  GET  /api/v1/merchant/market/stats/value    — Total inventory assets value
"""

import asyncio
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
from app.schemas.offer import OfferCreate, OfferUpdate, OfferResponse
from app.schemas.market_profile import MarketProfileUpdate, EmployeesUpdate, MarketProfileResponse
from app.services.embedding import embedding_service
from app.services.alert_service import check_and_trigger_stock_alerts
from app.services.attribute_rules import sanitize_merchant_attributes
from app.services.storage import storage_service
from sqlalchemy.exc import IntegrityError
from app.services.item_classifier import classify_item_ensemble, restricted_reason_for
from app.services.item_enrichment import enrich_and_embed
from app.utils.barcode import normalize_barcode

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


# ── Catalog helpers (classification, categories, moderation) ────
MAX_CSV_ROWS = 200
CSV_CLASSIFY_CONCURRENCY = 6

MSG_PENDING = "تمت إضافة المنتج وهو قيد المراجعة، وسيظهر للزبائن بعد الموافقة عليه."
MSG_CATEGORY_REQUIRED = "تعذّر تحديد القسم تلقائياً. الرجاء اختيار القسم ثم المحاولة مرة أخرى."
MSG_SHARED_RENAME = "هذا المنتج من الكتالوج المشترك ولا يمكن تغيير اسمه. يمكنك تعديل السعر والكمية فقط."
MAX_PHOTOS_PER_ITEM = 5
MAX_PHOTO_BYTES = 8 * 1024 * 1024


async def _category_by_slug(db: AsyncSession, slug: str | None) -> Category | None:
    if not slug:
        return None
    return (await db.execute(select(Category).where(Category.slug == slug))).scalar_one_or_none()


async def _merchant_category(db: AsyncSession, category_id: uuid.UUID | None, listing_type: str) -> Category | None:
    """The merchant's explicit choice, only if it is a real leaf category of the right type."""
    if category_id is None:
        return None
    cat = (await db.execute(select(Category).where(Category.id == category_id))).scalar_one_or_none()
    if cat is None or cat.parent_category_id is None:
        return None
    if cat.listing_type and cat.listing_type != listing_type:
        return None
    return cat


async def _category_name(db: AsyncSession, category_id: uuid.UUID | None) -> str | None:
    if category_id is None:
        return None
    row = (await db.execute(select(Category.name_en, Category.name).where(Category.id == category_id))).first()
    return (row[0] or row[1]) if row else None


async def _trigger_alerts_if_visible(db: AsyncSession, gi: GlobalItem, mi: MarketItem) -> None:
    """Customer 'notify me' alerts only for products customers can actually see."""
    if gi.moderation_status != "approved" or not mi.status:
        return
    try:
        await check_and_trigger_stock_alerts(db, mi.id)
    except Exception as e:
        logger.warning(f"Stock alert check failed for {mi.id}: {e!r}")


def _dashboard_row(mi: MarketItem, gi: GlobalItem) -> MarketItemDashboardResponse:
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
        moderation_status=gi.moderation_status,
    )

# ── GET /market/items ───────────────────────────────────────────
@router.get("/market/items", response_model=List[MarketItemDashboardResponse])
async def get_market_items(
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all global items stocked at the merchant's market (including ones under review)."""
    result = await db.execute(
        select(MarketItem, GlobalItem)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(Market.merchant_id == user.id)
        .order_by(GlobalItem.name)
    )
    return [_dashboard_row(row[0], row[1]) for row in result.unique().all()]

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
    """Toggle stock availability status."""
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
        await _trigger_alerts_if_visible(db, gi, mi)
    await db.commit()
    return _dashboard_row(mi, gi)


# ── PATCH /market/items/{item_id} ───────────────────────────────
@router.patch("/market/items/{item_id}", response_model=MarketItemDashboardResponse)
async def update_market_item(
    item_id: uuid.UUID,
    data: ItemUpdateRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a market item's stock count or price, or rename the product.

    Renaming changes the shared catalog row, so it is only allowed for a product this
    merchant created and no other store stocks. A renamed product is re-classified
    (it may go to review) and re-embedded.
    """
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

    new_name = data.name.strip() if data.name else None
    if new_name and new_name != gi.name:
        other_stores = (await db.execute(
            select(func.count()).select_from(MarketItem)
            .where(MarketItem.item_id == gi.id, MarketItem.market_id != mi.market_id)
        )).scalar_one()
        if gi.created_by != user.id or other_stores:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "shared_product", "message": MSG_SHARED_RENAME},
            )
        verdict = await classify_item_ensemble(new_name, gi.description, gi.listing_type, interactive=True)
        gi.name = new_name
        # A rename can send an approved product to review, but can never release a product
        # that is under review for a restriction flag, a user report, or a human block.
        if gi.moderation_status == "approved" or gi.restricted_reason == "classifier_unavailable":
            gi.moderation_status = verdict.moderation_status
            gi.restricted_reason = restricted_reason_for(verdict)
        await enrich_and_embed(gi, await _category_name(db, gi.category_id), timeout=20.0)

    if data.stock_count is not None:
        mi.stock_count = data.stock_count
        mi.status = data.stock_count > 0

    if data.price is not None:
        mi.price = data.price

    await db.flush()
    await _trigger_alerts_if_visible(db, gi, mi)
    await db.commit()
    return _dashboard_row(mi, gi)


# ── POST /items/check ───────────────────────────────────────────
@router.post("/items/check", response_model=ItemCheckResponse)
async def check_item(
    data: ItemCheckRequest,
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Search approved catalog items matching the search string (case-insensitive substring)."""
    # Escape LIKE wildcards so user-supplied % and _ are matched literally, not as glob chars
    escaped = (
        data.item_name
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    result = await db.execute(
        select(GlobalItem)
        .where(
            GlobalItem.name.ilike(f"%{escaped}%", escape="\\"),
            GlobalItem.moderation_status == "approved",
        )
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
    """Link an existing (approved) catalog item to the merchant's physical market."""
    market = (await db.execute(
        select(Market).where(Market.id == data.market_id, Market.merchant_id == user.id)
    )).scalar_one_or_none()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your market.",
        )

    gi = (await db.execute(select(GlobalItem).where(GlobalItem.id == data.item_id))).unique().scalar_one_or_none()
    if gi is None or gi.moderation_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Catalog item not found.",
        )

    mi = (await db.execute(
        select(MarketItem).where(
            MarketItem.market_id == data.market_id,
            MarketItem.item_id == data.item_id,
        )
    )).scalar_one_or_none()

    if mi:
        mi.stock_count += data.stock_count
        mi.status = True
        message = f"Stock incremented by {data.stock_count} for existing item."
    else:
        mi = MarketItem(
            market_id=data.market_id,
            item_id=data.item_id,
            stock_count=data.stock_count,
            status=True,
        )
        db.add(mi)
        message = "New catalog item successfully linked to your market."

    try:
        await db.flush()
    except IntegrityError:
        # Two quick taps: the unique (market_id, item_id) constraint caught a duplicate link
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item is already linked to your market.")
    await _trigger_alerts_if_visible(db, gi, mi)
    await db.commit()

    return ItemLinkResponse(
        success=True,
        message=message,
        market_item_id=mi.id,
        stock_count=mi.stock_count,
        moderation_status=gi.moderation_status,
    )

# ── POST /items/{global_item_id}/photos ─────────────────────────
@router.post("/items/{global_item_id}/photos")
async def add_item_photo(
    global_item_id: uuid.UUID,
    image: UploadFile = File(...),
    user: User = Depends(get_merchant),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a photo to a catalog product this merchant stocks (merchant-crowdsourced catalog photos).

    The first photo of a product becomes its primary (catalog-wide) photo; later ones are
    extras, up to MAX_PHOTOS_PER_ITEM. Stocking the product is required so merchants can
    only photograph products they actually carry.
    """
    stocked = (await db.execute(
        select(MarketItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(MarketItem.item_id == global_item_id, Market.merchant_id == user.id)
        .limit(1)
    )).scalar_one_or_none()
    if stocked is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Add the product to your store first.")

    gi = (await db.execute(select(GlobalItem).where(GlobalItem.id == global_item_id))).unique().scalar_one_or_none()
    if gi is None or gi.moderation_status == "blocked":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog item not found.")

    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only image files are accepted.")
    data = await image.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty image.")
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image is larger than 8 MB.")

    existing = (await db.execute(
        select(func.count()).select_from(ProductImage).where(ProductImage.global_item_id == gi.id)
    )).scalar_one()
    if existing >= MAX_PHOTOS_PER_ITEM:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This product already has enough photos.")
    has_primary = (await db.execute(
        select(func.count()).select_from(ProductImage)
        .where(ProductImage.global_item_id == gi.id, ProductImage.is_primary == True)  # noqa: E712
    )).scalar_one() > 0

    url = await storage_service.upload(
        file_bytes=data,
        original_filename=image.filename or "photo.jpg",
        subfolder="products",
    )
    db.add(ProductImage(global_item_id=gi.id, image_url=url, is_primary=not has_primary))
    await db.commit()
    logger.info("Photo added to %s by merchant %s (primary=%s)", gi.id, user.id, not has_primary)
    return {"image_url": url, "is_primary": not has_primary}


# ── POST /items/new ─────────────────────────────────────────────
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
    """
    Create a brand-new catalog product or service and stock it in the merchant's market.

    Order: validate -> classify (restriction + category) -> upload images -> save ->
    enrich + embed. Nothing is uploaded for a request that fails validation.
    """
    market = (await db.execute(
        select(Market).where(Market.id == market_id, Market.merchant_id == user.id)
    )).scalar_one_or_none()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your market.",
        )

    listing_type = (listing_type or "product").strip().lower()
    if listing_type not in ("product", "service"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="listing_type must be 'product' or 'service'.")
    name = (name or "").strip()
    description = (description or "").strip() or None
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name is required.")

    parsed_attributes = {}
    if attributes:
        try:
            parsed_attributes = json.loads(attributes) if isinstance(attributes, str) else attributes
        except Exception:
            parsed_attributes = {}
    # Search filters on these values, so only known keys with the right types are stored.
    parsed_attributes = sanitize_merchant_attributes(parsed_attributes)

    effective_barcode = normalize_barcode(barcode) if listing_type == "product" else None
    if effective_barcode:
        existing = (await db.execute(
            select(GlobalItem.id).where(GlobalItem.barcode == effective_barcode)
        )).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "barcode_exists",
                    "message": "هذا الباركود موجود في الكتالوج. أضفه إلى متجرك من خلال مسح الباركود.\nThis barcode is already in the catalog. Add it to your store by scanning the barcode.",
                    "global_item_id": str(existing),
                },
            )

    # 1. Classify before storing anything
    verdict = await classify_item_ensemble(name, description, listing_type, interactive=True)

    # 2. Category: the merchant's explicit choice wins; otherwise the classifier's
    cat = await _merchant_category(db, category_id, listing_type)
    if cat is None:
        cat = await _category_by_slug(db, verdict.category_slug)
    if cat is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "category_required", "message": MSG_CATEGORY_REQUIRED},
        )

    # 3. Images (local or cloud, based on STORAGE_BACKEND)
    image_bytes = await image.read()
    primary_image_url = await storage_service.upload(
        file_bytes=image_bytes,
        original_filename=image.filename or "photo.jpg",
        subfolder="products",
    )
    secondary_urls = []
    for sec_file in secondary_images:
        if sec_file.filename:
            sec_url = await storage_service.upload(
                file_bytes=await sec_file.read(),
                original_filename=sec_file.filename,
                subfolder="products",
            )
            secondary_urls.append(sec_url)

    # 4. Save
    gi = GlobalItem(
        name=name,
        description=description,
        barcode=effective_barcode,
        listing_type=listing_type,
        attributes=parsed_attributes,
        category_id=cat.id,
        created_by=user.id,
        moderation_status=verdict.moderation_status,
        restricted_reason=restricted_reason_for(verdict),
    )
    db.add(gi)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "barcode_exists", "message": "هذا الباركود موجود في الكتالوج.\nThis barcode is already in the catalog."},
        )

    db.add(ProductImage(global_item_id=gi.id, image_url=primary_image_url, is_primary=True))
    for sec_url in secondary_urls:
        db.add(ProductImage(global_item_id=gi.id, image_url=sec_url, is_primary=False))

    mi = MarketItem(
        market_id=market_id,
        item_id=gi.id,
        stock_count=stock_count if listing_type == "product" else 99,
        price=price,
        status=True,
    )
    db.add(mi)
    await db.flush()

    # 5. Search terms + embedding (best effort: the product is saved either way)
    await enrich_and_embed(gi, cat.name_en or cat.name, timeout=20.0)
    await _trigger_alerts_if_visible(db, gi, mi)
    await db.commit()

    pending = gi.moderation_status != "approved"
    return ItemLinkResponse(
        success=True,
        message=MSG_PENDING if pending else f"Brand-new {listing_type} added to your store.",
        market_item_id=mi.id,
        stock_count=mi.stock_count,
        moderation_status=gi.moderation_status,
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
    Bulk ingest/link inventory via CSV (max MAX_CSV_ROWS rows).
    Required header: name. Optional: barcode, description, stock_count, price.

    Rows match existing approved catalog items by barcode, then by exact name.
    Unmatched rows are classified in parallel and created as new catalog items
    (embedded from name + description; LLM search terms are filled later by the
    batch enrichment job, so the request stays fast).
    """
    market = (await db.execute(
        select(Market).where(Market.id == market_id, Market.merchant_id == user.id)
    )).scalar_one_or_none()
    if market is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your market.",
        )

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

    # ── Parse ──
    rows, truncated = [], 0
    for idx, raw in enumerate(reader, start=2):
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not norm.get("name"):
            continue
        if len(rows) >= MAX_CSV_ROWS:
            truncated += 1
            continue
        try:
            stock = int(norm.get("stock_count") or 0)
        except ValueError:
            stock = 0
        try:
            price_val = float(norm["price"]) if norm.get("price") else None
        except ValueError:
            price_val = None
        rows.append({
            "line": idx,
            "name": norm["name"],
            "barcode": normalize_barcode(norm.get("barcode")),
            "description": norm.get("description") or None,
            "stock": max(stock, 0),
            "price": price_val,
        })

    # ── Match existing approved catalog items ──
    for r in rows:
        gi = None
        if r["barcode"]:
            gi = (await db.execute(
                select(GlobalItem).where(GlobalItem.barcode == r["barcode"])
            )).unique().scalar_one_or_none()
            if gi is not None and gi.moderation_status != "approved":
                r["skip"] = "barcode belongs to a product that is not available"
                continue
        if gi is None:
            gi = (await db.execute(
                select(GlobalItem).where(
                    func.lower(GlobalItem.name) == r["name"].lower(),
                    GlobalItem.moderation_status == "approved",
                ).limit(1)
            )).unique().scalars().first()
        r["gi"] = gi

    # ── Classify unmatched rows in parallel ──
    to_classify = [r for r in rows if r.get("gi") is None and "skip" not in r]
    sem = asyncio.Semaphore(CSV_CLASSIFY_CONCURRENCY)

    async def _classify(r):
        async with sem:
            r["verdict"] = await classify_item_ensemble(r["name"], r["description"], "product", interactive=True)

    await asyncio.gather(*(_classify(r) for r in to_classify))

    # ── Create / link ──
    created, linked, held, skipped = 0, 0, [], []
    created_by_barcode: dict[str, GlobalItem] = {}
    for r in rows:
        if "skip" in r:
            skipped.append({"line": r["line"], "name": r["name"], "reason": r["skip"]})
            continue
        gi = r.get("gi") or (created_by_barcode.get(r["barcode"]) if r["barcode"] else None)
        if gi is None:
            verdict = r["verdict"]
            cat = await _category_by_slug(db, verdict.category_slug)
            if cat is None:
                skipped.append({"line": r["line"], "name": r["name"], "reason": "category could not be determined"})
                continue
            gi = GlobalItem(
                name=r["name"],
                description=r["description"],
                barcode=r["barcode"],
                listing_type="product",
                category_id=cat.id,
                created_by=user.id,
                moderation_status=verdict.moderation_status,
                restricted_reason=restricted_reason_for(verdict),
            )
            db.add(gi)
            await db.flush()
            await enrich_and_embed(gi, cat.name_en or cat.name, use_llm=False)
            if r["barcode"]:
                created_by_barcode[r["barcode"]] = gi
            created += 1
            if gi.moderation_status != "approved":
                held.append({"line": r["line"], "name": r["name"]})
        else:
            linked += 1

        mi = (await db.execute(
            select(MarketItem).where(MarketItem.market_id == market_id, MarketItem.item_id == gi.id)
        )).scalar_one_or_none()
        if mi:
            mi.stock_count += r["stock"]
            if r["stock"] > 0:
                mi.status = True
            if r["price"] is not None:
                mi.price = r["price"]
        else:
            mi = MarketItem(
                market_id=market_id,
                item_id=gi.id,
                stock_count=r["stock"],
                price=r["price"],
                status=r["stock"] > 0,
            )
            db.add(mi)
            await db.flush()
        await _trigger_alerts_if_visible(db, gi, mi)

    await db.commit()

    return {
        "success": True,
        "created": created,
        "linked": linked,
        "held_for_review": held,
        "skipped": skipped,
        "truncated_rows": truncated,
        "message": (
            f"CSV import complete: {created} new item(s) created, {linked} existing item(s) linked"
            + (f", {len(held)} held for review" if held else "")
            + (f", {len(skipped)} skipped" if skipped else "")
            + (f"; only the first {MAX_CSV_ROWS} rows were processed" if truncated else "")
            + "."
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
    """Find a catalog item by barcode (normalized) and whether this branch already stocks it."""
    market = await get_user_market(user, db)

    code = normalize_barcode(barcode)
    gi = None
    if code:
        gi = (await db.execute(select(GlobalItem).where(GlobalItem.barcode == code))).unique().scalar_one_or_none()
    # Blocked products are never visible; products under review only to the merchant who created them
    if gi is None or gi.moderation_status == "blocked" or (
        gi.moderation_status != "approved" and gi.created_by != user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found in global catalog.",
        )

    mi = (await db.execute(
        select(MarketItem).where(MarketItem.market_id == market.id, MarketItem.item_id == gi.id)
    )).scalar_one_or_none()

    return BarcodeLookupResponse(
        exists_in_branch=mi is not None,
        market_item_id=mi.id if mi else None,
        global_item_id=gi.id,
        name=gi.name,
        category=gi.category,
        image_url=gi.image_url,
        price=float(mi.price) if (mi and mi.price is not None) else None,
        stock_count=mi.stock_count if mi else None,
        barcode=barcode,
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
        if item.quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Quantity must be positive (got {item.quantity}).",
            )
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


