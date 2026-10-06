"""
Auth V1 API — Multi-channel registration (Email / Phone), verification, and sign-in.

Endpoints:
  POST /api/v1/auth/signup  — Register with email OR phone, dispatches verification code
  POST /api/v1/auth/verify  — Submit 6-digit verification code
  POST /api/v1/auth/signin  — Authenticate and receive JWT
"""

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from app.rate_limit import limiter
from pydantic import BaseModel, Field
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
from app.services import signin_throttle
from app.services.password_policy import password_problem
from app.config import settings
from app.services.email_service import send_verification_email
from app.services.whatsapp_service import normalize_jo_mobile, send_verification_code as send_whatsapp_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth V1"])


class ResendCodeRequest(BaseModel):
    user_id: uuid.UUID


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3)


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)


PHONE_SIGNUP_UNAVAILABLE = (
    "التسجيل برقم الهاتف غير متاح حالياً، الرجاء التسجيل بالبريد الإلكتروني.\n"
    "Sign-up with a phone number isn't available yet. Please sign up with your email."
)


PHONE_INVALID = (
    "رقم الهاتف غير صحيح. أدخل رقم هاتف أردني، مثل 0791234567.\n"
    "Invalid phone number. Enter a Jordanian mobile number, like 0791234567."
)
CODE_SEND_FAILED = (
    "تعذّر إرسال رمز التحقق عبر واتساب. تأكّد أن الرقم مسجّل على واتساب، أو سجّل بالبريد الإلكتروني.\n"
    "We couldn't send the code on WhatsApp. Make sure this number uses WhatsApp, or sign up with your email."
)
RESEND_TOO_SOON = (
    "الرجاء الانتظار دقيقة قبل طلب رمز جديد.\n"
    "Please wait a minute before requesting a new code."
)
RESEND_COOLDOWN_SECONDS = 60  # each WhatsApp code costs money and counts toward Meta's daily limit
_LOCK_MINUTES = signin_throttle.WINDOW_SECONDS // 60
SIGNIN_LOCKED = (
    f"محاولات تسجيل دخول فاشلة كثيرة لهذا الحساب. انتظر حتى {_LOCK_MINUTES} دقيقة ثم حاول مرة أخرى، أو أعد تعيين كلمة المرور.\n"
    f"Too many failed sign-in attempts for this account. Wait up to {_LOCK_MINUTES} minutes and try again, or reset your password."
)


def _within_cooldown(user: User) -> bool:
    sent = user.verification_code_created_at
    return bool(sent and (datetime.now(timezone.utc) - sent).total_seconds() < RESEND_COOLDOWN_SECONDS)


def _identifier_filter(identifier: str):
    """Match an account by email, or by phone in any typed form (0791..., +962 79..., ...)."""
    identifier = identifier.strip()
    phone = normalize_jo_mobile(identifier) if "@" not in identifier else None
    return or_(User.email == identifier, User.phone_number == (phone or identifier))


async def _deliver_code(user: User, code: str) -> str:
    """Send a verification code on the account's channel. Returns the channel name.
    Raises 503 when WhatsApp delivery fails, so the caller's transaction is rolled back."""
    if user.email:
        await send_verification_email(user.email, code)
        return "email"
    if not await send_whatsapp_code(user.phone_number, code):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=CODE_SEND_FAILED)
    return "whatsapp"


def _reject_weak_password(password: str, **personal) -> None:
    problem = password_problem(password, **personal)
    if problem:
        # Log which rule refused it (never the password), so refusals can be diagnosed
        logger.info("New password rejected by policy rule: %s", problem[0])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=problem[1])


def _generate_code(length: int = 6) -> str:
    """Generate a random numeric verification code."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


# ── POST /signup ────────────────────────────────────────────────
@router.post("/signup", response_model=SignUpResponse, status_code=201)
@limiter.limit("10/minute")
async def signup(request: Request, data: SignUpRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new customer or merchant.

    Accepts email OR phone_number. Generates a 6-digit verification code
    and dispatches it via the appropriate channel (email, or WhatsApp for phone numbers).
    The account is stored as unverified until /verify is called.
    """
    phone = None
    if data.phone_number and not data.email:
        if not settings.phone_signup_enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PHONE_SIGNUP_UNAVAILABLE)
        phone = normalize_jo_mobile(data.phone_number)
        if not phone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PHONE_INVALID)
    _reject_weak_password(data.password, email=data.email, name=data.full_name, phone=phone)

    # Check for existing account
    result = await db.execute(select(User).where(
        User.email == data.email if data.email else User.phone_number == phone
    ))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.verified:
            # Real verified account — cannot re-register
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account already exists. Please sign in.",
            )
        # Unverified account — regenerate the code and resend (with a cooldown)
        if _within_cooldown(existing_user):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=RESEND_TOO_SOON)
        code = _generate_code()
        existing_user.password_hash = hash_password(data.password)
        existing_user.verification_code = code
        existing_user.verification_code_created_at = datetime.now(timezone.utc)
        existing_user.verification_attempts = 0
        if data.full_name:
            existing_user.full_name = data.full_name
        await db.flush()
        channel = await _deliver_code(existing_user, code)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "user_id": str(existing_user.id),
                "message": f"Verification code resent via {channel}.",
                "channel": channel,
            },
        )

    # Create the unverified user, then deliver the code. If WhatsApp delivery fails,
    # _deliver_code raises and get_db rolls back, so no half-created account remains.
    code = _generate_code()
    user = User(
        email=data.email,
        phone_number=phone,
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
    channel = await _deliver_code(user, code)

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

    # Verify code (constant-time comparison)
    if not secrets.compare_digest(user.verification_code, data.verification_code):
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
    if _within_cooldown(user):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=RESEND_TOO_SOON)

    code = _generate_code()
    user.verification_code = code
    user.verification_code_created_at = datetime.now(timezone.utc)
    user.verification_attempts = 0
    await db.flush()
    channel = await _deliver_code(user, code)

    return {"message": "Verification code resent", "channel": channel}


# ── POST /forgot-password ──────────────────────────────────────
@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Send a password reset code by email, or on WhatsApp for phone accounts.
    The `email` field accepts an email address or a phone number.
    Always returns the same response, so it can't be used to discover accounts.
    """
    result = await db.execute(select(User).where(_identifier_filter(data.email)))
    user = result.scalar_one_or_none()

    if user and user.verified and not _within_cooldown(user):
        code = _generate_code()
        user.verification_code = code
        user.verification_code_created_at = datetime.now(timezone.utc)
        user.verification_attempts = 0
        await db.flush()
        try:
            await _deliver_code(user, code)
            logger.info("[AUTH] Password reset code sent to user %s", user.id)
        except HTTPException:
            logger.warning("[AUTH] Password reset code could not be delivered to user %s", user.id)
    else:
        logger.info("[AUTH] Password reset requested for an unknown, unverified or cooling-down account")

    return {"message": "If an account exists, a reset code has been sent."}


# ── POST /reset-password ───────────────────────────────────────
@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Reset password using the code sent to email.
    """
    # Checked before the code, so a weak choice doesn't use up one of the 5 attempts
    _reject_weak_password(data.new_password, email=data.email if "@" in data.email else None,
                          phone=normalize_jo_mobile(data.email))
    result = await db.execute(select(User).where(_identifier_filter(data.email)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")

    if not user.verification_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reset code pending. Please request a new one.",
        )

    # State changes before an HTTPException must be COMMITTED: get_db() rolls back
    # on any exception, so a flush() here would be undone and the attempt limit
    # would never take effect (unlimited guessing of the 6-digit reset code).

    # Check attempts
    if user.verification_attempts >= MAX_VERIFICATION_ATTEMPTS:
        user.verification_code = None
        user.verification_code_created_at = None
        user.verification_attempts = 0
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please request a new reset code.",
        )

    # Check expiry (10 minutes)
    if user.verification_code_created_at:
        elapsed = datetime.now(timezone.utc) - user.verification_code_created_at
        if elapsed.total_seconds() > VERIFICATION_CODE_TTL_MINUTES * 60:
            user.verification_code = None
            user.verification_code_created_at = None
            user.verification_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Reset code has expired. Please request a new one.",
            )

    # Verify code (constant-time comparison)
    if not secrets.compare_digest(user.verification_code, data.code):
        user.verification_attempts += 1
        await db.commit()
        remaining = MAX_VERIFICATION_ATTEMPTS - user.verification_attempts
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid code. {remaining} attempts remaining.",
        )

    # Success — update password
    user.password_hash = hash_password(data.new_password)
    user.verification_code = None
    user.verification_code_created_at = None
    user.verification_attempts = 0
    await db.flush()

    # A reset proves control of the account: let the owner sign in right away, even if the
    # failed-attempts block was active.
    await signin_throttle.reset_failures(signin_throttle.canonical_identifier(data.email, normalize_jo_mobile))

    return {"message": "Password reset successfully. Please sign in with your new password."}


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
      - 429: too many failed attempts for this account (see signin_throttle)
    """
    # Per-account limit on failed attempts. Checked first, before the lookup and the slow
    # password hash; it applies to unknown accounts too, so it never reveals whether one exists.
    account = signin_throttle.canonical_identifier(data.email_or_phone, normalize_jo_mobile)
    wait = await signin_throttle.seconds_locked(account)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=SIGNIN_LOCKED,
            headers={"Retry-After": str(wait)},
        )

    # Resolve user by email or phone
    result = await db.execute(
        select(User).where(_identifier_filter(data.email_or_phone))
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(data.password, user.password_hash):
        await signin_throttle.record_failure(account)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Credentials",
        )

    await signin_throttle.reset_failures(account)  # a correct password clears the account's failures

    if not user.verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Unverified Account. Please complete verification first.",
                "user_id": str(user.id),
                "channel": "email" if user.email else "whatsapp",
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
