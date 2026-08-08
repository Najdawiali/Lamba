"""Baseline: extensions and schema fixes from lifespan.

Revision ID: 001
Revises:
Create Date: 2026-08-03

This migration captures the manual DDL that was previously executed in the
FastAPI lifespan handler. For existing databases, run `alembic stamp head`
to mark them as current. For new databases, `alembic upgrade head` applies
everything.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Columns added after initial create_all (idempotent)
    op.execute(
        "ALTER TABLE markets ADD COLUMN IF NOT EXISTS "
        "is_currently_open BOOLEAN DEFAULT TRUE;"
    )
    op.execute(
        "ALTER TABLE markets ADD COLUMN IF NOT EXISTS "
        "is_manual_override BOOLEAN DEFAULT FALSE;"
    )
    op.execute(
        "ALTER TABLE markets ADD COLUMN IF NOT EXISTS "
        "override_set_at TIMESTAMP WITH TIME ZONE;"
    )
    op.execute(
        "ALTER TABLE markets ADD COLUMN IF NOT EXISTS "
        "phone VARCHAR(40);"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "full_name VARCHAR(255);"
    )
    op.execute(
        "ALTER TABLE global_items ADD COLUMN IF NOT EXISTS "
        "barcode VARCHAR(100) UNIQUE;"
    )

    # Unique constraint on ratings
    op.execute("ALTER TABLE ratings DROP CONSTRAINT IF EXISTS uq_customer_market;")
    op.execute(
        "ALTER TABLE ratings ADD CONSTRAINT uq_customer_market "
        "UNIQUE (customer_id, market_id);"
    )


def downgrade() -> None:
    # Downgrade intentionally left as no-op for baseline.
    # Dropping extensions or columns from the original schema
    # would be destructive and is not recommended.
    pass
