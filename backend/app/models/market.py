"""
Market model representing a physical retail branch location with PostGIS coordinates.
Supports physical store features (operating hours, employees, business nature, multi-branch).
"""

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import String, DateTime, ForeignKey, Text, JSON, Column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import text

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
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_nature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # One-line fallback text, composed by the server from the structured fields below.
    address: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured address (migration 0005). Nullable: rows from before it have only `address`.
    # `governorate` is a key from app/jordan_geo.py; area/street/landmark are stored as typed.
    governorate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    street: Mapped[str | None] = mapped_column(String(160), nullable=True)
    landmark: Mapped[str | None] = mapped_column(String(200), nullable=True)

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

    profile_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    name_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    address_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employees: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=False, default=list)

    # Relationships
    merchant = relationship("User", back_populates="markets")
    items = relationship("MarketItem", back_populates="market", cascade="all, delete-orphan")
    ratings = relationship("Rating", back_populates="market", cascade="all, delete-orphan")
    pos_receipts = relationship("POSReceipt", back_populates="market", cascade="all, delete-orphan")
