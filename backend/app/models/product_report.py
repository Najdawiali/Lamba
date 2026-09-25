"""
ProductReport model representing user reports on catalog items.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProductReport(Base):
    __tablename__ = "product_reports"
    # One user can report a product only once
    __table_args__ = (
        UniqueConstraint("reporter_id", "global_item_id", name="uq_report_reporter_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    global_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("global_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The store where the customer saw it
    market_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("markets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Allowed values: restricted_item, wrong_info, offensive, spam, other
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Allowed values: open, actioned, dismissed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    reporter = relationship("User")
    global_item = relationship("GlobalItem")
    market = relationship("Market")
