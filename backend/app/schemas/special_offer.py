"""Pydantic schemas for Special Offer endpoints."""

import uuid
from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field


class SpecialOfferCreate(BaseModel):
    market_item_id: uuid.UUID = Field(..., description="ID of the market item listing")
    offer_type: str = Field(..., description="Offer type: 'BOGO' or 'DISCOUNT' or 'OTHER'")
    discount_percentage: Optional[float] = Field(None, ge=0.0, le=100.0, description="Optional discount percentage")
    description: Optional[str] = Field(None, max_length=1000, description="Optional custom details")


class SpecialOfferUpdate(BaseModel):
    is_active: Optional[bool] = None
    discount_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    description: Optional[str] = Field(None, max_length=1000)


class SpecialOfferResponse(BaseModel):
    id: uuid.UUID
    market_item_id: uuid.UUID
    offer_type: str
    discount_percentage: Optional[float] = None
    description: Optional[str] = None
    power: float
    is_active: bool
    created_at: datetime

    # We also include product info for merchant dashboard list
    name: str
    category: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[float] = None
    stock_count: int

    model_config = {"from_attributes": True}


class CustomerSpecialOfferResponse(BaseModel):
    id: uuid.UUID
    market_item_id: uuid.UUID
    offer_type: str
    config: Optional[Dict[str, Any]] = None
    discount_percentage: Optional[float] = None
    description: Optional[str] = None
    offer_summary: Optional[str] = None
    power: float = 50.0
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None

    # Product Catalog details
    product_id: uuid.UUID  # global item ID
    product_name: str
    product_description: Optional[str] = None
    price: Optional[float] = None
    discounted_price: Optional[float] = None
    category: Optional[str] = None
    category_name_ar: Optional[str] = None
    category_name_en: Optional[str] = None
    image_url: Optional[str] = None
    stock_count: int
    in_stock: bool

    # Shop location details
    shop_id: uuid.UUID
    shop_name: str
    shop_address: str
    latitude: float
    longitude: float
    shop_is_open: bool

    # Location scoring metrics
    distance_km: float
    sorting_score: float

    model_config = {"from_attributes": True}
