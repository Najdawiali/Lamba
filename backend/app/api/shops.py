"""
Shops API — CRUD for merchant shop management.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from geoalchemy2.elements import WKTElement
from geoalchemy2 import Geometry
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.shop import Shop
from app.models.user import User
from app.schemas.shop import ShopCreate, ShopUpdate, ShopResponse
from app.api.auth import get_current_user, require_merchant

router = APIRouter(prefix="/api/shops", tags=["Shops"])


def _shop_to_response(shop: Shop, lat: float, lng: float) -> ShopResponse:
    """Convert a Shop model instance to a response schema."""
    return ShopResponse(
        id=shop.id,
        owner_id=shop.owner_id,
        name=shop.name,
        address=shop.address,
        latitude=lat,
        longitude=lng,
        phone=shop.phone,
        image_url=shop.image_url,
        is_active=shop.is_active,
        created_at=shop.created_at,
    )


@router.post("/", response_model=ShopResponse, status_code=201)
async def create_shop(
    data: ShopCreate,
    user: User = Depends(require_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new shop (merchant only)."""
    shop = Shop(
        owner_id=user.id,
        name=data.name,
        address=data.address,
        phone=data.phone,
        image_url=data.image_url,
        location=WKTElement(
            f"POINT({data.longitude} {data.latitude})", srid=4326
        ),
    )
    db.add(shop)
    await db.flush()

    return _shop_to_response(shop, data.latitude, data.longitude)


@router.get("/mine", response_model=list[ShopResponse])
async def get_my_shops(
    user: User = Depends(require_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Get all shops owned by the current merchant."""
    result = await db.execute(
        select(
            Shop,
            func.ST_Y(Shop.location.cast(Geometry)).label("lat"),
            func.ST_X(Shop.location.cast(Geometry)).label("lng"),
        ).where(Shop.owner_id == user.id)
    )
    shops = []
    for row in result.all():
        shops.append(_shop_to_response(row[0], row[1], row[2]))
    return shops


@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single shop by ID."""
    result = await db.execute(
        select(
            Shop,
            func.ST_Y(Shop.location.cast(Geometry)).label("lat"),
            func.ST_X(Shop.location.cast(Geometry)).label("lng"),
        ).where(Shop.id == shop_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Shop not found")

    return _shop_to_response(row[0], row[1], row[2])


@router.put("/{shop_id}", response_model=ShopResponse)
async def update_shop(
    shop_id: uuid.UUID,
    data: ShopUpdate,
    user: User = Depends(require_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Update a shop (owner only)."""
    result = await db.execute(select(Shop).where(Shop.id == shop_id))
    shop = result.scalar_one_or_none()

    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    if shop.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your shop")

    update_data = data.model_dump(exclude_unset=True)

    # Handle location update
    lat = update_data.pop("latitude", None)
    lng = update_data.pop("longitude", None)
    if lat is not None and lng is not None:
        shop.location = WKTElement(f"POINT({lng} {lat})", srid=4326)

    for key, value in update_data.items():
        setattr(shop, key, value)

    await db.flush()

    # Return updated coordinates
    final_lat = lat if lat is not None else 0.0
    final_lng = lng if lng is not None else 0.0
    return _shop_to_response(shop, final_lat, final_lng)
