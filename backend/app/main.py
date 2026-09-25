"""
Lamba API — Main Application Entry Point

Initializes FastAPI with:
  - CORS middleware for mobile client access
  - Lifespan events for embedding model loading
  - All API routers mounted
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from app.rate_limit import limiter

from app.config import settings
from app.database import engine
from app.services.embedding import embedding_service
from app.services.reranker import reranker_service
from app.services.http_pool import close_client
from app.services.cache import close_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/shutdown lifecycle manager.

    On startup:
      1. Create PostgreSQL tables (if not exist)
      2. Load the Qwen3 embedding model
      3. Pre-warm cross-encoder reranker
    """
    # ── Startup ─────────────────────────────────────────────
    logger.info("Starting Lamba API...")

    # Schema is managed by Alembic. On deploy run: alembic upgrade head

    # 2. Load Qwen3 text encoder
    embedding_service.load_model()

    # 3. Pre-warm the cross-encoder reranker
    if settings.enable_reranker:
        reranker_service.load()

    # 4. Ensure upload directory exists
    os.makedirs(settings.upload_dir, exist_ok=True)

    logger.info("Lamba API ready!")
    yield

    # ── Shutdown ────────────────────────────────────────────
    logger.info("Shutting down Lamba API...")
    await close_redis()
    await close_client()
    await engine.dispose()


# ── App Instance ────────────────────────────────────────────────
app = FastAPI(
    title="Lamba API",
    description="Hyper-local retail discovery with semantic search",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiting ───────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Static files (product images) ──────────────────────────────
os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

# ── Routers ─────────────────────────────────────────────────────
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
    return {"status": "healthy", "service": "lamba-api"}
