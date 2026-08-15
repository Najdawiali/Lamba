"""Pydantic schemas for v1 merchant and market endpoints."""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ── Market Onboarding Schemas ───────────────────────────────────
class MarketCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    address: str = Field(..., min_length=5)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    business_nature: Optional[str] = Field(None, description="Type/nature of store business")
    operating_hours: Optional[dict] = Field(None, description="Structured weekday operating intervals")
    employee_directory: Optional[list] = Field(None, description="Directory of staff assigned to the branch")
    phone: Optional[str] = Field(None, description="Store contact phone number")
    is_currently_open: Optional[bool] = Field(True, description="Whether the market is open or closed")


class MarketResponse(BaseModel):
    id: uuid.UUID
    merchant_id: uuid.UUID
    name: str
    name_ar: Optional[str] = None
    address: str
    address_ar: Optional[str] = None
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
    address_edited_at: Optional[datetime] = None
    is_name_locked: bool = False
    is_address_locked: bool = False
    is_profile_locked: bool = False
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


