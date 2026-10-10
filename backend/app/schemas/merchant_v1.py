"""Pydantic schemas for v1 merchant and market endpoints."""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator

from app.jordan_geo import (
    AREA_MAX_LENGTH, LANDMARK_MAX_LENGTH, STREET_MAX_LENGTH,
    clean_text, in_jordan_bbox, normalize_governorate,
)

MSG_OUTSIDE_JORDAN = "يجب أن يكون موقع المتجر داخل الأردن\nThe store location must be inside Jordan"


# ── Market Onboarding Schemas ───────────────────────────────────
class StoreLocationFields(BaseModel):
    """
    The pin and structured address of a store, shared by creating a store and later location
    updates. The text is kept as typed (whitespace trimmed); the governorate is a key from
    app/jordan_geo.py. The one-line `address` is composed by the server, never sent.
    """
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    governorate: str
    area: str = Field(..., max_length=AREA_MAX_LENGTH)
    street: Optional[str] = Field(None, max_length=STREET_MAX_LENGTH)
    landmark: Optional[str] = Field(None, max_length=LANDMARK_MAX_LENGTH)

    @field_validator("governorate", mode="before")
    @classmethod
    def _known_governorate(cls, v):
        key = normalize_governorate(v) if isinstance(v, str) else None
        if key is None:
            raise ValueError("Unknown governorate")
        return key

    @field_validator("area", "street", "landmark", mode="before")
    @classmethod
    def _clean(cls, v, info):
        if v is None:
            cleaned = None
        elif isinstance(v, str):
            cleaned = clean_text(v)
        else:
            raise ValueError("Must be text")
        if cleaned is None and info.field_name == "area":
            raise ValueError("Area is required")
        return cleaned

    @model_validator(mode="after")
    def _inside_jordan(self):
        if not in_jordan_bbox(self.latitude, self.longitude):
            raise ValueError(MSG_OUTSIDE_JORDAN)
        return self


class MarketCreate(StoreLocationFields):
    name: str = Field(..., min_length=2, max_length=255)
    business_nature: Optional[str] = Field(None, description="Type/nature of store business")
    operating_hours: Optional[dict] = Field(None, description="Structured weekday operating intervals")
    employee_directory: Optional[list] = Field(None, description="Directory of staff assigned to the branch")
    phone: Optional[str] = Field(None, description="Store contact phone number")
    is_currently_open: Optional[bool] = Field(True, description="Whether the market is open or closed")


class MarketLocationUpdate(StoreLocationFields):
    """PUT /market/location: the whole location, replaced. What may change is decided by the lock policy."""


class MarketResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    name: str
    name_ar: Optional[str] = None
    address: str
    governorate: Optional[str] = None
    area: Optional[str] = None
    street: Optional[str] = None
    landmark: Optional[str] = None
    latitude: float
    longitude: float
    business_nature: Optional[str] = None
    operating_hours: Optional[dict] = None
    employee_directory: Optional[list] = None
    phone: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    employees: List[str] = []
    profile_edited_at: Optional[datetime] = None
    name_edited_at: Optional[datetime] = None
    is_name_locked: bool = False
    is_currently_open: bool
    is_manual_override: bool
    override_set_at: Optional[datetime] = None
    created_at: datetime
    access_token: Optional[str] = None

    model_config = {"from_attributes": True}



class MarketStatusUpdateRequest(BaseModel):
    is_currently_open: Optional[bool] = None
    is_manual_override: bool


# ── Fuzzy Search Schemas ────────────────────────────────────────
class ItemCheckRequest(BaseModel):
    item_name: str = Field(..., min_length=1)


class CatalogItemMatch(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ItemCheckResponse(BaseModel):
    exists: bool
    matches: List[CatalogItemMatch]


# ── Link Existing Item Schemas ──────────────────────────────────
class ItemLinkRequest(BaseModel):
    item_id: uuid.UUID
    market_id: uuid.UUID
    stock_count: int = Field(0, ge=0)


class ItemLinkResponse(BaseModel):
    success: bool
    message: str
    market_item_id: uuid.UUID
    stock_count: int
    moderation_status: Optional[str] = None  # approved | pending_review | blocked


# ── Dashboard Item Listing Schemas ──────────────────────────────
class MarketItemDashboardResponse(BaseModel):
    id: uuid.UUID  # market_item.id
    item_id: uuid.UUID  # global_item.id
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    stock_count: int
    in_stock: bool
    price: Optional[float] = None
    moderation_status: Optional[str] = None  # approved | pending_review | blocked


# ── Toggle Stock Schema ─────────────────────────────────────────
class StockToggleRequest(BaseModel):
    in_stock: bool


# ── Edit Inventory Schemas ──────────────────────────────────────
class ItemUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    stock_count: Optional[int] = Field(None, ge=0)
    price: Optional[float] = Field(None, ge=0.0)


class BarcodeLookupResponse(BaseModel):
    exists_in_branch: bool
    market_item_id: Optional[uuid.UUID] = None
    global_item_id: uuid.UUID
    name: str
    category: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[float] = None
    stock_count: Optional[int] = None
    barcode: str


class POSCheckoutItem(BaseModel):
    market_item_id: uuid.UUID
    quantity: int = Field(..., ge=1)


class CheckoutRequest(BaseModel):
    items: List[POSCheckoutItem]


