"""Pydantic schemas for v1 authentication endpoints."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


class UserType(str, Enum):
    customer = "customer"
    merchant = "merchant"


class SignUpRequest(BaseModel):
    """Registration request — requires email OR phone_number (not both empty)."""
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, min_length=8, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = Field(None, max_length=255)
    user_type: UserType = UserType.customer

    @model_validator(mode="after")
    def require_email_or_phone(self):
        if not self.email and not self.phone_number:
            raise ValueError("Either email or phone_number must be provided")
        return self


class SignUpResponse(BaseModel):
    user_id: uuid.UUID
    message: str
    channel: str  # "email" or "sms"


class VerifyRequest(BaseModel):
    user_id: uuid.UUID
    verification_code: str = Field(..., min_length=6, max_length=6)


class VerifyResponse(BaseModel):
    verified: bool
    message: str


class UnverifiedAccountResponse(BaseModel):
    detail: str
    user_id: uuid.UUID
    channel: str
    contact: str
    user_type: str


class SignInRequest(BaseModel):
    email_or_phone: str = Field(..., min_length=3)
    password: str
    # Apps that renew their session through /auth/refresh send true and get a short-lived
    # access token plus a refresh token. Older builds omit it and keep the 24-hour token.
    client_supports_refresh: bool = False


class SignInResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "SignInUserInfo"
    refresh_token: Optional[str] = None  # only when the client asked for it
    expires_in: Optional[int] = None  # seconds the access token lives (only with refresh_token)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20, max_length=200)


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    expires_in: int
    user: "SignInUserInfo"


class SignInUserInfo(BaseModel):
    id: uuid.UUID
    email: Optional[str] = None
    phone_number: Optional[str] = None
    full_name: Optional[str] = None
    user_type: str
    verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
