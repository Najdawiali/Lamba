"""
SpecialOffer model representing promotional offers like BOGO or discounts on market catalog items.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SpecialOffer(Base):
    __tablename__ = "special_offers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    offer_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # 'BOGO', 'DISCOUNT', 'OTHER'
    )
    discount_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    power: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    market_item = relationship("MarketItem", back_populates="special_offers")
