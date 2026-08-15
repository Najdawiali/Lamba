"""separate name and address edit locks on markets

Revision ID: 008
Revises: 007
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('markets', sa.Column('name_edited_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('markets', sa.Column('address_edited_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('markets', 'address_edited_at')
    op.drop_column('markets', 'name_edited_at')
