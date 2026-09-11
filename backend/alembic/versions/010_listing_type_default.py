"""Add server default for listing_type.

Revision ID: 010
Revises: 009
"""
from typing import Sequence, Union
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "global_items",
        "listing_type",
        server_default="product",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "global_items",
        "listing_type",
        server_default=None,
    )
