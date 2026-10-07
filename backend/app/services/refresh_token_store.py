"""SQLAlchemy storage for refresh tokens (the rules are in refresh_tokens.py)."""

import uuid
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class SqlRefreshStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, **fields) -> RefreshToken:
        row = RefreshToken(**fields)
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_for_update(self, token_hash: str) -> RefreshToken | None:
        # FOR UPDATE: two requests with the same token are serialised, so only one can rotate it.
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, row_id: uuid.UUID) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.id == row_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID, reason: str, now: datetime) -> None:
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
        )

    async def revoke_user(self, user_id: uuid.UUID, reason: str, now: datetime) -> int:
        result = await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
        )
        return result.rowcount or 0

    async def prune_family(self, family_id: uuid.UUID, now: datetime) -> None:
        await self.db.execute(
            delete(RefreshToken).where(
                RefreshToken.family_id == family_id,
                or_(RefreshToken.expires_at <= now, RefreshToken.family_expires_at <= now),
            )
        )

    async def prune_user(self, user_id: uuid.UUID, now: datetime) -> None:
        await self.db.execute(
            delete(RefreshToken).where(
                RefreshToken.user_id == user_id,
                or_(RefreshToken.expires_at <= now, RefreshToken.family_expires_at <= now),
            )
        )
