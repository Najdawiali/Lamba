"""add profile_edited_at, contact info, and employees to markets

Revision ID: 007
Revises: 006
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('markets', sa.Column('profile_edited_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('markets', sa.Column('contact_phone', sa.String(20), nullable=True))
    op.add_column('markets', sa.Column('contact_email', sa.String(255), nullable=True))
    op.add_column('markets', sa.Column('employees', JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False))


def downgrade() -> None:
    op.drop_column('markets', 'employees')
    op.drop_column('markets', 'contact_email')
    op.drop_column('markets', 'contact_phone')
    op.drop_column('markets', 'profile_edited_at')
