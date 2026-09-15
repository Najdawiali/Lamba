"""Customer V1 API — Near-market search, spatial queries, and shop categorized catalog.

Every endpoint that returns personalised data or mutates state requires an
authenticated customer (`Depends(require_customer)`). Identity is taken from
the JWT, never from the request body/query — preventing impersonation.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.elements import WKTElement
from geoalchemy2 import Geometry, Geography
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.auth import require_customer
from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.models.rating import Rating
from app.models.user import User
from app.models.search_alert import SearchAlert
from app.models.search_history import SearchHistory
from app.schemas.customer_v1 import (
    NearMarketResponse,
    CustomerItemResponse,
    MarketCatalogResponse,
    NearbyItemResponse,
    RatingCreate,
    RatingResponse,
    RatingDetailResponse,
    MarketRatingSummaryResponse,
    CategoryNodeResponse,
    SearchAlertResponse,
    MarketItemDetailsResponse,
    SearchHistoryEntry,
    SearchHistoryCreate,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)
from app.schemas.special_offer import CustomerSpecialOfferResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/customer", tags=["Customer V1"])



# ── GET /near-markets ───────────────────────────────────────────
@router.get("/near-markets", response_model=List[NearMarketResponse])
async def get_near_markets(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude of user"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude of user"),
    radius_km: float = Query(5.0, gt=0.0, description="Proximity radius in kilometers"),
    db: AsyncSession = Depends(get_db),
):
    """
    Geospatial Proximity query searching for physical shops/markets within a metric distance radius.
    Casts PostGIS coordinates to Geography to compute high-performance metric distance in kilometers.
    Sorted by nearest first, capped at a maximum of 5 shops.
    """
    try:
        # Create user location WKTElement POINT
        point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        
        # Cast shapes to Geography for accurate distance calculations in meters
        geog_location = Market.location.cast(Geography)
        geog_point = func.cast(point_wkt, Geography)
        
        # Calculate radius limit in meters (ST_DWithin expects meters on geography)
        radius_meters = radius_km * 1000.0
        
        # ST_Distance returns distance in meters on geography. Divide by 1000 to get kilometers.
        distance_expression = (func.ST_Distance(geog_location, geog_point) / 1000.0).label("distance_km")
        
        # Subqueries for rating aggregates
        avg_rating_subquery = (
            select(func.coalesce(func.avg(Rating.score), 0.0))
            .where(Rating.market_id == Market.id)
            .scalar_subquery()
        )
        count_rating_subquery = (
            select(func.count(Rating.id))
            .where(Rating.market_id == Market.id)
            .scalar_subquery()
        )

        # Query matching shops sorted by computed distance up to a limit of 5
        query = (
            select(
                Market,
                func.ST_Y(Market.location.cast(Geometry)).label("lat"),
                func.ST_X(Market.location.cast(Geometry)).label("lng"),
                distance_expression,
                avg_rating_subquery.label("avg_rating"),
                count_rating_subquery.label("total_reviews")
            )
            .where(func.ST_DWithin(geog_location, geog_point, radius_meters))
            .order_by("distance_km")
            .limit(5)
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        # Run dynamic schedule update to ensure freshness
        unique_markets = list({row[0].id: row[0] for row in rows}.values())
        if unique_markets:
            from app.utils.schedule import check_and_update_markets_schedule
            await check_and_update_markets_schedule(db, unique_markets)
            
        markets_list = []
        for row in rows:
            market, lat, lng, dist_km, avg_rating, total_reviews = row[0], row[1], row[2], row[3], row[4], row[5]
            markets_list.append(
                NearMarketResponse(
                    id=market.id,
                    merchant_id=market.merchant_id,
                    name=market.name,
                    name_ar=getattr(market, "name_ar", None),
                    name_en=getattr(market, "name_en", None),
                    address=market.address,
                    latitude=float(lat),
                    longitude=float(lng),
                    distance_km=round(float(dist_km), 2),
                    phone=market.phone,
                    is_currently_open=market.is_currently_open,
                    is_manual_override=market.is_manual_override,
                    override_set_at=market.override_set_at,
                    average_rating=round(float(avg_rating), 1),
                    total_reviews=int(total_reviews),
                    created_at=market.created_at
                )
            )
            
        return markets_list
        
    except Exception as e:
        logger.error(f"Geospatial proximity query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while executing the proximity search.",
        )


# ── GET /nearby-items ──────────────────────────────────────────
@router.get("/nearby-items", response_model=List[NearbyItemResponse])
async def get_nearby_items(
    latitude: float = Query(..., ge=-90.0, le=90.0),
    longitude: float = Query(..., ge=-180.0, le=180.0),
    radius_km: float = Query(15.0, ge=0.1, le=100.0),
    limit: int = Query(12, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve featured in-stock items from nearby stores for the explore feed.
    """
    try:
        user_point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
        geog_point = user_point.cast(Geography)
        geog_location = Market.location.cast(Geography)
        radius_meters = radius_km * 1000.0

        stmt = (
            select(
                MarketItem,
                GlobalItem,
                Market,
            )
            .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
            .join(Market, MarketItem.market_id == Market.id)
            .options(
                selectinload(GlobalItem.images),
                selectinload(GlobalItem.category_rel),
            )
            .where(
                MarketItem.status == True,
                MarketItem.stock_count > 0,
                func.ST_DWithin(geog_location, geog_point, radius_meters),
            )
            .order_by(MarketItem.id)
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()

        items = []
        for market_item, global_item, market in rows:
            img_url = None
            if global_item.images:
                img_url = global_item.images[0].image_url

            cat_rel = getattr(global_item, "category_rel", None)
            cat_name = cat_rel.name if cat_rel else global_item.category
            cat_name_ar = getattr(cat_rel, "name_ar", None) if cat_rel else None
            cat_name_en = getattr(cat_rel, "name_en", None) if cat_rel else None

            items.append(
                NearbyItemResponse(
                    id=global_item.id,
                    market_item_id=market_item.id,
                    name=global_item.name,
                    name_ar=global_item.name_ar,
                    name_en=global_item.name_en,
                    price=float(market_item.price or 0.0),
                    market_id=market.id,
                    market_name=market.name,
                    market_name_ar=getattr(market, "name_ar", None),
                    market_name_en=getattr(market, "name_en", None),
                    category_name=cat_name,
                    category_name_ar=cat_name_ar,
                    category_name_en=cat_name_en,
                    image_url=img_url,
                    is_in_stock=bool(market_item.stock_count > 0),
                )
            )

        return items
    except Exception as e:
        logger.error(f"Failed to fetch nearby items: {e}", exc_info=True)
        return []


# ── GET /market/{market_id}/items ───────────────────────────────
@router.get("/market/{market_id}/items", response_model=MarketCatalogResponse)
async def get_market_catalog(
    market_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve categorized inventory catalog for a target physical shop location.
    Returns all merchant-active items (including zero-stock, so the customer app
    can render an "Out of Stock" badge). The ``in_stock`` flag reflects real
    availability (stock_count > 0) so the UI overlay activates correctly.
    """
    # Verify the market exists
    market_exists = await db.execute(select(Market).where(Market.id == market_id))
    market = market_exists.scalar_one_or_none()
    if not market:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop location not found.",
        )
        
    # Run dynamic schedule update to ensure freshness
    from app.utils.schedule import check_and_update_markets_schedule
    await check_and_update_markets_schedule(db, [market])
        
    # Join market_items and global_items for the target market
    # Show all merchant-active items, including out-of-stock ones so the
    # mobile "Out of Stock" overlay can actually trigger.
    query = (
        select(MarketItem, GlobalItem)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .options(
            selectinload(GlobalItem.category_rel),
            selectinload(GlobalItem.images)
        )
        .where(
            MarketItem.market_id == market_id,
            MarketItem.status == True,
        )
        .order_by(GlobalItem.name)
    )
    
    result = await db.execute(query)
    rows = result.unique().all()
    
    catalog: Dict[str, List[CustomerItemResponse]] = {}
    
    for row in rows:
        mi, gi = row[0], row[1]
        cat_rel = getattr(gi, "category_rel", None)
        category_name = cat_rel.name if cat_rel else (gi.category or "Grocery")
        cat_ar = cat_rel.name_ar if cat_rel else None
        cat_en = cat_rel.name_en if cat_rel else None
        category_name = category_name.strip() if category_name.strip() else "Grocery"
        
        item_resp = CustomerItemResponse(
            id=gi.id,
            market_item_id=mi.id,
            name=gi.name,
            name_ar=getattr(gi, "name_ar", None),
            name_en=getattr(gi, "name_en", None),
            description=gi.description,
            category=category_name,
            category_name_ar=cat_ar,
            category_name_en=cat_en,
            image_url=gi.image_url,
            stock_count=mi.stock_count,
            in_stock=mi.stock_count > 0,
            price=float(mi.price) if mi.price is not None else None
        )
        
        if category_name not in catalog:
            catalog[category_name] = []
        catalog[category_name].append(item_resp)
        
    return catalog


# ── POST /purchase was removed ──────────────────────────────────
# Lamba is a discovery app, not a storefront. The cart/purchase flow was
# dead/fake (no cart state anywhere in the mobile app) and was a security
# hole (no auth + free stock decrement). Repair alerts are handled by the
# SearchAlert lifecycle instead. See backend alert_service for resolution.


@router.get("/categories", response_model=List[CategoryNodeResponse])
async def get_categories_tree(
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve the entire hierarchical category tree recursively in a single query.
    """
    from app.models.category import Category
    
    result = await db.execute(select(Category).order_by(Category.name))
    all_categories = result.scalars().all()
    
    # Build tree in memory
    from collections import defaultdict
    by_parent = defaultdict(list)
    roots = []
    
    for cat in all_categories:
        if cat.parent_category_id is None:
            roots.append(cat)
        else:
            by_parent[cat.parent_category_id].append(cat)
            
    category_ar_map = {
        "Food & Beverages": "الأغذية والمشروبات",
        "Home & Personal Care": "العناية المنزلية والشخصية",
        "Electronics & Tech": "الإلكترونيات والتقنية",
        "Home & Kitchen": "المنزل والمطبخ",
        "Services": "الخدمات",
        "Fruits & Vegetables": "الخضار والفواكه",
        "Cooking Essentials": "مستلزمات الطبخ",
        "Dairy & Eggs": "الألبان والبيض",
        "Meat & Poultry": "اللحوم والدواجن",
        "Beverages": "المشروبات",
        "Snacks": "المأكولات الخفيفة",
        "Bakery": "المخبوزات",
        "Frozen Food": "الأطعمة المجمدة",
        "Cleaning & Detergents": "التنظيف المنزلي",
        "Beauty & Personal Care": "العناية الشخصية",
        "Electronics": "الإلكترونيات",
        "Mobiles & Tech": "الهواتف والتقنية",
        "Cookware & Kitchenware": "أدوات المطبخ",
        "Beauty & Personal Care Services": "خدمات التجميل والعناية الشخصية",
        "Vehicle Maintenance & Care": "صيانة وتغسيل السيارات",
        "Home & Maintenance Services": "خدمات وصيانة المنازل",
        "Education & Tutoring": "التعليم والدروس الخصوصية",
    }

    def format_cat(cat: Category):
        subs = by_parent[cat.id]
        name_ar = getattr(cat, "name_ar", None) or category_ar_map.get(cat.name, cat.name)
        return {
            "id": cat.id,
            "name": cat.name,
            "name_ar": name_ar,
            "name_en": getattr(cat, "name_en", None) or cat.name,
            "listing_type": getattr(cat, "listing_type", None),
            "subcategories": [format_cat(s) for s in subs]
        }
        
    return [format_cat(rc) for rc in roots]


@router.get("/alerts", response_model=List[SearchAlertResponse])
async def get_customer_alerts(
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all active and inactive search alerts for the authenticated customer.
    Auto-resolves alerts if matching items now exist in the catalog.
    """
    from app.services.alert_service import resolve_matching_alerts
    await resolve_matching_alerts(db)

    result = await db.execute(
        select(SearchAlert)
        .where(SearchAlert.user_id == user.id)
        .order_by(SearchAlert.created_at.desc())
    )
    alerts = result.scalars().all()
    return alerts


@router.get("/item/{market_item_id}", response_model=MarketItemDetailsResponse)
async def get_market_item_details(
    market_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed customer-facing product information, shop operating parameters,
    multiple images, and branch staff directories for a single market item.
    """
    from app.models.category import Category
    from app.models.product_image import ProductImage

    # Query market item with explicit joins to avoid MissingGreenlet
    stmt = (
        select(MarketItem, GlobalItem, Market)
        .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
        .join(Market, MarketItem.market_id == Market.id)
        .where(MarketItem.id == market_item_id)
    )
    result = await db.execute(stmt)
    row = result.unique().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product or Shop listing not found.",
        )
        
    mi, gi, market = row[0], row[1], row[2]
    
    # Run dynamic schedule update to ensure freshness
    from app.utils.schedule import check_and_update_markets_schedule
    await check_and_update_markets_schedule(db, [market])
    
    # Query multiple images for this global item to be completely safe from MissingGreenlet
    images_result = await db.execute(
        select(ProductImage)
        .where(ProductImage.global_item_id == gi.id)
        .order_by(ProductImage.is_primary.desc(), ProductImage.created_at)
    )
    images = images_result.scalars().all()
    image_urls = [img.image_url for img in images]
    
    # Query category name safely
    cat_name = None
    cat_ar = None
    cat_en = None
    if gi.category_id:
        cat_result = await db.execute(
            select(Category.name, Category.name_ar, Category.name_en).where(Category.id == gi.category_id)
        )
        cat_row = cat_result.first()
        if cat_row:
            cat_name = cat_row[0]
            cat_ar = cat_row[1]
            cat_en = cat_row[2]
        
    # Get coordinates
    coords_res = await db.execute(
        select(
            func.ST_Y(Market.location.cast(Geometry)).label("lat"),
            func.ST_X(Market.location.cast(Geometry)).label("lng")
        )
        .where(Market.id == market.id)
    )
    coords_row = coords_res.first()
    lat = float(coords_row[0]) if coords_row else 0.0
    lng = float(coords_row[1]) if coords_row else 0.0
    
    # Format employee directory list of dicts to list of strings safely
    formatted_employees = []
    if market.employee_directory:
        for emp in market.employee_directory:
            if isinstance(emp, dict):
                name = emp.get("name") or emp.get("Name") or ""
                role = emp.get("role") or emp.get("Role") or ""
                contact = emp.get("contact") or emp.get("Contact") or ""
                parts = []
                if name:
                    parts.append(name)
                if role:
                    parts.append(f"({role})")
                if contact:
                    parts.append(f"- {contact}")
                if parts:
                    formatted_employees.append(" ".join(parts).strip())
            elif isinstance(emp, str):
                formatted_employees.append(emp)
            else:
                formatted_employees.append(str(emp))

    # Query ratings aggregates for the market
    ratings_agg_res = await db.execute(
        select(
            func.coalesce(func.avg(Rating.score), 0.0),
            func.count(Rating.id)
        ).where(Rating.market_id == market.id)
    )
    avg_score, total_count = ratings_agg_res.first() or (0.0, 0)

    return {
        "id": str(mi.id),
        "item_id": str(gi.id),
        "name": gi.name,
        "name_ar": getattr(gi, "name_ar", None),
        "name_en": getattr(gi, "name_en", None),
        "description": gi.description,
        "category": cat_name or "Grocery",
        "category_name_ar": cat_ar,
        "category_name_en": cat_en,
        "image_url": gi.image_url,
        "images": image_urls if image_urls else ([gi.image_url] if gi.image_url else []),
        "stock_count": mi.stock_count,
        "price": float(mi.price) if mi.price is not None else None,
        "in_stock": mi.status,
        "shop": {
            "id": str(market.id),
            "name": market.name,
            "address": market.address,
            "latitude": lat,
            "longitude": lng,
            "phone": market.phone,
            "business_nature": market.business_nature or "Grocery",
            "operating_hours": market.operating_hours,
            "employee_directory": formatted_employees if formatted_employees else None,
            "is_currently_open": market.is_currently_open,
            "is_manual_override": market.is_manual_override,
            "override_set_at": market.override_set_at,
            "average_rating": round(float(avg_score), 1),
            "total_reviews": int(total_count),
        }
    }


# ── GET /offers ─────────────────────────────────────────────────
@router.get("/offers", response_model=List[CustomerSpecialOfferResponse])
async def get_customer_offers(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Latitude of user"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Longitude of user"),
    query: Optional[str] = Query(None, description="Optional search term matching product/shop name"),
    offer_type: Optional[str] = Query(None, description="Filter by offer type"),
    max_distance_km: Optional[float] = Query(None, gt=0.0, description="Optional maximum distance filter in km"),
    category_id: Optional[uuid.UUID] = Query(None, description="Optional category filter ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all active, non-expired offers from the offers table.
    Sorted by a dynamic proximity + offer power score.
    """
    from app.models.offer import Offer
    from app.models.category import Category
    from sqlalchemy import or_

    def _compute_power(offer_type: str, config: dict) -> float:
        """Derive a sorting power score from offer config."""
        if not config:
            return 50.0
        if offer_type == 'percentage':
            return float(config.get('percent', 50))
        elif offer_type == 'fixed_amount':
            return min(float(config.get('amount', 1)) * 20, 100.0)
        elif offer_type == 'buy_x_get_y':
            buy = float(config.get('buy', 1))
            get = float(config.get('get', 1))
            return min((get / buy) * 100, 100.0) if buy > 0 else 50.0
        elif offer_type == 'quantity_price':
            return 60.0
        return 50.0

    def _compute_discount_pct(offer_type: str, config: dict) -> Optional[float]:
        """Derive discount percentage for backward compat."""
        if not config:
            return None
        if offer_type == 'percentage':
            return config.get('percent')
        return None

    def _compute_discounted_price(offer_type: str, config: dict, price: Optional[float]) -> Optional[float]:
        """
        Return the effective price after the offer is applied.
        None means the offer does not change the unit price
        (e.g. buy_x_get_y, quantity_price).
        """
        if price is None or not config:
            return None
        if offer_type == 'percentage':
            pct = config.get('percent')
            if pct and 0 < float(pct) < 100:
                return round(float(price) * (1 - float(pct) / 100), 2)
        elif offer_type == 'fixed_amount':
            amt = config.get('amount')
            if amt and 0 < float(amt) < float(price):
                return round(float(price) - float(amt), 2)
        return None

    def _offer_summary(offer_type: str, config: dict) -> str:
        """Human-readable offer summary."""
        if not config:
            return ''
        if offer_type == 'percentage':
            return f"{config.get('percent', 0)}% off"
        elif offer_type == 'fixed_amount':
            return f"{config.get('amount', 0)} JOD off"
        elif offer_type == 'buy_x_get_y':
            return f"Buy {config.get('buy', 0)} Get {config.get('get', 0)} Free"
        elif offer_type == 'quantity_price':
            return f"{config.get('quantity', 0)} for {config.get('price', 0)} JOD"
        return ''

    # Map customer-facing filter values to actual offer_type values
    OFFER_TYPE_MAP = {
        'BOGO': 'buy_x_get_y',
        'DISCOUNT': 'percentage',
    }

    try:
        point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        geog_location = Market.location.cast(Geography)
        geog_point = func.cast(point_wkt, Geography)
        distance_expression = (func.ST_Distance(geog_location, geog_point) / 1000.0).label("distance_km")

        stmt = (
            select(
                Offer,
                MarketItem,
                GlobalItem,
                Market,
                Category,
                func.ST_Y(Market.location.cast(Geometry)).label("lat"),
                func.ST_X(Market.location.cast(Geometry)).label("lng"),
                distance_expression,
            )
            .join(MarketItem, Offer.market_item_id == MarketItem.id)
            .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
            .join(Market, Offer.market_id == Market.id)
            .outerjoin(Category, GlobalItem.category_id == Category.id)
            .where(
                Offer.is_active == True,
                MarketItem.status == True,
                or_(
                    Offer.expires_at.is_(None),
                    Offer.expires_at > datetime.now(timezone.utc),
                ),
            )
        )

        # Apply filters
        if query and query.strip():
            search_str = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    GlobalItem.name.ilike(search_str),
                    GlobalItem.description.ilike(search_str),
                    Market.name.ilike(search_str)
                )
            )

        if offer_type:
            mapped_type = OFFER_TYPE_MAP.get(offer_type.upper(), offer_type)
            stmt = stmt.where(Offer.offer_type == mapped_type)

        if max_distance_km is not None:
            radius_meters = max_distance_km * 1000.0
            stmt = stmt.where(func.ST_DWithin(geog_location, geog_point, radius_meters))

        if category_id:
            stmt = stmt.where(GlobalItem.category_id == category_id)

        result = await db.execute(stmt)
        rows = result.unique().all()

        # Run dynamic schedule update to ensure freshness
        unique_markets = list({row[3].id: row[3] for row in rows}.values())
        if unique_markets:
            from app.utils.schedule import check_and_update_markets_schedule
            await check_and_update_markets_schedule(db, unique_markets)

        offers_list = []
        for row in rows:
            offer, mi, gi, market, cat = row[0], row[1], row[2], row[3], row[4]
            lat, lng, dist_km = row[5], row[6], row[7]
            config = offer.config or {}
            power = _compute_power(offer.offer_type, config)
            score = power / (1.0 + float(dist_km))

            offers_list.append(
                CustomerSpecialOfferResponse(
                    id=offer.id,
                    market_item_id=offer.market_item_id,
                    offer_type=offer.offer_type,
                    config=config,
                    discount_percentage=_compute_discount_pct(offer.offer_type, config),
                    description=offer.description,
                    offer_summary=_offer_summary(offer.offer_type, config),
                    power=power,
                    is_active=offer.is_active,
                    created_at=offer.created_at,
                    expires_at=offer.expires_at,
                    product_id=gi.id,
                    product_name=gi.name,
                    product_description=gi.description,
                    price=mi.price,
                    discounted_price=_compute_discounted_price(offer.offer_type, config, mi.price),
                    category=gi.category,
                    category_name_ar=cat.name_ar if cat else None,
                    category_name_en=cat.name_en if cat else None,
                    image_url=gi.image_url,
                    stock_count=mi.stock_count,
                    in_stock=mi.status,
                    shop_id=market.id,
                    shop_name=market.name,
                    shop_address=market.address,
                    latitude=float(lat),
                    longitude=float(lng),
                    shop_is_open=market.is_currently_open,
                    distance_km=round(float(dist_km), 2),
                    sorting_score=round(score, 2)
                )
            )

        # Sort by score descending
        offers_list.sort(key=lambda o: o.sorting_score, reverse=True)
        return offers_list

    except Exception as e:
        logger.error(f"Failed to fetch special offers for customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while compiling special offers.",
        )


# ── POST /rating ────────────────────────────────────────────────
@router.post("/rating", response_model=RatingResponse)
async def create_location_verified_rating(
    payload: RatingCreate,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """
    Submits or updates a 1-to-5 star rating and optional review for a physical store/market.
    Identity is taken from the JWT (``user``), NOT the request body, so a caller cannot
    rate on behalf of another customer. Strictly verifies the user's current coordinates
    using PostGIS ST_Distance to enforce a 50 m geofence around the shop.
    """
    customer_id = user.id
    try:
        # 1. Verify the market exists
        market_stmt = select(Market).where(Market.id == payload.market_id)
        market_result = await db.execute(market_stmt)
        market = market_result.scalar_one_or_none()
        if not market:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop location not found."
            )

        # 2. Defensive sanity check: if a legacy customer_id is supplied, it must match the JWT user
        if payload.customer_id is not None and payload.customer_id != customer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Customer identity in payload does not match the authenticated user.",
            )

        # 3. Check for existing rating (One-Review-Per-Customer-Per-Shop)
        existing_stmt = select(Rating).where(
            Rating.market_id == payload.market_id,
            Rating.customer_id == customer_id
        )
        existing_result = await db.execute(existing_stmt)
        existing_rating = existing_result.scalar_one_or_none()

        # 4. Perform GPS Geofence Verification (verify <= 50 meters distance)
        point_wkt = WKTElement(f"POINT({payload.longitude} {payload.latitude})", srid=4326)
        geog_location = Market.location.cast(Geography)
        geog_point = func.cast(point_wkt, Geography)

        distance_stmt = select(func.ST_Distance(geog_location, geog_point)).where(Market.id == payload.market_id)
        distance_result = await db.execute(distance_stmt)
        distance_meters = distance_result.scalar()

        if distance_meters is None or distance_meters > 50.0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Location verification failed. You must be physically at the shop "
                    "(within 50 meters) to leave a verified review."
                )
            )

        # 5. Insert or Update rating
        if existing_rating:
            existing_rating.score = payload.score
            existing_rating.review = payload.review
            existing_rating.created_at = datetime.now(timezone.utc)
        else:
            new_rating = Rating(
                market_id=payload.market_id,
                customer_id=customer_id,
                score=payload.score,
                review=payload.review,
                created_at=datetime.now(timezone.utc)
            )
            db.add(new_rating)

        await db.commit()

        return RatingResponse(
            status="completed rating",
            stored_at=datetime.now(timezone.utc)
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to submit rating: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while storing your rating."
        )


# ── GET /market/{market_id}/ratings ────────────────────────────
@router.get("/market/{market_id}/ratings", response_model=MarketRatingSummaryResponse)
async def get_market_ratings(
    market_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all verified customer reviews, counts, and calculated average rating for a target market.
    """
    try:
        # Verify the market exists
        market_stmt = select(Market).where(Market.id == market_id)
        market_result = await db.execute(market_stmt)
        market = market_result.scalar_one_or_none()
        if not market:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop location not found."
            )

        # Query all ratings with joined customer profiles to fetch user names
        ratings_stmt = (
            select(Rating, User.full_name, User.email)
            .join(User, Rating.customer_id == User.id)
            .where(Rating.market_id == market_id)
            .order_by(Rating.created_at.desc())
        )
        ratings_result = await db.execute(ratings_stmt)
        rows = ratings_result.all()

        ratings_list = []
        total_score = 0.0

        for rating, full_name, email in rows:
            total_score += rating.score
            ratings_list.append(
                RatingDetailResponse(
                    id=rating.id,
                    customer_name=full_name or (email.split("@")[0] if email else "Anonymous"),
                    score=rating.score,
                    review=rating.review,
                    created_at=rating.created_at
                )
            )
            
        total_count = len(ratings_list)
        average_score = round(total_score / total_count, 1) if total_count > 0 else 0.0
        
        return MarketRatingSummaryResponse(
            average_score=average_score,
            total_reviews_count=total_count,
            ratings=ratings_list
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to fetch market ratings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while compiling store reviews."
        )


# ── GET /search-history ───────────────────────────────────────
@router.get("/search-history", response_model=List[SearchHistoryEntry])
async def get_search_history(
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve the authenticated customer's recent search history, newest first.
    """
    try:
        result = await db.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user.id)
            .order_by(SearchHistory.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Failed to fetch search history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching search history."
        )


# ── POST /search-history ──────────────────────────────────────
@router.post("/search-history", response_model=SearchHistoryEntry, status_code=status.HTTP_201_CREATED)
async def add_search_history(
    payload: SearchHistoryCreate,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """
    Record a new search to the authenticated customer's history.
    Deduplicates consecutive identical queries (case-insensitive).
    """
    query_text = (payload.query_text or "").strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="query_text must not be empty.",
        )
    try:
        # Check if the most recent entry has the same query
        last = await db.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user.id)
            .order_by(SearchHistory.created_at.desc())
            .limit(1)
        )
        last_entry = last.scalar_one_or_none()
        if last_entry and last_entry.query_text.lower().strip() == query_text.lower():
            # Update the result count and timestamp of existing entry instead of creating duplicate
            last_entry.result_count = payload.result_count
            last_entry.created_at = datetime.now(timezone.utc)
            last_entry.search_type = payload.search_type
            await db.commit()
            await db.refresh(last_entry)
            return last_entry

        entry = SearchHistory(
            user_id=user.id,
            query_text=query_text,
            search_type=payload.search_type,
            result_count=payload.result_count,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add search history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding search history."
        )


# ── DELETE /search-history ────────────────────────────────────
@router.delete("/search-history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_search_history(
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete all search history entries for the authenticated customer.
    """
    try:
        from sqlalchemy import delete as sql_delete
        await db.execute(
            sql_delete(SearchHistory).where(SearchHistory.user_id == user.id)
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to clear search history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while clearing search history."
        )


# ── PATCH /profile ────────────────────────────────────────────
@router.patch("/profile", response_model=ProfileUpdateResponse)
async def update_customer_profile(
    body: ProfileUpdateRequest,
    user: User = Depends(require_customer),
    db: AsyncSession = Depends(get_db),
):
    """
    Update the authenticated customer's profile (display name, phone).
    Only provided (non-None) fields are updated.
    """
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.phone_number is not None:
        user.phone_number = body.phone_number.strip()
    await db.commit()
    await db.refresh(user)
    return user




