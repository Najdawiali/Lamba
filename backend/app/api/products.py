"""
Products API — CRUD + CSV upload + stock toggle.
"""
import csv
import io
import uuid
import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, StockToggle
from app.api.auth import require_merchant
from app.services.indexer import IndexerService
from app.es_client import get_es_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/products", tags=["Products"])


async def _get_shop_location(shop_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession):
    result = await db.execute(
        select(Shop, func.ST_Y(Shop.location.ST_AsText()).label("lat"),
               func.ST_X(Shop.location.ST_AsText()).label("lng"))
        .where(Shop.id == shop_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop = row[0]
    if shop.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not your shop")
    return shop, float(row[1]), float(row[2])


@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(data: ProductCreate, user: User = Depends(require_merchant), db: AsyncSession = Depends(get_db)):
    """Create a product and auto-index in Elasticsearch with CLIP embedding."""
    shop, lat, lng = await _get_shop_location(data.shop_id, user.id, db)
    product = Product(shop_id=data.shop_id, name=data.name, description=data.description,
                      price=data.price, category=data.category, image_url=data.image_url, in_stock=data.in_stock)
    db.add(product)
    await db.flush()
    es_client = get_es_client()
    indexer = IndexerService(es_client)
    await indexer.index_product(product_id=product.id, shop_id=product.shop_id, name=product.name,
        description=product.description, price=float(product.price) if product.price else None,
        category=product.category, image_url=product.image_url, in_stock=product.in_stock, latitude=lat, longitude=lng)
    return ProductResponse.model_validate(product)


@router.get("/shop/{shop_id}", response_model=list[ProductResponse])
async def get_shop_products(shop_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get all products for a specific shop."""
    result = await db.execute(select(Product).where(Product.shop_id == shop_id).order_by(Product.name))
    return [ProductResponse.model_validate(p) for p in result.scalars().all()]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a single product by ID."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductResponse.model_validate(product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(product_id: uuid.UUID, data: ProductUpdate,
                         user: User = Depends(require_merchant), db: AsyncSession = Depends(get_db)):
    """Update a product and re-index in Elasticsearch."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    shop_result = await db.execute(select(Shop).where(Shop.id == product.shop_id))
    shop = shop_result.scalar_one_or_none()
    if shop is None or shop.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your product")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)
    await db.flush()
    if "name" in update_data or "description" in update_data:
        loc = await db.execute(select(func.ST_Y(Shop.location.ST_AsText()).label("lat"),
                                      func.ST_X(Shop.location.ST_AsText()).label("lng")).where(Shop.id == product.shop_id))
        coords = loc.first()
        es_client = get_es_client()
        indexer = IndexerService(es_client)
        await indexer.index_product(product_id=product.id, shop_id=product.shop_id, name=product.name,
            description=product.description, price=float(product.price) if product.price else None,
            category=product.category, image_url=product.image_url, in_stock=product.in_stock,
            latitude=float(coords[0]), longitude=float(coords[1]))
    return ProductResponse.model_validate(product)


@router.patch("/{product_id}/stock", response_model=ProductResponse)
async def toggle_stock(product_id: uuid.UUID, data: StockToggle,
                       user: User = Depends(require_merchant), db: AsyncSession = Depends(get_db)):
    """Toggle stock status — lightweight partial ES update, no re-embedding."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    shop_result = await db.execute(select(Shop).where(Shop.id == product.shop_id))
    shop = shop_result.scalar_one_or_none()
    if shop is None or shop.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your product")
    product.in_stock = data.in_stock
    await db.flush()
    es_client = get_es_client()
    indexer = IndexerService(es_client)
    await indexer.update_stock(product.id, data.in_stock)
    return ProductResponse.model_validate(product)


@router.post("/upload-csv/{shop_id}", status_code=201)
async def upload_csv(shop_id: uuid.UUID, file: UploadFile = File(...),
                     user: User = Depends(require_merchant), db: AsyncSession = Depends(get_db)):
    """Bulk import products from CSV. Columns: name, description, price, category, in_stock"""
    if file.content_type not in ("text/csv", "application/vnd.ms-excel"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    shop, lat, lng = await _get_shop_location(shop_id, user.id, db)
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    products_to_index = []
    created_count = 0
    for row in reader:
        name = row.get("name", "").strip()
        if not name:
            continue
        price = None
        price_str = row.get("price", "").strip()
        if price_str:
            try:
                price = float(price_str)
            except ValueError:
                pass
        in_stock = row.get("in_stock", "true").strip().lower() in ("true", "1", "yes")
        product = Product(shop_id=shop_id, name=name, description=row.get("description", "").strip() or None,
                          price=price, category=row.get("category", "").strip() or None, in_stock=in_stock)
        db.add(product)
        await db.flush()
        products_to_index.append({"product_id": product.id, "shop_id": shop_id, "name": product.name,
            "description": product.description, "price": price, "category": product.category,
            "image_url": None, "in_stock": product.in_stock, "latitude": lat, "longitude": lng})
        created_count += 1
    es_client = get_es_client()
    indexer = IndexerService(es_client)
    indexed_count = await indexer.bulk_index(products_to_index)
    return {"message": f"Imported {created_count} products, indexed {indexed_count}",
            "created": created_count, "indexed": indexed_count}
