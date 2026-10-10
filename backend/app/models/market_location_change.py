"""
Audit log of changes to a store's location (pin and structured address).

One row per accepted change made through PUT /api/v1/merchant/market/location: where the pin was,
where it is now, how far it moved, what the address fields were and are, who did it and when.
The creation of a store is not a change and is not logged. The rule for what is allowed lives in
app/services/market_location.py.

Rows go with the store (and with the user) through the database delete rules.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketLocationChange(Base):
    __tablename__ = "market_location_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    old_latitude: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    old_longitude: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    new_latitude: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    new_longitude: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    moved_m: Mapped[float] = mapped_column(Float(precision=53), nullable=False)
    # {"governorate", "area", "street", "landmark"} before and after
    old_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    new_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
