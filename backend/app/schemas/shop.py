"""Pydantic schemas for shop management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ShopCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    phone: str | None = None
    image_url: str | None = None


class ShopUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    phone: str | None = None
    image_url: str | None = None
    is_active: bool | None = None


class ShopResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    address: str
    latitude: float
    longitude: float
    phone: str | None
    image_url: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
