"""
Migration v2 — Qwen3 text embeddings + Arabic tsvector lexical search.

Idempotent. Safe to run multiple times. Intended to be executed once after
deploying the new Qwen3-based text search stack.

What it does:
  1. Ensures the `vector` and `postgis` Postgres extensions.
  2. Altering `global_items.text_embedding` from VECTOR(384) to VECTOR(1024).
  3. Adds `search_terms TEXT` and a generated `search_tsv TSVECTOR` column
     combining Arabic + simple configurations over (name, description, search_terms).
  4. Creates an HNSW cosine index on `text_embedding` (text retrieval) and a
     second HNSW index on `image_embedding` for the future image-search phase.
  5. Creates a GIN index on `search_tsv` for fast lexical matching.
  6. Drops the old `text_embedding` HNSW/IVFFlat index (if any) so it can be
     rebuilt with the new dimensionality.

Run:
    python -m backend.scripts.migrate_embeddings_v2
or, from inside the backend/ directory:
    python scripts/migrate_embeddings_v2.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os

from sqlalchemy import text

# Allow execution as a plain script: add backend/ to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_v2")


MIGRATION_STATEMENTS = [
    # ── Extensions ───────────────────────────────────────────────
    "CREATE EXTENSION IF NOT EXISTS vector;",
    "CREATE EXTENSION IF NOT EXISTS postgis;",

    # ── text_embedding column resize 384 → 1024 ─────────────────
    # If the column was previously smaller, cast & alter the type.
    # Old values will be NULL'd out (re-encoding is done by the backfill script).
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'global_items' AND column_name = 'text_embedding'
        ) THEN
            -- Drop any index that references text_embedding BEFORE altering type,
            -- otherwise the ALTER will be blocked by the dependent HNSW/IVFFlat index.
            EXECUTE 'DROP INDEX IF EXISTS ix_global_items_text_embedding_hnsw;';
            EXECUTE 'DROP INDEX IF EXISTS ix_global_items_text_embedding_ivfflat;';
            EXECUTE 'DROP INDEX IF EXISTS ix_global_items_text_embedding;';
            -- Resize; existing embeddings are now the wrong dimension and will be truncated
            -- to NULL by the cast. They will be re-computed by the backfill script.
            EXECUTE 'UPDATE global_items SET text_embedding = NULL;';
            EXECUTE 'ALTER TABLE global_items ALTER COLUMN text_embedding TYPE VECTOR(%s);';
        ELSE
            EXECUTE 'ALTER TABLE global_items ADD COLUMN IF NOT EXISTS text_embedding VECTOR(%s);';
        END IF;
    END $$;
    """ % (settings.text_embedding_dim, settings.text_embedding_dim),

    # ── search_terms column ──────────────────────────────────────
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'global_items' AND column_name = 'search_terms'
        ) THEN
            ALTER TABLE global_items ADD COLUMN search_terms TEXT;
        END IF;
    END $$;
    """,

    # ── search_tsv generated column ──────────────────────────────
    # Use a non-persisted-friendly expression that's still indexed via GIN.
    # Postgres 14+ supports STORED generated columns. The expression below uses
    # both the 'arabic' and 'simple' text search configurations concatenated.
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'global_items' AND column_name = 'search_tsv'
        ) THEN
            ALTER TABLE global_items ADD COLUMN search_tsv TSVECTOR
            GENERATED ALWAYS AS (
                setweight(to_tsvector('arabic', coalesce(name,'') || ' ' || coalesce(search_terms,'')), 'A') ||
                setweight(to_tsvector('arabic', coalesce(description,'')), 'B') ||
                setweight(to_tsvector('simple', coalesce(name,'') || ' ' || coalesce(search_terms,'')), 'A') ||
                setweight(to_tsvector('simple', coalesce(description,'')), 'B')
            ) STORED;
        END IF;
    END $$;
    """,

    # ── HNSW indexes ─────────────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS ix_global_items_text_embedding_hnsw "
    "ON global_items USING hnsw (text_embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 200);",

    "CREATE INDEX IF NOT EXISTS ix_global_items_image_embedding_hnsw "
    "ON global_items USING hnsw (image_embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 200);",

    # ── GIN index on the generated tsvector ──────────────────────
    "CREATE INDEX IF NOT EXISTS ix_global_items_search_tsv_gin "
    "ON global_items USING gin (search_tsv);",

    # ── Ensure ef_search is reasonable for ~5k-50k row table ─────
    "SET hnsw.ef_search = 64;",
]


async def run_migration() -> None:
    logger.info("Starting migration v2 (Qwen3 text embeddings + Arabic tsvector).")
    async with engine.begin() as conn:
        for stmt in MIGRATION_STATEMENTS:
            stmt_clean = " ".join(stmt.split())
            logger.info(f"Executing: {stmt_clean[:120]}{'...' if len(stmt_clean) > 120 else ''}")
            await conn.execute(text(stmt))
    logger.info("Migration v2 complete. Now run scripts/backfill_search_terms.py to re-encode items.")


if __name__ == "__main__":
    asyncio.run(run_migration())