"""Pydantic schemas for search requests and responses."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class TextSearchRequest(BaseModel):
    """Text-based semantic search request."""
    query: str = Field(..., min_length=1, max_length=500)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(5.0, ge=0.1, le=50.0)
    in_stock_only: bool = True
    category: str | None = None
    limit: int = Field(20, ge=1, le=50)


class ImageSearchRequest(BaseModel):
    """
    Image-based visual search request.
    The image itself is uploaded as a multipart form field;
    these fields come as form data alongside the file.
    """
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_km: float = Field(5.0, ge=0.1, le=50.0)
    in_stock_only: bool = True
    category: str | None = None
    limit: int = Field(20, ge=1, le=50)


class ShopInfo(BaseModel):
    """Abbreviated shop info embedded in search results."""
    id: uuid.UUID
    name: str
    address: str
    latitude: float
    longitude: float
    phone: str | None


class SearchResultItem(BaseModel):
    """A single search result combining product, shop, and ranking data."""
    product_id: uuid.UUID
    product_name: str
    description: str | None
    price: Decimal | None
    category: str | None
    image_url: str | None
    in_stock: bool

    shop: ShopInfo
    distance_km: float = Field(..., description="Distance from user in km")
    semantic_score: float = Field(..., description="Cosine similarity (0-1)")
    hybrid_score: float = Field(..., description="Combined ranking score")


class SearchResponse(BaseModel):
    """Paginated search results."""
    query: str | None = None
    search_type: str = "text"  # "text" or "image"
    radius_km: float
    total_results: int
    results: list[SearchResultItem]
