"""Pydantic schemas for Offers."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VALID_OFFER_TYPES = ["percentage", "fixed_amount", "buy_x_get_y", "quantity_price"]


class OfferCreate(BaseModel):
    market_item_id: UUID
    offer_type: str
    config: Dict[str, Any]
    description: Optional[str] = None
    expires_at: Optional[datetime] = None

    @field_validator("offer_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_OFFER_TYPES:
            raise ValueError(f"offer_type must be one of: {VALID_OFFER_TYPES}")
        return v

    @model_validator(mode="after")
    def validate_config(self) -> "OfferCreate":
        ot = self.offer_type
        v = self.config
        if not isinstance(v, dict):
            raise ValueError("config must be a dictionary")
        if ot == "percentage":
            if "percent" not in v or not isinstance(v["percent"], (int, float)) or not (0 < v["percent"] <= 100):
                raise ValueError("percentage requires config.percent between 1-100")
        elif ot == "fixed_amount":
            if "amount" not in v or not isinstance(v["amount"], (int, float)) or v["amount"] <= 0:
                raise ValueError("fixed_amount requires config.amount > 0")
        elif ot == "buy_x_get_y":
            if (
                "buy" not in v
                or "get" not in v
                or not isinstance(v["buy"], (int, float))
                or not isinstance(v["get"], (int, float))
                or v["buy"] < 1
                or v["get"] < 1
            ):
                raise ValueError("buy_x_get_y requires config.buy >= 1 and config.get >= 1")
        elif ot == "quantity_price":
            if (
                "quantity" not in v
                or "price" not in v
                or not isinstance(v["quantity"], (int, float))
                or not isinstance(v["price"], (int, float))
                or v["quantity"] < 2
                or v["price"] <= 0
            ):
                raise ValueError("quantity_price requires config.quantity >= 2 and config.price > 0")
        return self


class OfferUpdate(BaseModel):
    is_active: Optional[bool] = None
    description: Optional[str] = None
    expires_at: Optional[datetime] = None


class OfferResponse(BaseModel):
    id: UUID
    market_id: UUID
    market_item_id: UUID
    offer_type: str
    config: Dict[str, Any]
    description: Optional[str] = None
    is_active: bool
    starts_at: datetime
    expires_at: Optional[datetime] = None
    created_at: datetime
    item_name: Optional[str] = None
    item_name_ar: Optional[str] = None
    item_price: Optional[float] = None
    item_image_url: Optional[str] = None

    model_config = {"from_attributes": True}
