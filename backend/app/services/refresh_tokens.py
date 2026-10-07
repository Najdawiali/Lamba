"""
Refresh tokens: the logic of long-lived sessions behind the short access token.

A refresh token is 256 random bits (opaque, not a JWT). Only its SHA-256 is stored. Every use
rotates it: the old token is marked used and a new one replaces it. Tokens that belong to one
sign-in form a family.

Rules (RFC 9700 section 4.14 and OWASP session guidance; see CLAUDE.md for the lifetime choice):
  - idle window: a token expires `refresh_idle_days` after it was issued; each rotation issues a
    new one, so the window slides while the app is used.
  - absolute cap: the family dies `refresh_absolute_days` after the sign-in, whatever the activity.
  - reuse detection: presenting a token that was already rotated means two parties hold it
    (a thief and the owner). The whole family is revoked, so both are signed out.
  - leeway: a mobile app can lose the response to a refresh call (tunnel, dead zone), and its
    retry then looks exactly like reuse. For `refresh_reuse_leeway_seconds` after a rotation, a
    replay of the just-used token is forgiven once more: the unused successor is revoked and a new
    token is issued. The leeway never slides (it counts from the first use). It is logged.

This module has no SQLAlchemy import: it works on any store with the methods of RefreshStore
(SqlRefreshStore in refresh_token_store.py in production, an in-memory one in the tests).
Raw tokens are never logged.
"""

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

SUPERSEDED = "superseded"  # revoked_reason of a token replaced inside the leeway window


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Policy:
    idle: timedelta
    absolute: timedelta
    leeway: timedelta


def policy_from_settings(settings) -> Policy:
    return Policy(
        idle=timedelta(days=settings.refresh_idle_days),
        absolute=timedelta(days=settings.refresh_absolute_days),
        leeway=timedelta(seconds=settings.refresh_reuse_leeway_seconds),
    )


class RefreshStore(Protocol):
    """What the rules need from storage. `get_*_for_update` must lock the row until commit."""

    async def add(self, **fields): ...
    async def get_for_update(self, token_hash: str): ...
    async def get_by_id_for_update(self, row_id: uuid.UUID): ...
    async def revoke_family(self, family_id: uuid.UUID, reason: str, now: datetime) -> None: ...
    async def revoke_user(self, user_id: uuid.UUID, reason: str, now: datetime) -> int: ...
    async def prune_family(self, family_id: uuid.UUID, now: datetime) -> None: ...
    async def prune_user(self, user_id: uuid.UUID, now: datetime) -> None: ...


@dataclass
class RotateResult:
    ok: bool
    user_id: Optional[uuid.UUID] = None
    raw_token: Optional[str] = None
    reason: str = ""  # unknown | revoked | expired | reuse (failures only)
    # State was modified although the call failed (reuse revokes the family). The caller must
    # commit before it raises, because get_db() rolls back on any exception.
    changed: bool = False


async def issue(store: RefreshStore, user_id: uuid.UUID, policy: Policy, now: Optional[datetime] = None) -> str:
    """Start a new family for a fresh sign-in. Returns the raw token."""
    now = now or utcnow()
    raw = new_raw_token()
    await store.add(
        id=uuid.uuid4(), user_id=user_id, family_id=uuid.uuid4(), token_hash=hash_token(raw),
        created_at=now, expires_at=now + min(policy.idle, policy.absolute),
        family_expires_at=now + policy.absolute,
    )
    await store.prune_user(user_id, now)  # dead rows of earlier sign-ins
    return raw


async def _issue_child(store: RefreshStore, parent, policy: Policy, now: datetime) -> str:
    raw = new_raw_token()
    child_id = uuid.uuid4()
    await store.add(
        id=child_id, user_id=parent.user_id, family_id=parent.family_id, token_hash=hash_token(raw),
        created_at=now, expires_at=min(now + policy.idle, parent.family_expires_at),
        family_expires_at=parent.family_expires_at,
    )
    parent.replaced_by_id = child_id
    return raw


async def rotate(store: RefreshStore, raw_token: str, policy: Policy, now: Optional[datetime] = None) -> RotateResult:
    """Exchange a refresh token for its successor, or explain why that isn't possible."""
    now = now or utcnow()
    row = await store.get_for_update(hash_token(raw_token))
    if row is None:
        return RotateResult(ok=False, reason="unknown")

    if row.revoked_at is not None and row.revoked_reason != SUPERSEDED:
        return RotateResult(ok=False, reason="revoked")
    if row.expires_at <= now or row.family_expires_at <= now:
        return RotateResult(ok=False, reason="expired")

    if row.used_at is None and row.revoked_reason != SUPERSEDED:
        row.used_at = now
        raw = await _issue_child(store, row, policy, now)
        await store.prune_family(row.family_id, now)
        return RotateResult(ok=True, user_id=row.user_id, raw_token=raw, changed=True)

    # Already rotated (or replaced inside a leeway window): someone presents an old token.
    head = await store.get_by_id_for_update(row.replaced_by_id) if row.replaced_by_id else None
    lost_response = (
        row.used_at is not None
        and policy.leeway > timedelta(0)  # 0 switches the leeway off
        and now - row.used_at <= policy.leeway
        and head is not None
        and head.used_at is None
        and head.revoked_at is None
        and head.expires_at > now
    )
    if lost_response:
        head.revoked_at = now
        head.revoked_reason = SUPERSEDED
        raw = await _issue_child(store, row, policy, now)  # row.used_at stays: the leeway doesn't slide
        logger.warning(
            "[AUTH] Refresh token replayed %.1fs after rotation: forgiven (leeway), family %s user %s",
            (now - row.used_at).total_seconds(), row.family_id, row.user_id,
        )
        return RotateResult(ok=True, user_id=row.user_id, raw_token=raw, changed=True)

    await store.revoke_family(row.family_id, "reuse", now)
    logger.warning("[AUTH] Refresh token reuse detected: family %s of user %s revoked", row.family_id, row.user_id)
    return RotateResult(ok=False, reason="reuse", changed=True)


async def revoke_by_raw(store: RefreshStore, raw_token: str, now: Optional[datetime] = None) -> bool:
    """Logout: revoke the family of this token. Unknown tokens are ignored. Returns whether one was found."""
    now = now or utcnow()
    row = await store.get_for_update(hash_token(raw_token))
    if row is None:
        return False
    await store.revoke_family(row.family_id, "logout", now)
    return True


async def revoke_all(store: RefreshStore, user_id: uuid.UUID, reason: str, now: Optional[datetime] = None) -> int:
    """Sign a user out everywhere (password reset, account deletion)."""
    return await store.revoke_user(user_id, reason, now or utcnow())
