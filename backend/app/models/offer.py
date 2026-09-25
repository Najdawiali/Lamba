import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Offer(Base):
    __tablename__ = "offers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_id = Column(UUID(as_uuid=True), ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True)
    market_item_id = Column(UUID(as_uuid=True), ForeignKey("market_items.id", ondelete="CASCADE"), nullable=False, index=True)
    offer_type = Column(String(20), nullable=False)
    config = Column(JSONB, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    starts_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    market = relationship("Market", backref="offers")
    market_item = relationship("MarketItem", backref="offers")
