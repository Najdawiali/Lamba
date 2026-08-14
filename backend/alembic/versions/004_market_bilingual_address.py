"""Add bilingual name and address columns to markets table.

Revision ID: 004
Revises: 003
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS name_ar TEXT;")
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS name_en TEXT;")
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS address_ar TEXT;")
    op.execute("ALTER TABLE markets ADD COLUMN IF NOT EXISTS address_en TEXT;")

def downgrade() -> None:
    op.drop_column("markets", "address_en")
    op.drop_column("markets", "address_ar")
    op.drop_column("markets", "name_en")
    op.drop_column("markets", "name_ar")
