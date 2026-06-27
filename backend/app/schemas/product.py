"""Pydantic schemas for product management."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    shop_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    price: Decimal | None = Field(None, ge=0, decimal_places=2)
    category: str | None = None
    image_url: str | None = None
    in_stock: bool = True


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = Field(None, ge=0, decimal_places=2)
    category: str | None = None
    image_url: str | None = None
    in_stock: bool | None = None


class StockToggle(BaseModel):
    in_stock: bool


class ProductResponse(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    name: str
    description: str | None
    price: Decimal | None
    category: str | None
    image_url: str | None
    in_stock: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
