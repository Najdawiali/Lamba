"""create offers table

Revision ID: 006
Revises: 005
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'offers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('market_id', UUID(as_uuid=True), sa.ForeignKey('markets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('market_item_id', UUID(as_uuid=True), sa.ForeignKey('market_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('offer_type', sa.String(20), nullable=False),
        sa.Column('config', JSONB, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('is_active', sa.Boolean, server_default=sa.text('true')),
        sa.Column('starts_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_offers_market_id', 'offers', ['market_id'])
    op.create_index('ix_offers_market_item_id', 'offers', ['market_item_id'])


def downgrade() -> None:
    op.drop_table('offers')
