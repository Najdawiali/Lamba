"""
Auth V1 API — Multi-channel registration (Email / Phone), verification, and sign-in.

Endpoints:
  POST /api/v1/auth/signup  — Register with email OR phone, dispatches verification code
  POST /api/v1/auth/verify  — Submit 6-digit verification code
  POST /api/v1/auth/signin  — Authenticate and receive JWT
"""

import logging
import random
import string
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from app.rate_limit import limiter
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.auth_v1 import (
    SignUpRequest, SignUpResponse,
    VerifyRequest, VerifyResponse,
    SignInRequest, SignInResponse, SignInUserInfo,
)
from app.services.auth import hash_password, verify_password, create_access_token
from app.services.email_service import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth V1"])


class ResendCodeRequest(BaseModel):
    user_id: uuid.UUID


def _generate_code(length: int = 6) -> str:
    """Generate a random numeric verification code."""
    return "".join(random.choices(string.digits, k=length))


# ── POST /signup ────────────────────────────────────────────────
@router.post("/signup", response_model=SignUpResponse, status_code=201)
@limiter.limit("10/minute")
async def signup(request: Request, data: SignUpRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new customer or merchant.

    Accepts email OR phone_number. Generates a 6-digit verification code
    and dispatches it via the appropriate channel (Email or SMS).
    The account is stored as unverified until /verify is called.
    """
    # Check for existing account
    result = await db.execute(select(User).where(
        User.email == data.email if data.email else User.phone_number == data.phone_number
    ))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.verified:
            # Real verified account — cannot re-register
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account already exists. Please sign in.",
            )
        else:
            # Unverified account — regenerate OTP and resend
            code = f"{random.randint(0, 999999):06d}"
            existing_user.password_hash = hash_password(data.password)
            existing_user.verification_code = code
            existing_user.verification_code_created_at = datetime.now(timezone.utc)
            existing_user.verification_attempts = 0
            if data.full_name:
                existing_user.full_name = data.full_name
            await db.flush()

            # Send new verification code
            if data.email:
                await send_verification_email(data.email, code)
            elif data.phone_number:
                logger.info(f"📱  MOCK SMS: Code {code} → {data.phone_number}")

            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "user_id": str(existing_user.id),
                    "message": "Verification code resent. Please check your email.",
                    "channel": "email" if data.email else "sms",
                },
            )

    # Generate verification code
    code = _generate_code()

    # Create unverified user
    user = User(
        email=data.email,
        phone_number=data.phone_number,
        password_hash=hash_password(data.password),
        user_type=data.user_type.value,
        full_name=data.full_name,
        verified=False,
        verification_code=code,
        verification_code_created_at=datetime.now(timezone.utc),
        verification_attempts=0,
    )
    db.add(user)
    await db.flush()

    # Send verification code via configured provider (resend or mock)
    channel = "email" if data.email else "sms"
    if data.email:
        await send_verification_email(data.email, code)
    elif data.phone_number:
        # SMS delivery not yet implemented — log to console
        logger.info(f"📱  MOCK SMS: Code {code} → {data.phone_number}")

    return SignUpResponse(
        user_id=user.id,
        message=f"Verification code sent via {channel}. Please verify to complete registration.",
        channel=channel,
    )


# ── Constants ──────────────────────────────────────────────────
VERIFICATION_CODE_TTL_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 5


# ── POST /verify ───────────────────────────────────────────────
@router.post("/verify", response_model=VerifyResponse)
@limiter.limit("10/minute")
async def verify(request: Request, data: VerifyRequest, db: AsyncSession = Depends(get_db)):
    """
    Verify a user's registration with their 6-digit code.

    Security:
      - Code expires after 10 minutes
      - Max 5 attempts before code is invalidated (must request new one)
    """
    result = await db.execute(select(User).where(User.id == data.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.verified:
        return VerifyResponse(verified=True, message="Account is already verified")

    if not user.verification_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code pending. Please request a new one.",
        )

    # Check attempt limit
    if user.verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
        # Invalidate the code — user must request a new one
        user.verification_code = None
        user.verification_code_created_at = None
        user.verification_attempts = 0
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Verification code invalidated. Please sign up again or request a new code.",
        )

    # Check expiry
    if user.verification_code_created_at:
        elapsed = datetime.now(timezone.utc) - user.verification_code_created_at
        if elapsed.total_seconds() > VERIFICATION_CODE_TTL_MINUTES * 60:
            user.verification_code = None
            user.verification_code_created_at = None
            user.verification_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Verification code has expired. Please request a new one.",
            )

    # Verify code
    if user.verification_code != data.verification_code:
        user.verification_attempts += 1
        if user.verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
            user.verification_code = None
            user.verification_code_created_at = None
            user.verification_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Verification code invalidated. Please sign up again or request a new code.",
            )
        await db.commit()
        remaining = MAX_VERIFICATION_ATTEMPTS - user.verification_attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification code. {remaining} attempts remaining.",
        )

    # Success — mark verified and clean up
    user.verified = True
    user.verification_code = None
    user.verification_code_created_at = None
    user.verification_attempts = 0
    await db.commit()

    return VerifyResponse(verified=True, message="Account verified successfully!")


# ── POST /resend-code ──────────────────────────────────────────
@router.post("/resend-code")
@limiter.limit("3/minute")
async def resend_code(request: Request, data: ResendCodeRequest, db: AsyncSession = Depends(get_db)):
    """
    Resend verification code for an unverified account.
    Rate limited to 3 per minute to prevent abuse.
    """
    result = await db.execute(select(User).where(User.id == data.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is already verified")

    code = f"{random.randint(0, 999999):06d}"
    user.verification_code = code
    user.verification_code_created_at = datetime.now(timezone.utc)
    user.verification_attempts = 0
    await db.flush()

    if user.email:
        await send_verification_email(user.email, code)
    elif user.phone_number:
        logger.info(f"📱  MOCK SMS: Code {code} → {user.phone_number}")

    return {
        "message": "Verification code resent",
        "channel": "email" if user.email else "sms",
    }


# ── POST /signin ───────────────────────────────────────────────
@router.post("/signin", response_model=SignInResponse)
@limiter.limit("10/minute")
async def signin(request: Request, data: SignInRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate a user by email or phone number.

    Returns JWT access token on success.
    Returns descriptive error payloads:
      - 401: "Invalid Credentials"
      - 403: "Unverified Account"
    """
    # Resolve user by email or phone
    result = await db.execute(
        select(User).where(
            or_(
                User.email == data.email_or_phone,
                User.phone_number == data.email_or_phone,
            )
        )
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Credentials",
        )

    if not user.verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Unverified Account. Please complete verification first.",
                "user_id": str(user.id),
                "channel": "sms" if user.phone_number else "email",
                "contact": user.phone_number or user.email,
                "user_type": user.user_type,
            },
        )

    # Generate JWT with user context
    token = create_access_token(user.id, user.user_type)

    return SignInResponse(
        access_token=token,
        user=SignInUserInfo.model_validate(user),
    )
