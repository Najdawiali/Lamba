"""Add bilingual columns, listing_type, and embedding metadata.

Revision ID: 002
Revises: 001
Create Date: 2026-08-03

Adds:
  - global_items: listing_type, attributes, name_ar, name_en,
    description_ar, description_en, embedding_model, embedding_dim,
    embedded_at, embedding_status
  - categories: name_ar, name_en, listing_type
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── global_items ────────────────────────────────────────────
    op.add_column(
        "global_items",
        sa.Column(
            "listing_type",
            sa.String(16),
            nullable=False,
            server_default="product",
        ),
    )
    op.add_column(
        "global_items",
        sa.Column("attributes", JSONB, nullable=True, server_default="{}"),
    )
    op.add_column(
        "global_items",
        sa.Column("name_ar", sa.Text, nullable=True),
    )
    op.add_column(
        "global_items",
        sa.Column("name_en", sa.Text, nullable=True),
    )
    op.add_column(
        "global_items",
        sa.Column("description_ar", sa.Text, nullable=True),
    )
    op.add_column(
        "global_items",
        sa.Column("description_en", sa.Text, nullable=True),
    )
    op.add_column(
        "global_items",
        sa.Column("embedding_model", sa.Text, nullable=True),
    )
    op.add_column(
        "global_items",
        sa.Column("embedding_dim", sa.Integer, nullable=True),
    )
    op.add_column(
        "global_items",
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "global_items",
        sa.Column(
            "embedding_status",
            sa.Text,
            nullable=True,
            server_default="pending",
        ),
    )

    # ── categories ──────────────────────────────────────────────
    op.add_column(
        "categories",
        sa.Column("name_ar", sa.Text, nullable=True),
    )
    op.add_column(
        "categories",
        sa.Column("name_en", sa.Text, nullable=True),
    )
    op.add_column(
        "categories",
        sa.Column("listing_type", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    # ── categories ──────────────────────────────────────────────
    op.drop_column("categories", "listing_type")
    op.drop_column("categories", "name_en")
    op.drop_column("categories", "name_ar")

    # ── global_items ────────────────────────────────────────────
    op.drop_column("global_items", "embedding_status")
    op.drop_column("global_items", "embedded_at")
    op.drop_column("global_items", "embedding_dim")
    op.drop_column("global_items", "embedding_model")
    op.drop_column("global_items", "description_en")
    op.drop_column("global_items", "description_ar")
    op.drop_column("global_items", "name_en")
    op.drop_column("global_items", "name_ar")
    op.drop_column("global_items", "attributes")
    op.drop_column("global_items", "listing_type")
