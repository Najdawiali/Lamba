"""
Embedding Service — DeepInfra-hosted Qwen3-Embedding-0.6B (multilingual, Arabic-strong).

Text-only search stack in serverless mode:
  - Backend POSTs each normalized query to DeepInfra's OpenAI-compatible
    /embeddings endpoint and gets back a 1024-d Matryoshka embedding.
  - LRU cache (256 queries, 5-min TTL) absorbs repeat traffic.
  - Graceful fallback: on any API failure the service logs and returns a
    zero vector, so search_v1 can degrade to tsvector-only lexical ranking
    instead of returning a 500 to the mobile client.

CLIP and the Gemma VLM remain gated behind settings.enable_image_search
for the future image-search phase — they're not loaded by default.
"""

from __future__ import annotations

import asyncio
import logging
import time
from io import BytesIO
from collections import OrderedDict
from typing import Optional

import numpy as np

from app.config import settings
from app.services.arabic_norm import normalize_query

# Optional imports kept for the future local-self-host path. They're lazy and
# only enter the runtime if settings.embedding_provider == "local", which is
# not the default.
try:
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

logger = logging.getLogger(__name__)


# ── Tiny thread-safe-ish LRU cache with TTL ────────────────────────
class _LRUCache:
    """OrderedDict-backed LRU with TTL. Single-process; async-safe via lock."""

    def __init__(self, max_size: int, ttl_sec: int) -> None:
        self._store: OrderedDict[str, tuple[float, np.ndarray]] = OrderedDict()
        self._max = max_size
        self._ttl = ttl_sec
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[np.ndarray]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, val = entry
            if (time.time() - ts) > self._ttl:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return val.copy()

    async def put(self, key: str, val: np.ndarray) -> None:
        async with self._lock:
            self._store[key] = (time.time(), val.copy())
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()


class EmbeddingService:
    """
    Async embedding service backed by DeepInfra for the Qwen3-Embedding-0.6B
    model. Maintains a small LRU cache for repeat queries.
    """

    def __init__(self) -> None:
        self._http = None  # httpx.AsyncClient, lazily created
        self._cache: Optional[_LRUCache] = None
        # Legacy local-encoder handles (only used if provider == "local"):
        self._text_model = None
        self._text_loaded = False
        # CLIP / VLM (image search) — only enabled in future phase:
        self._clip_model = None
        self._clip_dim = 512
        self._clip_loaded = False
        self.gemma_processor = None
        self.gemma_model = None

    @property
    def embedding_dim(self) -> int:
        return settings.text_embedding_dim

    # ── Lifecycle ─────────────────────────────────────────────────
    def load_model(self) -> None:
        """
        Called during FastAPI startup. In serverless (DeepInfra) mode this only
        initializes the cache and HTTP client — no torch, no model weights.
        In local mode it loads Qwen3 via sentence-transformers as before.
        """
        if self._cache is None:
            self._cache = _LRUCache(
                max_size=settings.embedding_cache_size,
                ttl_sec=settings.embedding_cache_ttl_sec,
            )

        if settings.embedding_provider == "local":
            self._load_text_encoder_local()
        else:
            logger.info(
                f"Embedding provider={settings.embedding_provider} "
                f"model={settings.qwen_embed_model} — no local weights loaded."
            )

        if settings.enable_image_search:
            self._load_clip()

    def _ensure_http(self) -> None:
        """Lazy-init the httpx.AsyncClient. Must be called inside an event loop."""
        if self._http is not None:
            return
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError(
                "httpx is required for the DeepInfra embedding provider. "
                "Install with `pip install httpx`."
            ) from e
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.embedding_request_timeout_sec),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        logger.info(f"HTTP client ready — base={settings.deepinfra_api_base}")

    # ── DeepInfra async embedding call ──────────────────────────
    async def _embed_via_deepinfra(self, text: str) -> np.ndarray:
        """
        POST one text to DeepInfra /openai/embeddings (OpenAI-compatible).
        Returns L2-normalized 1024-d float32 vector.
        """
        self._ensure_http()
        url = f"{settings.deepinfra_api_base}/openai/embeddings"
        headers = {
            "Authorization": f"Bearer {settings.deepinfra_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.qwen_embed_model,
            "input": [text],
        }

        last_err: Optional[Exception] = None
        for attempt in range(settings.embedding_max_retries + 1):
            try:
                resp = await self._http.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                vec = np.asarray(data["data"][0]["embedding"], dtype=np.float32)
                vec = vec / (np.linalg.norm(vec) + 1e-12)
                return vec
            except Exception as e:
                last_err = e
                logger.warning(
                    f"DeepInfra embeddings attempt {attempt+1} failed: {e}"
                )
                if attempt < settings.embedding_max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))

        logger.error(
            f"DeepInfra embeddings exhausted retries for text='{text[:60]}': {last_err}"
        )
        # Graceful fallback: zero vector signals "no semantic signal" to search_v1.
        return np.zeros(settings.text_embedding_dim, dtype=np.float32)

    # ── Public async API ─────────────────────────────────────────
    async def encode_text_async(self, text: str, dim: Optional[int] = None) -> np.ndarray:
        """
        Async encode of a normalized or raw query. Lookup is cache-first.
        `dim` may request a Matryoshka truncation to a smaller dimension.
        """
        if self._cache is None:
            self._cache = _LRUCache(
                max_size=settings.embedding_cache_size,
                ttl_sec=settings.embedding_cache_ttl_sec,
            )

        # Surface-form cache key uses the already-normalized text (Arabic NFKC +
        # alef/hamza unification + Arabizi → Arabic). Don't cache truncated slices
        # because reslicing is cheap.
        norm = normalize_query(text) or text
        cache_key = norm if dim is None else f"{norm}#{dim}"

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        if settings.embedding_provider == "local":
            vec = self._encode_local(norm)
        else:
            vec = await self._embed_via_deepinfra(norm)

        if dim is not None and dim < vec.shape[0]:
            vec = vec[:dim]
            n = np.linalg.norm(vec)
            if n > 0:
                vec = vec / n

        await self._cache.put(cache_key, vec)
        return vec

    def encode_text(self, text: str, dim: Optional[int] = None) -> np.ndarray:
        """
        Synchronous wrapper for scripts (backfill, seed) that aren't async.
        Runs encode_text_async inside an event loop.
        """
        try:
            asyncio.get_running_loop()
            # Already in an event loop — caller must use the async version.
            raise RuntimeError(
                "encode_text() called from within an event loop. "
                "Use `await encode_text_async()` instead."
            )
        except RuntimeError as e:
            if "no running event loop" not in str(e).lower() and "encode_text() called" not in str(e):
                raise
        return asyncio.run(self.encode_text_async(text, dim=dim))

    def encode_text_384(self, text: str) -> np.ndarray:
        """Deprecated back-compat alias (returns full 1024-d, not 384)."""
        return self.encode_text(text)

    def encode_product(self, name: str, description: str | None = None,
                        search_terms: str | None = None) -> np.ndarray:
        """Build indexed embedding for a GlobalItem. Sync wrapper for scripts."""
        parts = [name]
        if description:
            parts.append(description)
        if search_terms:
            parts.append(search_terms)
        return self.encode_text(" ".join(parts))

    async def encode_product_async(self, name: str, description: str | None = None,
                                    search_terms: str | None = None) -> np.ndarray:
        """Async version of encode_product — used by live API paths."""
        parts = [name]
        if description:
            parts.append(description)
        if search_terms:
            parts.append(search_terms)
        return await self.encode_text_async(" ".join(parts))

    # ── Legacy local self-host path (only when provider == "local") ──
    def _load_text_encoder_local(self) -> None:
        if not _HAS_ST:
            logger.warning(
                "sentence-transformers not installed. Local embedding path unavailable."
            )
            return
        if self._text_loaded:
            return
        logger.info(f"Loading local text encoder: {settings.qwen_embed_model}")
        try:
            import torch
            model_kwargs: dict = {}
            if settings.qwen_embed_device == "cuda" and torch.cuda.is_available():
                model_kwargs["device"] = "cuda"
                model_kwargs["model_kwargs"] = {
                    "torch_dtype": torch.float16 if settings.qwen_embed_dtype == "float16"
                    else torch.float32
                }
            else:
                model_kwargs["device"] = "cpu"
            self._text_model = SentenceTransformer(
                settings.qwen_embed_model, model_kwargs=model_kwargs
            )
            self._text_loaded = True
            logger.info("Local Qwen3 encoder loaded.")
        except Exception as e:
            logger.error(f"Failed to load local Qwen3 encoder: {e}", exc_info=True)

    def _encode_local(self, text: str) -> np.ndarray:
        if not self._text_loaded or self._text_model is None:
            logger.warning("Local encoder not loaded — returning zero vector.")
            return np.zeros(settings.text_embedding_dim, dtype=np.float32)
        emb = self._text_model.encode(
            text, convert_to_numpy=True, normalize_embeddings=True
        )
        return emb.astype(np.float32)

    # ── CLIP cross-modal encoder (optional, future phase) ───────
    def _load_clip(self) -> None:
        if self._clip_loaded or not _HAS_ST:
            return
        try:
            self._clip_model = SentenceTransformer(settings.clip_model_name)
            self._clip_dim = self._clip_model.get_sentence_embedding_dimension()
            self._clip_loaded = True
            logger.info(f"CLIP loaded — dim={self._clip_dim}")
        except Exception as e:
            logger.error(f"Failed to load CLIP: {e}", exc_info=True)

    def encode_image_bytes(self, image_bytes: bytes) -> np.ndarray:
        if not settings.enable_image_search:
            raise RuntimeError("Image search is disabled.")
        if not self._clip_loaded:
            self._load_clip()
        if self._clip_model is None:
            raise RuntimeError("CLIP unavailable.")
        from PIL import Image
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        emb = self._clip_model.encode(img, convert_to_numpy=True, normalize_embeddings=True)
        return emb.astype(np.float32)

    # ── VLM (disabled) ────────────────────────────────────────────
    def identify_product_from_image(self, image_bytes: bytes) -> str | None:
        return None


# ── Singleton instance ──────────────────────────────────────────
embedding_service = EmbeddingService()