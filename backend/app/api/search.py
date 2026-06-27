"""
Search API — Text and Image search endpoints.

Both endpoints follow the same flow:
  1. Encode query (text string or uploaded image) via CLIP
  2. Query Elasticsearch kNN with geo-distance pre-filter
  3. Enrich results with shop data from PostgreSQL
  4. Return hybrid-ranked results
"""

import uuid
import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.shop import Shop
from app.schemas.search import (
    TextSearchRequest,
    SearchResponse,
    SearchResultItem,
    ShopInfo,
)
from app.services.embedding import embedding_service
from app.services.search import SearchService
from app.es_client import get_es_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["Search"])


# ── Helpers ─────────────────────────────────────────────────────
async def _enrich_with_shop_data(
    raw_results: list[dict],
    db: AsyncSession,
) -> list[SearchResultItem]:
    """
    Join raw ES results with shop data from PostgreSQL.
    Groups by shop_id to minimize database queries.
    """
    if not raw_results:
        return []

    # Collect unique shop IDs
    shop_ids = list({uuid.UUID(r["shop_id"]) for r in raw_results})

    # Fetch shops in one query
    result = await db.execute(select(Shop).where(Shop.id.in_(shop_ids)))
    shops = {shop.id: shop for shop in result.scalars().all()}

    enriched = []
    for r in raw_results:
        shop_id = uuid.UUID(r["shop_id"])
        shop = shops.get(shop_id)
        if not shop:
            continue  # Skip if shop not found (shouldn't happen)

        enriched.append(
            SearchResultItem(
                product_id=uuid.UUID(r["product_id"]),
                product_name=r["name"],
                description=r.get("description"),
                price=r.get("price"),
                category=r.get("category"),
                image_url=r.get("image_url"),
                in_stock=r.get("in_stock", True),
                shop=ShopInfo(
                    id=shop.id,
                    name=shop.name,
                    address=shop.address,
                    latitude=r["location"]["lat"],
                    longitude=r["location"]["lon"],
                    phone=shop.phone,
                ),
                distance_km=r["distance_km"],
                semantic_score=r["semantic_score"],
                hybrid_score=r["hybrid_score"],
            )
        )

    return enriched


# ── Text Search ─────────────────────────────────────────────────
@router.post("/text", response_model=SearchResponse)
async def text_search(
    request: TextSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Semantic text search.

    Converts the query string into a 512-d CLIP embedding and performs
    a kNN search against the product embedding index, pre-filtered by
    geographic distance. Results are ranked using the hybrid formula:

        score = 0.7 × cosine_similarity + 0.3 × proximity_score
    """
    # 1. Encode text query via CLIP
    query_vector = embedding_service.encode_text(request.query)

    # 2. Search Elasticsearch
    es_client = get_es_client()
    search_service = SearchService(es_client)
    raw_results = await search_service.search_by_vector(
        vector=query_vector,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
        in_stock_only=request.in_stock_only,
        category=request.category,
        limit=request.limit,
    )

    # 3. Enrich with shop data
    results = await _enrich_with_shop_data(raw_results, db)

    return SearchResponse(
        query=request.query,
        search_type="text",
        radius_km=request.radius_km,
        total_results=len(results),
        results=results,
    )


# ── Image Search ────────────────────────────────────────────────
@router.post("/image", response_model=SearchResponse)
async def image_search(
    image: UploadFile = File(..., description="Product image to search for"),
    latitude: float = Form(...),
    longitude: float = Form(...),
    radius_km: float = Form(5.0),
    in_stock_only: bool = Form(True),
    category: str | None = Form(None),
    limit: int = Form(20),
    db: AsyncSession = Depends(get_db),
):
    """
    Visual search (cross-modal retrieval).

    Processes the uploaded image through CLIP's Vision Transformer (ViT),
    generating a 512-d embedding in the SAME vector space as text embeddings.
    This enables finding products whose text descriptions are semantically
    similar to the uploaded image — true cross-modal retrieval.
    """
    # Validate file type
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WebP images are supported",
        )

    # 1. Read image and encode via CLIP ViT
    image_bytes = await image.read()
    query_vector = embedding_service.encode_image_bytes(image_bytes)

    # 2. Search Elasticsearch (same kNN query as text search)
    es_client = get_es_client()
    search_service = SearchService(es_client)
    raw_results = await search_service.search_by_vector(
        vector=query_vector,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        in_stock_only=in_stock_only,
        category=category,
        limit=limit,
    )

    # 3. Enrich with shop data
    results = await _enrich_with_shop_data(raw_results, db)

    return SearchResponse(
        query=None,
        search_type="image",
        radius_km=radius_km,
        total_results=len(results),
        results=results,
    )
