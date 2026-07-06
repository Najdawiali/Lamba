"""
Eagle Vision API — Main Application Entry Point

Initializes FastAPI with:
  - CORS middleware for mobile client access
  - Lifespan events for CLIP model loading and ES index creation
  - All API routers mounted
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text
from app.config import settings
from app.database import engine, Base
from app.es_client import init_es_client, close_es_client, get_es_client
from app.services.embedding import embedding_service
from app.services.indexer import IndexerService
from app.services.reranker import reranker_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown lifecycle manager.

    On startup:
      1. Create PostgreSQL tables (if not exist)
      2. Load the CLIP model into memory (~340MB)
      3. Initialize Elasticsearch client and create index
    """
    # ── Startup ─────────────────────────────────────────────
    logger.info("Starting Eagle Vision API...")

    # 1. Create database tables and ensure extensions are created
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS is_currently_open BOOLEAN DEFAULT TRUE;"))
        await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS is_manual_override BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS override_set_at TIMESTAMP WITH TIME ZONE;"))
        await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS phone VARCHAR(40);"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);"))
        # Enforce unique constraint on ratings to prevent duplicate customer reviews per shop
        await conn.execute(text("ALTER TABLE ratings DROP CONSTRAINT IF EXISTS uq_customer_market;"))
        await conn.execute(text("ALTER TABLE ratings ADD CONSTRAINT uq_customer_market UNIQUE (customer_id, market_id);"))
        # Ensure barcode column exists on global_items
        await conn.execute(text("ALTER TABLE global_items ADD COLUMN IF NOT EXISTS barcode VARCHAR(100) UNIQUE;"))
    logger.info("Database tables ensured")

    # 2. Load Qwen3 text encoder (and CLIP only if image search is enabled)
    embedding_service.load_model()

    # 2b. Pre-warm the BGE cross-encoder reranker (GPU) so the first request
    #     doesn't pay the model-load cost. No-op if disabled by config.
    if settings.enable_reranker:
        reranker_service.load()

    # 3. Initialize Elasticsearch
    es = init_es_client()
    indexer = IndexerService(es)
    await indexer.ensure_index()

    # 4. Ensure upload directory exists
    os.makedirs(settings.upload_dir, exist_ok=True)

    logger.info("Eagle Vision API ready!")
    yield

    # ── Shutdown ────────────────────────────────────────────
    logger.info("Shutting down Eagle Vision API...")
    await close_es_client()
    await engine.dispose()


# ── App Instance ────────────────────────────────────────────────
app = FastAPI(
    title="Eagle Vision API",
    description="Hyper-local retail discovery with semantic & visual search",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files (product images) ──────────────────────────────
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# ── Routers ─────────────────────────────────────────────────────
# from app.api.auth import router as auth_router
from app.api.auth_v1 import router as auth_v1_router
from app.api.merchant_v1 import router as merchant_v1_router
from app.api.customer_v1 import router as customer_v1_router
from app.api.search_v1 import router as search_v1_router
from app.api.chat_v1 import router as chat_v1_router

app.include_router(auth_v1_router)
app.include_router(merchant_v1_router)
app.include_router(customer_v1_router)
app.include_router(search_v1_router)
app.include_router(chat_v1_router)




@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and load balancers."""
    return {"status": "healthy", "service": "eagle-vision-api"}
