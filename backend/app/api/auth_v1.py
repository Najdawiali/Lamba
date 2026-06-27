"""
Auth V1 API — Multi-channel registration (Email / Phone), verification, and sign-in.

Endpoints:
  POST /api/v1/auth/signup  — Register with email OR phone, triggers mock verification
  POST /api/v1/auth/verify  — Submit 6-digit verification code
  POST /api/v1/auth/signin  — Authenticate and receive JWT
"""

import logging
import random
import string

from fastapi import APIRouter, Depends, HTTPException, status
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth V1"])


def _generate_code(length: int = 6) -> str:
    """Generate a random numeric verification code."""
    return "".join(random.choices(string.digits, k=length))


def _mock_send_sms(phone: str, code: str) -> None:
    """Mock SMS gateway — prints to server console."""
    logger.info("=" * 60)
    logger.info("📱  MOCK SMS VERIFICATION")
    logger.info(f"   To:   {phone}")
    logger.info(f"   Code: {code}")
    logger.info("=" * 60)


def _mock_send_email(email: str, code: str) -> None:
    """Mock Email gateway — prints to server console."""
    logger.info("=" * 60)
    logger.info("📧  MOCK EMAIL VERIFICATION")
    logger.info(f"   To:   {email}")
    logger.info(f"   Code: {code}")
    logger.info("=" * 60)


# ── POST /signup ────────────────────────────────────────────────
@router.post("/signup", response_model=SignUpResponse, status_code=201)
async def signup(data: SignUpRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new customer or merchant.

    Accepts email OR phone_number. Generates a 6-digit verification code
    and dispatches it via the appropriate mock channel (SMS or Email).
    The account is stored as unverified until /verify is called.
    """
    # Check for duplicate email or phone
    conditions = []
    if data.email:
        conditions.append(User.email == data.email)
    if data.phone_number:
        conditions.append(User.phone_number == data.phone_number)

    existing = await db.execute(select(User).where(or_(*conditions)))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email or phone number already exists",
        )

    # Generate verification code
    code = _generate_code()

    # Create unverified user
    user = User(
        email=data.email,
        phone_number=data.phone_number,
        password_hash=hash_password(data.password),
        user_type=data.user_type.value,
        verified=False,
        verification_code=code,
    )
    db.add(user)
    await db.flush()

    # Dispatch mock verification
    if data.phone_number:
        _mock_send_sms(data.phone_number, code)
        channel = "sms"
    else:
        _mock_send_email(data.email, code)
        channel = "email"

    return SignUpResponse(
        user_id=user.id,
        message=f"Verification code sent via {channel}. Please verify to complete registration.",
        channel=channel,
    )


# ── POST /verify ───────────────────────────────────────────────
@router.post("/verify", response_model=VerifyResponse)
async def verify(data: VerifyRequest, db: AsyncSession = Depends(get_db)):
    """
    Verify a user's registration with their 6-digit code.

    On success, sets verified=True and clears the stored code.
    On failure, returns a 400 error to allow retry (Activity Diagram loop).
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

    if user.verification_code != data.verification_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code. Please try again.",
        )

    # Mark as verified
    user.verified = True
    user.verification_code = None
    await db.flush()

    return VerifyResponse(verified=True, message="Account verified successfully!")


# ── POST /signin ───────────────────────────────────────────────
@router.post("/signin", response_model=SignInResponse)
async def signin(data: SignInRequest, db: AsyncSession = Depends(get_db)):
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
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": "Unverified Account. Please complete verification first.",
                "user_id": str(user.id),
                "channel": "sms" if user.phone_number else "email",
                "contact": user.phone_number or user.email,
                "user_type": user.user_type,
            }
        )

    # Generate JWT with user context
    token = create_access_token(user.id, user.user_type)

    return SignInResponse(
        access_token=token,
        user=SignInUserInfo.model_validate(user),
    )
