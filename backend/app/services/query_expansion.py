"""
LLM Query Expansion Service — multi-query retrieval via DeepInfra chat completions.

Latency-tolerant, quality-first: one cheap instruct-LLM call per (cache-missed)
query produces up to N paraphrases across languages:

    "مشروب احمر ساخن"  →  ["hot red drink", "شاي", "مشروبات ساخنة"]
    "ghazaleen"        →  ["غزالين", "Ghazaleen tea", "شاي غزالين"]

The variants feed extra semantic retrieval branches and widen the lexical
tsquery before Reciprocal Rank Fusion in search_v1.

Any failure (timeout, quota, malformed JSON) degrades gracefully to an empty
list, so search never depends on this call succeeding. Responses are cached
(LRU + TTL) because popular queries repeat heavily.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict
from typing import Optional

from app.config import settings
from app.services.arabic_norm import normalize_query

logger = logging.getLogger(__name__)

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.S)

_SYSTEM_PROMPT = (
    "You are a search-query expander for a retail marketplace in the Middle East. "
    "Customers search in Arabic, English, or Arabizi (Arabic written with Latin "
    "letters and digits). Given one customer query, return ONLY a JSON array of "
    "up to {n} alternative search phrasings that mean the same thing, covering: "
    "1) the English translation, 2) the Arabic translation or a common Arabic "
    "synonym, 3) the product-category phrase. Rules: JSON array of strings only, "
    "no explanations, no duplicates of the original query, each variant under "
    "6 words."
)


class _LRUCache:
    """OrderedDict-backed LRU with TTL. Single-process; async-safe via lock."""

    def __init__(self, max_size: int, ttl_sec: int) -> None:
        self._store: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()
        self._max = max_size
        self._ttl = ttl_sec
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[list[str]]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, val = entry
            if (time.time() - ts) > self._ttl:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return list(val)

    async def put(self, key: str, val: list[str]) -> None:
        async with self._lock:
            self._store[key] = (time.time(), list(val))
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)


class QueryExpansionService:
    """Async LLM-based query expansion backed by DeepInfra chat completions."""

    def __init__(self) -> None:
        self._http = None  # httpx.AsyncClient, lazily created
        self._cache = _LRUCache(
            max_size=settings.expansion_cache_size,
            ttl_sec=settings.expansion_cache_ttl_sec,
        )

    def _ensure_http(self) -> None:
        if self._http is not None:
            return
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError(
                "httpx is required for the query expansion service."
            ) from e
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.expansion_timeout_sec),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    @staticmethod
    def _parse_variants(content: str, original: str, max_variants: int) -> list[str]:
        """Extract a JSON array of strings from the LLM response, defensively."""
        match = _JSON_ARRAY_RE.search(content or "")
        if not match:
            return []
        try:
            raw = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return []
        if not isinstance(raw, list):
            return []

        norm_original = (normalize_query(original) or original).strip().lower()
        seen: set[str] = set()
        out: list[str] = []
        for v in raw:
            if not isinstance(v, str):
                continue
            v = v.strip()
            if not v or len(v) > 80:
                continue
            key = (normalize_query(v) or v).strip().lower()
            if not key or key == norm_original or key in seen:
                continue
            seen.add(key)
            out.append(v)
            if len(out) >= max_variants:
                break
        return out

    async def expand_async(self, query: str) -> list[str]:
        """
        Return up to `settings.expansion_max_variants` paraphrases of `query`.
        Cache-first; returns [] when disabled or on any provider failure.
        """
        if not settings.enable_query_expansion or not query or not query.strip():
            return []

        cache_key = (normalize_query(query) or query).strip().lower()
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            self._ensure_http()
            url = f"{settings.deepinfra_api_base}/openai/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.deepinfra_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.expansion_model,
                "temperature": 0.2,
                "max_tokens": 150,
                "messages": [
                    {
                        "role": "system",
                        "content": _SYSTEM_PROMPT.format(
                            n=settings.expansion_max_variants
                        ),
                    },
                    {"role": "user", "content": query.strip()},
                ],
            }
            resp = await self._http.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            variants = self._parse_variants(
                content, query, settings.expansion_max_variants
            )
            await self._cache.put(cache_key, variants)
            logger.info(f"Query expansion '{query[:40]}' -> {variants}")
            return variants
        except Exception as e:
            logger.warning(f"Query expansion failed for '{query[:40]}': {e}")
            return []


# ── Singleton ──────────────────────────────────────────────────────
query_expansion_service = QueryExpansionService()
