"""
GlobalItem model representing catalog items with pgvector embeddings for similarity searches.
Supports strict categories and multi-image galleries while preserving backward compatibility.
"""

import uuid
from sqlalchemy import String, ForeignKey, Text, Computed
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from pgvector.sqlalchemy import Vector

from app.database import Base
from app.config import settings


class GlobalItem(Base):
    __tablename__ = "global_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # pgvector columns for high-performance similarity searches
    # Text embeddings use Qwen3-Embedding-0.6B (Matryoshka 1024-d) — multilingual, Arabic-strong.
    # Image embeddings kept at CLIP ViT-B/32 (512-d) for the future VLM/image-search phase.
    text_embedding = mapped_column(Vector(settings.text_embedding_dim), nullable=True)
    image_embedding = mapped_column(Vector(512), nullable=True)

    # Enriched search terms: deterministic concatenation of Arabic name, English name,
    # dialect/Arabizi variants, and category label. Populated by the indexer at write time
    # and by the one-time backfill script. Significantly boosts recall for cross-lingual
    # queries like شاي ↔ "Ghazaleen Tea".
    search_terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generated tsvector over the normalized text bundle. Used by the lexical branch
    # of the hybrid query (replaces the old ILIKE substring scan). GIN-indexed.
    # Computed by Postgres on insert/update, so always consistent with the source columns.
    search_tsv = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('arabic', coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(search_terms,'')) "
            "|| to_tsvector('simple', coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(search_terms,''))",
            persisted=True,
        ),
        nullable=True,
    )
    
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    creator = relationship("User", back_populates="created_items")
    market_items = relationship("MarketItem", back_populates="global_item", cascade="all, delete-orphan")
    category_rel = relationship("Category", back_populates="global_items", lazy="joined")
    images = relationship("ProductImage", back_populates="global_item", lazy="joined", cascade="all, delete-orphan")

    # ── Backward-Compatible Virtual Properties ──────────────────
    @hybrid_property
    def category(self) -> str | None:
        """Virtual property returning the linked category's name for backward compatibility."""
        if "category_rel" in self.__dict__ and self.category_rel is not None:
            return self.category_rel.name
        return None

    @hybrid_property
    def image_url(self) -> str | None:
        """Virtual property returning the primary thumbnail URL for backward compatibility."""
        if "images" in self.__dict__ and self.images:
            for img in self.images:
                if img.is_primary:
                    return img.image_url
            return self.images[0].image_url
        return None
