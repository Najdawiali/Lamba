"""add conversations and messages tables

Revision ID: 005
Revises: 003
Create Date: 2026-08-14 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, Sequence[str], None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add push_token column to users table if not exists
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='users' AND column_name='push_token'
            ) THEN
                ALTER TABLE users ADD COLUMN push_token VARCHAR(255);
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id UUID PRIMARY KEY,
            customer_id UUID NOT NULL REFERENCES users(id),
            market_id UUID NOT NULL REFERENCES markets(id),
            product_id UUID REFERENCES global_items(id),
            last_message_text TEXT,
            last_message_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL REFERENCES conversations(id),
            sender_id UUID NOT NULL REFERENCES users(id),
            text TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_customer ON conversations (customer_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_conversations_market ON conversations (market_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_conversation ON messages (conversation_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages;")
    op.execute("DROP TABLE IF EXISTS conversations;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS push_token;")
