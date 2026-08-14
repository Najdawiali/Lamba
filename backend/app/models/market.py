"""
Market model representing a physical retail branch location with PostGIS coordinates.
Supports physical store features (operating hours, employees, business nature, multi-branch).
"""

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_nature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    address_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # PostGIS geometry POINT (longitude, latitude) with standard SRID 4326
    location = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False,
    )
    operating_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    employee_directory: Mapped[list | None] = mapped_column(JSON, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_currently_open: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    is_manual_override: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    override_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    merchant = relationship("User", back_populates="markets")
    items = relationship("MarketItem", back_populates="market", cascade="all, delete-orphan")
    ratings = relationship("Rating", back_populates="market", cascade="all, delete-orphan")
    pos_receipts = relationship("POSReceipt", back_populates="market", cascade="all, delete-orphan")
