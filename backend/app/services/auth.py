"""
Auth Service — JWT token creation and verification.
Uses PyJWT with HS256 and passlib/bcrypt for password hashing.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import bcrypt

from app.config import settings

# ── Password hashing ───────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))


# ── JWT tokens ──────────────────────────────────────────────────
def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """
    Create a JWT access token.

    Payload contains:
        sub: user UUID (string)
        role: "customer" or "merchant"
        exp: expiration timestamp
        iat: issued-at timestamp
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": now + timedelta(minutes=settings.jwt_expiration_minutes),
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Returns:
        Decoded payload dict with 'sub' (user_id) and 'role'.

    Raises:
        jwt.ExpiredSignatureError: Token has expired
        jwt.InvalidTokenError: Token is malformed or invalid
    """
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
