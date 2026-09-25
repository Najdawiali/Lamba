"""
MarketItem model connecting a physical market to a global catalog item with stock and status details.
"""

import uuid

from sqlalchemy import Integer, Boolean, ForeignKey, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MarketItem(Base):
    __tablename__ = "market_items"
    __table_args__ = (
        UniqueConstraint("market_id", "item_id", name="uq_market_items_market_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("global_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stock_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    market = relationship("Market", back_populates="items")
    global_item = relationship("GlobalItem", back_populates="market_items")
    special_offers = relationship("SpecialOffer", back_populates="market_item", cascade="all, delete-orphan")
