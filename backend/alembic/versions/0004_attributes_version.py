"""global_items.attributes_version

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09

Which version of the attribute extraction prompt filled global_items.attributes
(see app/services/attribute_extraction.py). NULL means "never processed". The catalog
enrichment job sets it even when nothing could be extracted, so a finished product is not
billed again on a rerun, and a newer prompt can select attributes_version < N.
Additive and nullable: the old API image keeps working against the new schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('global_items', sa.Column('attributes_version', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('global_items', 'attributes_version')
