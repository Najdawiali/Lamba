"""Resize vector columns to 1024-d with dynamic DB inspection.

Revision ID: 003
Revises: 002
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # ── global_items.text_embedding check and alter ─────────────────
    op.execute(
        """
        DO $$
        DECLARE
            curr_dim integer;
        BEGIN
            -- Check vector dimension if column exists and has values
            SELECT vector_dims(text_embedding) INTO curr_dim 
            FROM global_items 
            WHERE text_embedding IS NOT NULL 
            LIMIT 1;

            -- If column is not 1024d (or is NULL / wrong dim)
            IF curr_dim IS NULL OR curr_dim != 1024 THEN
                -- Drop dependent HNSW/IVFFlat indexes first
                EXECUTE 'DROP INDEX IF EXISTS ix_global_items_text_embedding_hnsw;';
                EXECUTE 'DROP INDEX IF EXISTS ix_global_items_text_embedding_ivfflat;';
                EXECUTE 'DROP INDEX IF EXISTS ix_global_items_text_embedding;';

                -- Reset stale vectors
                EXECUTE 'UPDATE global_items SET text_embedding = NULL;';

                -- Alter column type to VECTOR(1024)
                EXECUTE 'ALTER TABLE global_items ALTER COLUMN text_embedding TYPE VECTOR(1024);';
            END IF;

            -- Recreate HNSW cosine index
            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_global_items_text_embedding_hnsw '
                    'ON global_items USING hnsw (text_embedding vector_cosine_ops) '
                    'WITH (m = 16, ef_construction = 200);';
        END $$;
        """
    )

    # ── search_alerts.query_vector check and alter ──────────────────
    op.execute(
        """
        DO $$
        DECLARE
            curr_dim integer;
        BEGIN
            SELECT vector_dims(query_vector) INTO curr_dim 
            FROM search_alerts 
            WHERE query_vector IS NOT NULL 
            LIMIT 1;

            IF curr_dim IS NULL OR curr_dim != 1024 THEN
                EXECUTE 'DROP INDEX IF EXISTS ix_search_alerts_query_vector_hnsw;';
                EXECUTE 'UPDATE search_alerts SET query_vector = NULL;';
                EXECUTE 'ALTER TABLE search_alerts ALTER COLUMN query_vector TYPE VECTOR(1024);';
            END IF;

            EXECUTE 'CREATE INDEX IF NOT EXISTS ix_search_alerts_query_vector_hnsw '
                    'ON search_alerts USING hnsw (query_vector vector_cosine_ops) '
                    'WITH (m = 16, ef_construction = 200);';
        END $$;
        """
    )

def downgrade() -> None:
    # No-op downgrade to avoid truncating 1024d vectors
    pass
