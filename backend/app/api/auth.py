"""
Auth API — Shared JWT-related dependencies (get_current_user, require_merchant).

Note: Account registration, verification, and sign-in are handled by the V1
auth router (`app.api.auth_v1`). This module only retains the FastAPI
dependencies that other V1 routers consume.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token

security = HTTPBearer()


# ── Dependencies ────────────────────────────────────────────────
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that extracts and validates the JWT token
    from the Authorization header, then loads the user from the database.
    """
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def require_merchant(user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user is a merchant."""
    role = getattr(user, "user_type", None) or getattr(user, "role", None)
    if role != "merchant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant access required",
        )
    return user


def require_customer(user: User = Depends(get_current_user)) -> User:
    """Dependency that ensures the current user is a customer."""
    role = getattr(user, "user_type", None) or getattr(user, "role", None)
    if role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access required",
        )
    return user