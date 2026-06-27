"""Pydantic schemas for V1 Customer endpoints."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class NearMarketResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    name: str
    address: str
    latitude: float
    longitude: float
    distance_km: float
    is_currently_open: bool
    is_manual_override: bool
    override_set_at: Optional[datetime] = None
    average_rating: float = 0.0
    total_reviews: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerItemResponse(BaseModel):
    id: uuid.UUID  # Catalog item ID (GlobalItem.id)
    market_item_id: uuid.UUID  # MarketItem.id for transaction tracking
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    stock_count: int
    in_stock: bool
    price: Optional[float] = None

    model_config = {"from_attributes": True}


# Schema for categorized list response, mapping category names to lists of items
MarketCatalogResponse = Dict[str, List[CustomerItemResponse]]


# ── Rating Schemas ──────────────────────────────────────────────
class RatingCreate(BaseModel):
    market_id: uuid.UUID = Field(..., description="ID of the physical store/market to rate")
    customer_id: uuid.UUID = Field(..., description="ID of the customer submitting the rating")
    score: int = Field(..., ge=1, le=5, description="Rating score from 1 to 5")
    review: Optional[str] = Field(None, max_length=1000, description="Optional written review comment")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude for location geofence validation")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude for location geofence validation")


class RatingResponse(BaseModel):
    status: str = Field("completed rating", description="Success status message")
    stored_at: datetime = Field(..., description="Timestamp indicating when the rating was stored")


class RatingDetailResponse(BaseModel):
    id: uuid.UUID
    customer_name: str
    score: int
    review: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MarketRatingSummaryResponse(BaseModel):
    average_score: float
    total_reviews_count: int
    ratings: List[RatingDetailResponse]


# ── Epic 6 Supporting Schemas ──────────────────────────────────
class CategoryNodeResponse(BaseModel):
    id: uuid.UUID
    name: str
    subcategories: List["CategoryNodeResponse"] = []

    model_config = {"from_attributes": True}


class SearchAlertResponse(BaseModel):
    id: uuid.UUID
    query_text: str
    is_active: bool
    created_at: datetime
    latitude: float
    longitude: float

    model_config = {"from_attributes": True}


class ShopDetails(BaseModel):
    id: uuid.UUID
    name: str
    address: str
    latitude: float
    longitude: float
    business_nature: Optional[str] = None
    operating_hours: Optional[Dict[str, Any]] = None
    employee_directory: Optional[List[str]] = None
    is_currently_open: bool
    is_manual_override: bool
    override_set_at: Optional[datetime] = None
    average_rating: float = 0.0
    total_reviews: int = 0

    model_config = {"from_attributes": True}


class MarketItemDetailsResponse(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    image_url: Optional[str] = None
    images: List[str] = []
    stock_count: int
    price: Optional[float] = None
    in_stock: bool
    shop: ShopDetails

    model_config = {"from_attributes": True}


class PurchaseRequest(BaseModel):
    customer_id: uuid.UUID
    market_item_id: uuid.UUID
    quantity: int = Field(1, ge=1)


class PurchaseResponse(BaseModel):
    success: bool
    message: str
    resolved_alerts_count: int


class SearchHistoryEntry(BaseModel):
    id: uuid.UUID
    query_text: str
    search_type: str
    result_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


