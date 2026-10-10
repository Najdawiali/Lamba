"""structured store address and the location change log

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-10

markets gets the structured address: governorate (a key from app/jordan_geo.py), area, street and
landmark, all nullable (a store from before this migration has only `address`, which stays NOT NULL
and is now composed by the server from the parts).
market_location_changes is the audit log of pin / address changes made after a store exists
(old and new pin, distance moved, old and new fields, user, time). It goes with its store and its
user through ON DELETE CASCADE.
Additive: the old API image keeps working against the new schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('markets', sa.Column('governorate', sa.String(length=20), nullable=True))
    op.add_column('markets', sa.Column('area', sa.String(length=120), nullable=True))
    op.add_column('markets', sa.Column('street', sa.String(length=160), nullable=True))
    op.add_column('markets', sa.Column('landmark', sa.String(length=200), nullable=True))
    op.create_table('market_location_changes',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('market_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('old_latitude', sa.Float(precision=53), nullable=False),
    sa.Column('old_longitude', sa.Float(precision=53), nullable=False),
    sa.Column('new_latitude', sa.Float(precision=53), nullable=False),
    sa.Column('new_longitude', sa.Float(precision=53), nullable=False),
    sa.Column('moved_m', sa.Float(precision=53), nullable=False),
    sa.Column('old_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('new_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['market_id'], ['markets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_market_location_changes_market_id'), 'market_location_changes', ['market_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_market_location_changes_market_id'), table_name='market_location_changes')
    op.drop_table('market_location_changes')
    op.drop_column('markets', 'landmark')
    op.drop_column('markets', 'street')
    op.drop_column('markets', 'area')
    op.drop_column('markets', 'governorate')
