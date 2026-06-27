"""Customer V1 API — Near-market search, spatial queries, and shop categorized catalog."""

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
from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.models.rating import Rating
from app.models.user import User
from app.models.search_alert import SearchAlert
from app.models.search_history import SearchHistory
import numpy as np
from app.schemas.customer_v1 import (
    NearMarketResponse,
    CustomerItemResponse,
    MarketCatalogResponse,
    RatingCreate,
    RatingResponse,
    RatingDetailResponse,
    MarketRatingSummaryResponse,
    CategoryNodeResponse,
    SearchAlertResponse,
    MarketItemDetailsResponse,
    PurchaseRequest,
    PurchaseResponse,
    SearchHistoryEntry,
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
                    address=market.address,
                    latitude=float(lat),
                    longitude=float(lng),
                    distance_km=round(float(dist_km), 2),
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
        logger.error(f"Geospatial proximity query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while executing the proximity search: {str(e)}",
        )


# ── GET /market/{market_id}/items ───────────────────────────────
@router.get("/market/{market_id}/items", response_model=MarketCatalogResponse)
async def get_market_catalog(
    market_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve categorized inventory catalog for a target physical shop location.
    Only returns active (in-stock status is True) items with actual inventory (stock_count > 0).
    Dynamically groups active market inventory by item category.
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
    # Filter to only active and in-stock items
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
            MarketItem.stock_count > 0
        )
        .order_by(GlobalItem.name)
    )
    
    result = await db.execute(query)
    rows = result.unique().all()
    
    catalog: Dict[str, List[CustomerItemResponse]] = {}
    
    for row in rows:
        mi, gi = row[0], row[1]
        category = gi.category or "Grocery"
        category = category.strip() if category.strip() else "Grocery"
        
        item_resp = CustomerItemResponse(
            id=gi.id,
            market_item_id=mi.id,
            name=gi.name,
            description=gi.description,
            category=category,
            image_url=gi.image_url,
            stock_count=mi.stock_count,
            in_stock=mi.status,
            price=float(mi.price) if mi.price is not None else None
        )
        
        if category not in catalog:
            catalog[category] = []
        catalog[category].append(item_resp)
        
    return catalog


# ── POST /rate ──────────────────────────────────────────────────
@router.post("/rate", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
async def rate_market(
    data: RatingCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit and persist a customer rating for a physical store location.
    Validates that the target market and customer actually exist, then stores
    the score (1-5) and optional written review.
    """
    # 1. Verify market exists
    market_result = await db.execute(select(Market).where(Market.id == data.market_id))
    if not market_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop location not found.",
        )
        
    # 2. Verify customer exists
    customer_result = await db.execute(select(User).where(User.id == data.customer_id))
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer account not found.",
        )
        
    # Validate user type/role is customer (safeguard)
    role = getattr(customer, "user_type", "customer")
    if role != "customer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only customer accounts can submit store reviews.",
        )
        
    try:
        # Create and persist Rating record
        rating = Rating(
            market_id=data.market_id,
            customer_id=data.customer_id,
            score=data.score,
            review=data.review,
            created_at=datetime.now(timezone.utc)
        )
        db.add(rating)
        await db.flush()
        
        return RatingResponse(
            status="completed rating",
            stored_at=rating.created_at
        )
        
    except Exception as e:
        logger.error(f"Persisting market rating failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while saving the rating: {str(e)}",
        )


@router.post("/purchase", response_model=PurchaseResponse)
async def purchase_item(
    data: PurchaseRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Simulates a successful purchase, reduces item stock count in DB,
    and resolves corresponding customer search alerts (Ticket 6.1 purchase verification).
    """
    try:
        # 1. Fetch MarketItem and link to GlobalItem with row-level lock
        result = await db.execute(
            select(MarketItem, GlobalItem)
            .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
            .where(MarketItem.id == data.market_item_id)
            .with_for_update(of=MarketItem)
        )
        row = result.unique().first()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found.",
            )
        
        market_item, global_item = row[0], row[1]
        
        if market_item.stock_count < data.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock. Available: {market_item.stock_count}",
            )
            
        # Reduce stock
        market_item.stock_count -= data.quantity
        if market_item.stock_count <= 0:
            market_item.stock_count = 0
            market_item.status = False
            
        await db.flush()
        
        # 2. Query customer active search alerts to resolve matches
        alerts_result = await db.execute(
            select(SearchAlert).where(
                SearchAlert.user_id == data.customer_id,
                SearchAlert.is_active == True
            )
        )
        alerts = alerts_result.scalars().all()
        
        resolved_count = 0
        product_vec = np.array(global_item.text_embedding) if global_item.text_embedding else None
        
        for alert in alerts:
            is_match = False
            
            # Substring/Token matching to avoid false positives (e.g. matching "tea" in "steak")
            gi_name_lower = global_item.name.lower()
            alert_query_lower = alert.query_text.lower()
            
            gi_words = set(gi_name_lower.split())
            alert_words = set(alert_query_lower.split())
            
            if gi_name_lower == alert_query_lower or (gi_words and alert_words and alert_words.issubset(gi_words)):
                is_match = True
            elif product_vec is not None and alert.query_vector:
                # Semantic cosine similarity comparison
                alert_vec = np.array(alert.query_vector)
                dot_val = np.dot(product_vec, alert_vec)
                norm_p = np.linalg.norm(product_vec)
                norm_a = np.linalg.norm(alert_vec)
                similarity = dot_val / (norm_p * norm_a) if norm_p > 0 and norm_a > 0 else 0.0
                
                if similarity > 0.75:  # Epic 6 specification
                    is_match = True
                    
            if is_match:
                alert.is_active = False
                resolved_count += 1
                
        await db.flush()
        
        return PurchaseResponse(
            success=True,
            message=f"Purchase completed. Resolving {resolved_count} active search intent alerts.",
            resolved_alerts_count=resolved_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Purchase process failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while executing the purchase.",
        )


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
            
    def format_cat(cat: Category):
        subs = by_parent[cat.id]
        return {
            "id": cat.id,
            "name": cat.name,
            "subcategories": [format_cat(s) for s in subs]
        }
        
    return [format_cat(rc) for rc in roots]


@router.get("/alerts", response_model=List[SearchAlertResponse])
async def get_customer_alerts(
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all active and inactive search alerts for a customer to track notifications.
    """
    result = await db.execute(
        select(SearchAlert)
        .where(SearchAlert.user_id == user_id)
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
    if gi.category_id:
        cat_result = await db.execute(
            select(Category.name).where(Category.id == gi.category_id)
        )
        cat_name = cat_result.scalar()
        
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
        "description": gi.description,
        "category": cat_name or "Grocery",
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
    offer_type: Optional[str] = Query(None, description="Filter by BOGO or DISCOUNT"),
    max_distance_km: Optional[float] = Query(None, gt=0.0, description="Optional maximum distance filter in km"),
    category_id: Optional[uuid.UUID] = Query(None, description="Optional category filter ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all active special offers across all physical stores, regardless of distance.
    Sorted by a dynamic proximity + offer power score:
    Score = Power / (1.0 + Distance_in_km)
    
    Includes filters for name/description search, offer type, category, and maximum distance constraint.
    """
    from app.models.special_offer import SpecialOffer
    from sqlalchemy import or_, text
    
    try:
        # Create user location WKTElement POINT
        point_wkt = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        
        # Cast shapes to Geography for accurate distance calculations in meters
        geog_location = Market.location.cast(Geography)
        geog_point = func.cast(point_wkt, Geography)
        
        # ST_Distance returns distance in meters on geography. Divide by 1000 to get kilometers.
        distance_expression = (func.ST_Distance(geog_location, geog_point) / 1000.0).label("distance_km")
        
        # Dynamic score expression: power / (1.0 + distance_km)
        # Add 1.0 to avoid division by zero if user is exactly on shop location
        score_expression = (SpecialOffer.power / (1.0 + (func.ST_Distance(geog_location, geog_point) / 1000.0))).label("sorting_score")
        
        # Select components
        stmt = (
            select(
                SpecialOffer,
                MarketItem,
                GlobalItem,
                Market,
                func.ST_Y(Market.location.cast(Geometry)).label("lat"),
                func.ST_X(Market.location.cast(Geometry)).label("lng"),
                distance_expression,
                score_expression
            )
            .join(MarketItem, SpecialOffer.market_item_id == MarketItem.id)
            .join(GlobalItem, MarketItem.item_id == GlobalItem.id)
            .join(Market, MarketItem.market_id == Market.id)
            .where(
                SpecialOffer.is_active == True,
                MarketItem.status == True,
                MarketItem.stock_count > 0
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
            stmt = stmt.where(SpecialOffer.offer_type == offer_type.upper())
            
        if max_distance_km is not None:
            # max_distance_km in meters
            radius_meters = max_distance_km * 1000.0
            stmt = stmt.where(func.ST_DWithin(geog_location, geog_point, radius_meters))
            
        if category_id:
            stmt = stmt.where(GlobalItem.category_id == category_id)
            
        # Order by computed score desc
        stmt = stmt.order_by(text("sorting_score DESC"))
        
        result = await db.execute(stmt)
        rows = result.unique().all()
        
        # Run dynamic schedule update to ensure freshness
        unique_markets = list({row[3].id: row[3] for row in rows}.values())
        if unique_markets:
            from app.utils.schedule import check_and_update_markets_schedule
            await check_and_update_markets_schedule(db, unique_markets)
            
        offers_list = []
        for row in rows:
            so, mi, gi, market = row[0], row[1], row[2], row[3]
            lat, lng, dist_km, sorting_score = row[4], row[5], row[6], row[7]
            
            offers_list.append(
                CustomerSpecialOfferResponse(
                    id=so.id,
                    market_item_id=so.market_item_id,
                    offer_type=so.offer_type,
                    discount_percentage=so.discount_percentage,
                    description=so.description,
                    power=so.power,
                    is_active=so.is_active,
                    created_at=so.created_at,
                    product_id=gi.id,
                    product_name=gi.name,
                    product_description=gi.description,
                    price=mi.price,
                    category=gi.category,
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
                    sorting_score=round(float(sorting_score), 2)
                )
            )
            
        return offers_list
        
    except Exception as e:
        logger.error(f"Failed to fetch special offers for customer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while compiling special offers: {str(e)}",
        )


# ── POST /rating ────────────────────────────────────────────────
@router.post("/rating", response_model=RatingResponse)
async def create_location_verified_rating(
    payload: RatingCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Submits or updates a 1-to-5 star rating and optional review for a physical store/market.
    Strictly verifies user's current coordinates using PostGIS ST_Distance to enforce geofence.
    """
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

        # 2. Verify the customer exists
        user_stmt = select(User).where(User.id == payload.customer_id)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer profile not found."
            )

        # 3. Check for existing rating (One-Review-Per-Customer-Per-Shop)
        existing_stmt = select(Rating).where(
            Rating.market_id == payload.market_id,
            Rating.customer_id == payload.customer_id
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
                detail=f"Location verification failed. You must be physically at the shop (within 50 meters) to leave a verified review. Current calculated distance: {round(distance_meters, 1) if distance_meters is not None else 'unknown'} meters."
            )

        # 5. Insert or Update rating
        if existing_rating:
            existing_rating.score = payload.score
            existing_rating.review = payload.review
            existing_rating.created_at = datetime.now(timezone.utc)
        else:
            new_rating = Rating(
                market_id=payload.market_id,
                customer_id=payload.customer_id,
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
        logger.error(f"Failed to submit rating: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while storing your rating: {str(e)}"
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
            select(Rating, User.name)
            .join(User, Rating.customer_id == User.id)
            .where(Rating.market_id == market_id)
            .order_by(Rating.created_at.desc())
        )
        ratings_result = await db.execute(ratings_stmt)
        rows = ratings_result.all()
        
        ratings_list = []
        total_score = 0.0
        
        for rating, user_name in rows:
            total_score += rating.score
            ratings_list.append(
                RatingDetailResponse(
                    id=rating.id,
                    customer_name=user_name,
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
        logger.error(f"Failed to fetch market ratings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while compiling store reviews: {str(e)}"
        )


# ── GET /search-history ───────────────────────────────────────
@router.get("/search-history", response_model=List[SearchHistoryEntry])
async def get_search_history(
    user_id: uuid.UUID = Query(..., description="User ID"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve the user's recent search history, newest first.
    """
    try:
        result = await db.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user_id)
            .order_by(SearchHistory.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Failed to fetch search history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching search history: {str(e)}"
        )


# ── POST /search-history ──────────────────────────────────────
@router.post("/search-history", response_model=SearchHistoryEntry, status_code=status.HTTP_201_CREATED)
async def add_search_history(
    user_id: uuid.UUID = Query(..., description="User ID"),
    query_text: str = Query(..., min_length=1, max_length=500),
    search_type: str = Query("text"),
    result_count: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Record a new search to the user's history. Deduplicates consecutive identical queries.
    """
    try:
        # Check if the most recent entry has the same query
        last = await db.execute(
            select(SearchHistory)
            .where(SearchHistory.user_id == user_id)
            .order_by(SearchHistory.created_at.desc())
            .limit(1)
        )
        last_entry = last.scalar_one_or_none()
        if last_entry and last_entry.query_text.lower().strip() == query_text.lower().strip():
            # Update the result count and timestamp of existing entry instead of creating duplicate
            last_entry.result_count = result_count
            last_entry.created_at = datetime.now(timezone.utc)
            last_entry.search_type = search_type
            await db.commit()
            await db.refresh(last_entry)
            return last_entry

        entry = SearchHistory(
            user_id=user_id,
            query_text=query_text.strip(),
            search_type=search_type,
            result_count=result_count,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry
    except Exception as e:
        logger.error(f"Failed to add search history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while adding search history: {str(e)}"
        )


# ── DELETE /search-history ────────────────────────────────────
@router.delete("/search-history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_search_history(
    user_id: uuid.UUID = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete all search history entries for a user.
    """
    try:
        from sqlalchemy import delete as sql_delete
        await db.execute(
            sql_delete(SearchHistory).where(SearchHistory.user_id == user_id)
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to clear search history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while clearing search history: {str(e)}"
        )



