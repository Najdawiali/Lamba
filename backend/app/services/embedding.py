"""
Embedding Service — Provider Abstraction supporting Local Qwen3-Embedding-0.6B (1024-d)
and legacy API backends. Maintains thread-safe LRU caching with key normalization.
"""

from __future__ import annotations

import asyncio
import logging
import time
import re
from collections import OrderedDict
from typing import Optional, List
import numpy as np

from app.config import settings
from app.services.arabic_norm import normalize_query
from app.services.local_embedding import local_embedding_provider
from app.services.http_pool import get_client

logger = logging.getLogger(__name__)


def normalize_cache_key(text: str) -> str:
    """
    Produce canonical cache keys:
    - Arabic NFKC normalization
    - Diacritic, tatweel removal
    - Alef/Hamza unification
    - Taa Marbuta normalization (ة -> ه)
    - Whitespace collapse
    - Lowercase Latin text
    """
    if not text:
        return ""
    norm = normalize_query(text) or text
    norm = norm.strip().lower()
    # Taa Marbuta normalization for caching
    norm = re.sub(r"ة\b", "ه", norm)
    norm = re.sub(r"\s+", " ", norm)
    return norm


class _LRUCache:
    """OrderedDict-backed LRU with TTL for embedding vectors."""

    def __init__(self, max_size: int, ttl_sec: int) -> None:
        self._store: OrderedDict[str, tuple[float, np.ndarray]] = OrderedDict()
        self._max = max_size
        self._ttl = ttl_sec
        self._lock = asyncio.Lock()
        self.hits: int = 0
        self.misses: int = 0
        self.errors: int = 0

    async def get(self, key: str) -> Optional[np.ndarray]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            ts, val = entry
            if (time.time() - ts) > self._ttl:
                self._store.pop(key, None)
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return val.copy()

    async def put(self, key: str, val: np.ndarray) -> None:
        if not bool(val.any()) or np.isnan(val).any():
            # Never cache zero or NaN vectors
            return
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
    Async embedding service backed by local transformers or API providers.
    """

    def __init__(self) -> None:
        self._http = None
        self._cache: Optional[_LRUCache] = None
        self._failures_count: int = 0

    @property
    def embedding_dim(self) -> int:
        return settings.text_embedding_dim

    def load_model(self) -> None:
        """Called during FastAPI startup."""
        if self._cache is None:
            self._cache = _LRUCache(
                max_size=getattr(settings, "embedding_cache_max_size", 2048),
                ttl_sec=getattr(settings, "embedding_cache_ttl_sec", 3600),
            )

        provider = settings.embedding_provider.lower()
        if provider == "local_transformers":
            local_embedding_provider.load_model()
            logger.info("Local transformers embedding provider initialized.")
        elif provider == "deepinfra":
            if not settings.deepinfra_api_key or "REPLACE" in settings.deepinfra_api_key:
                logger.warning(
                    f"Embedding provider '{provider}' selected but DEEPINFRA_API_KEY is invalid/missing."
                )
        else:
            logger.warning(f"Embedding provider '{provider}' is currently stubbed/disabled.")

    async def _embed_via_api(self, text: str) -> np.ndarray:
        """Remote API embedding request with retry logic."""
        # Check API key
        if not settings.deepinfra_api_key or "REPLACE" in settings.deepinfra_api_key:
            msg = "Embedding API key is invalid or unconfigured."
            logger.error(msg)
            if getattr(settings, "embedding_strict_mode", False):
                raise RuntimeError(msg)
            return np.zeros(settings.text_embedding_dim, dtype=np.float32)

        client = get_client()

        url = f"{settings.deepinfra_api_base}{settings.embedding_api_path}"
        headers = {
            "Authorization": f"Bearer {settings.deepinfra_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.qwen_embed_model,
            "input": [text],
            "encoding_format": "float",
            "dimensions": settings.text_embedding_dim,
        }

        last_error = None
        max_retries = settings.embedding_max_retries
        for attempt in range(max_retries):
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise Exception(f"Retryable HTTP {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()
                vec = np.asarray(data["data"][0]["embedding"], dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                return vec
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning(
                        f"Embedding API attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {backoff}s"
                    )
                    await asyncio.sleep(backoff)

        self._failures_count += 1
        logger.error(f"Embedding API request failed after {max_retries} retries: {last_error}")
        if getattr(settings, "embedding_strict_mode", False):
            raise RuntimeError(f"Embedding API failed under strict mode: {last_error}") from last_error
        return np.zeros(settings.text_embedding_dim, dtype=np.float32)

    async def encode_text_async(
        self, text: str, text_type: str = "query", dim: Optional[int] = None
    ) -> np.ndarray:
        """
        Async encode a string query or document. Cache-first.
        """
        if self._cache is None:
            self._cache = _LRUCache(
                max_size=getattr(settings, "embedding_cache_max_size", 2048),
                ttl_sec=getattr(settings, "embedding_cache_ttl_sec", 3600),
            )

        provider = settings.embedding_provider.lower()

        # Apply instruction template for API-based queries BEFORE cache lookup.
        # Local providers handle templates internally.
        if provider == "deepinfra" and text_type == "query":
            text = settings.embedding_query_template.format(
                instruction=settings.embedding_query_instruction,
                text=text,
            )

        cache_key = normalize_cache_key(text)
        if dim is not None:
            cache_key = f"{cache_key}#{dim}"

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        if provider == "local_transformers":
            if text_type == "query":
                vec_list = await local_embedding_provider.embed_query(text)
            else:
                vec_list = await local_embedding_provider.embed_document(text)
            vec = np.asarray(vec_list, dtype=np.float32)
        elif provider == "deepinfra":
            vec = await self._embed_via_api(text)
        else:
            logger.warning(f"Provider '{provider}' unavailable — returning zero vector.")
            vec = np.zeros(settings.text_embedding_dim, dtype=np.float32)

        if dim is not None and dim < vec.shape[0]:
            vec = vec[:dim]
            n = np.linalg.norm(vec)
            if n > 0:
                vec = vec / n

        if bool(vec.any()):
            await self._cache.put(cache_key, vec)

        return vec

    async def embed_texts_batch(
        self, texts: List[str], text_type: str = "query"
    ) -> List[List[float]]:
        """
        Async batch embedding for multi-query search or batch indexing.
        """
        if not texts:
            return []

        provider = settings.embedding_provider.lower()
        if provider == "local_transformers":
            return await local_embedding_provider.embed_texts_batch(texts, text_type=text_type)

        if provider == "deepinfra":
            # Apply instruction template for queries
            if text_type == "query":
                texts = [
                    settings.embedding_query_template.format(
                        instruction=settings.embedding_query_instruction,
                        text=t,
                    )
                    for t in texts
                ]

            # Batch via API in chunks
            all_results = []
            batch_size = settings.embedding_batch_size
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                if not settings.deepinfra_api_key or "REPLACE" in settings.deepinfra_api_key:
                    all_results.extend(
                        [np.zeros(settings.text_embedding_dim, dtype=np.float32).tolist()] * len(batch)
                    )
                    continue

                client = get_client()

                url = f"{settings.deepinfra_api_base}{settings.embedding_api_path}"
                headers = {
                    "Authorization": f"Bearer {settings.deepinfra_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": settings.qwen_embed_model,
                    "input": batch,
                    "encoding_format": "float",
                    "dimensions": settings.text_embedding_dim,
                }

                last_error = None
                max_retries = settings.embedding_max_retries
                for attempt in range(max_retries):
                    try:
                        resp = await client.post(url, headers=headers, json=payload)
                        if resp.status_code in (429, 500, 502, 503, 504):
                            raise Exception(f"Retryable HTTP {resp.status_code}")
                        resp.raise_for_status()
                        data = resp.json()
                        normed_vecs = []
                        for item in data["data"]:
                            v = np.asarray(item["embedding"], dtype=np.float32)
                            n = np.linalg.norm(v)
                            if n > 0:
                                v = v / n
                            normed_vecs.append(v.tolist())
                        all_results.extend(normed_vecs)
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            backoff = 0.5 * (2 ** attempt)
                            logger.warning(
                                f"Batch embedding attempt {attempt + 1}/{max_retries} failed: {e}. "
                                f"Retrying in {backoff}s"
                            )
                            await asyncio.sleep(backoff)

                if last_error:
                    logger.error(f"Batch embedding failed after {max_retries} retries: {last_error}")
                    all_results.extend(
                        [np.zeros(settings.text_embedding_dim, dtype=np.float32).tolist()] * len(batch)
                    )

            return all_results

        # Fallback for unknown providers
        results = []
        for t in texts:
            v = await self.encode_text_async(t, text_type=text_type)
            results.append(v.tolist())
        return results

    def encode_text(self, text: str, dim: Optional[int] = None) -> np.ndarray:
        """Sync wrapper for scripts."""
        try:
            asyncio.get_running_loop()
            raise RuntimeError("encode_text called inside loop — use await encode_text_async()")
        except RuntimeError as e:
            if "no running event loop" not in str(e).lower() and "encode_text" not in str(e):
                raise
        return asyncio.run(self.encode_text_async(text, dim=dim))

    def encode_product(
        self, name: str, description: Optional[str] = None, search_terms: Optional[str] = None
    ) -> np.ndarray:
        parts = [name]
        if description:
            parts.append(description)
        if search_terms:
            parts.append(search_terms)
        return self.encode_text(" ".join(parts))

    async def encode_product_async(
        self, name: str, description: Optional[str] = None, search_terms: Optional[str] = None
    ) -> np.ndarray:
        parts = [name]
        if description:
            parts.append(description)
        if search_terms:
            parts.append(search_terms)
        return await self.encode_text_async(" ".join(parts), text_type="document")


embedding_service = EmbeddingService()