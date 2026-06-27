import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import String, ForeignKey, Float, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class POSReceipt(Base):
    __tablename__ = "pos_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone(timedelta(hours=3))),
        nullable=False,
        index=True
    )

    # Relationships
    market = relationship("Market", back_populates="pos_receipts")
    items = relationship(
        "POSReceiptItem",
        back_populates="receipt",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class POSReceiptItem(Base):
    __tablename__ = "pos_receipt_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pos_receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Relationships
    receipt = relationship("POSReceipt", back_populates="items")
