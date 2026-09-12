"""
Cross-Encoder Reranker Service — Provider Abstraction supporting Local Qwen3-Reranker-0.6B
and legacy API backends.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Optional, List, Dict, Any

from app.config import settings
from app.services.local_reranker import local_reranker_provider
from app.services.http_pool import get_client, deepinfra_breaker

logger = logging.getLogger(__name__)


class RerankerService:
    """
    Reranker service backed by local transformers or remote APIs.
    """

    def __init__(self) -> None:
        self._http = None

    def load(self) -> None:
        """Called during FastAPI startup."""
        if not getattr(settings, "enable_reranker", True):
            logger.info("Reranker disabled by settings.enable_reranker=False")
            return

        provider = getattr(settings, "reranker_provider", "local_transformers").lower()
        if provider == "local_transformers":
            local_reranker_provider.load_model()
            logger.info("Local transformers reranker loaded.")
        elif provider == "local":
            local_reranker_provider.load_model()
        else:
            logger.info(f"Reranker provider '{provider}' configured.")

    async def _call_deepinfra_reranker(
        self, query: str, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Call DeepInfra reranker API with retry logic.
        Returns list of {"index": int, "score": float} dicts (min-max normalized).
        """
        import httpx

        url = f"https://api.deepinfra.com/v1/inference/{settings.reranker_model}"
        headers = {
            "Authorization": f"Bearer {settings.deepinfra_api_key}",
            "Content-Type": "application/json",
        }
        documents = [c.get("text", c.get("name", "")) for c in candidates]
        payload: Dict[str, Any] = {
            "queries": [query],
            "documents": documents,
        }
        if getattr(settings, "reranker_instruction_enabled", True):
            payload["instruction"] = settings.reranker_instruction

        # ── Diagnostic: log outbound payload ──────────────────────
        logger.debug(
            "[RERANKER API] Sending to DeepInfra: model=%s  query=%r  "
            "instruction=%r  num_documents=%d",
            settings.reranker_model, query,
            payload.get("instruction", "<none>"),
            len(documents),
        )
        for di, doc in enumerate(documents):
            logger.debug(
                "[RERANKER API]  document[%d] len=%d  text=%r",
                di, len(doc), doc[:200],
            )

        if deepinfra_breaker.should_skip():
            logger.warning("DeepInfra circuit breaker is OPEN. Skipping reranker API call.")
            raise RuntimeError("DeepInfra circuit breaker is OPEN.")

        max_retries = getattr(settings, "embedding_max_retries", 3)
        client = get_client()
        last_error = None
        for attempt in range(max_retries):
            if deepinfra_breaker.should_skip():
                logger.warning("DeepInfra circuit breaker tripped during reranker retries. Aborting.")
                break
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code in (429, 500, 502, 503, 504):
                    deepinfra_breaker.record_failure()
                    raise Exception(f"Retryable HTTP {resp.status_code}")
                resp.raise_for_status()
                data = resp.json()

                # DeepInfra returns either a flat "scores" list (positional)
                # or a "results" list of {index, relevance_score} dicts
                # (sorted by score descending, NOT positional).
                if "scores" in data:
                    raw_scores = data["scores"]
                elif "results" in data:
                    # Map scores back to positional order using the index field
                    raw_scores = [0.0] * len(candidates)
                    for item in data["results"]:
                        idx = item.get("index", None)
                        score = item.get("relevance_score", item.get("score", 0.0))
                        if idx is not None and idx < len(raw_scores):
                            raw_scores[idx] = score
                        else:
                            logger.warning(f"[RERANKER] Invalid index in response item: {item}")
                else:
                    raise KeyError(f"Unexpected reranker response keys: {list(data.keys())}")

                # ── Diagnostic: log raw API response ──────────────
                logger.debug(
                    "[RERANKER API] Raw scores from DeepInfra: %s",
                    [round(s, 6) for s in raw_scores],
                )

                result = []
                for i, score in enumerate(raw_scores):
                    result.append({"index": i, "score": score})

                logger.info(f"[RERANKER] Scored {len(raw_scores)} documents via DeepInfra")
                deepinfra_breaker.record_success()
                return result
            except Exception as e:
                last_error = e
                if "Retryable HTTP" not in str(e):
                    deepinfra_breaker.record_failure()
                if attempt < max_retries - 1 and not deepinfra_breaker.should_skip():
                    backoff = 0.5 * (2 ** attempt)
                    logger.warning(
                        f"Reranker API attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {backoff}s"
                    )
                    await asyncio.sleep(backoff)

        raise RuntimeError(f"DeepInfra reranker failed after {max_retries} retries: {last_error}")

    async def rerank_async(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        brand_terms: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Asynchronously rerank candidates.
        """
        if not getattr(settings, "enable_reranker", True) or not candidates:
            k = top_k or getattr(settings, "reranker_final_k", 15)
            return candidates[:k]

        provider = getattr(settings, "reranker_provider", "local_transformers").lower()

        if provider in ("local_transformers", "local"):
            return await local_reranker_provider.rerank(query, candidates, top_k=top_k)

        elif provider == "deepinfra":
            # DeepInfra reranker API call
            try:
                score_items = await self._call_deepinfra_reranker(query, candidates)
                k = top_k or getattr(settings, "reranker_final_k", 15)

                # Map scores back to correct candidates using the index field
                for item in score_items:
                    idx = item.get("index")
                    if idx is not None and idx < len(candidates):
                        candidates[idx]["rerank_score"] = item["score"]
                    else:
                        logger.warning(f"[RERANKER] Missing or invalid index in score item: {item}")

                # Sort by rerank_score descending, return top_k
                reranked = sorted(
                    [c for c in candidates if "rerank_score" in c],
                    key=lambda c: c["rerank_score"],
                    reverse=True,
                )
                # Include any candidates that didn't get a rerank score at the end
                unranked = [c for c in candidates if "rerank_score" not in c]
                for c in unranked:
                    c["rerank_score"] = c.get("cosine_sim", 0.5)
                return (reranked + unranked)[:k]
            except Exception as e:
                logger.warning(
                    f"DeepInfra reranker failed, falling back to fusion rank: {e}"
                )
                k = top_k or getattr(settings, "reranker_final_k", 15)
                for c in candidates:
                    c["rerank_score"] = 0.0
                    c["reranker_available"] = False
                    c["reranker_fallback"] = True
                return candidates[:k]
        else:
            # Unknown provider fallback
            logger.warning(
                f"Reranker provider '{provider}' is unavailable/disabled. Preserving prior fusion rank."
            )
            k = top_k or getattr(settings, "reranker_final_k", 15)
            for c in candidates:
                c["rerank_score"] = 0.0
                c["reranker_available"] = False
                c["reranker_fallback"] = True
            return candidates[:k]

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        brand_terms: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Synchronous wrapper."""
        try:
            asyncio.get_running_loop()
            raise RuntimeError("rerank() called inside loop — use await rerank_async()")
        except RuntimeError as e:
            if "no running event loop" not in str(e).lower() and "rerank()" not in str(e):
                raise
        return asyncio.run(self.rerank_async(query, candidates, top_k=top_k, brand_terms=brand_terms))


reranker_service = RerankerService()