"""
Cross-Encoder Re-ranker Service — DeepInfra-hosted Qwen3-Reranker-0.6B.

Serverless path:
  - POST {"queries": [q,q,...], "documents": [d,d,...], "instruction": "..."}
    to https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-0.6B
  - Response: a JSON array of sigmoid-style scores in [0,1], one per pair.
  - Fuse final_score = 0.6 * rerank_score + 0.4 * prior_final_score.

Graceful fallback: on API failure the service logs and returns candidates
unchanged (truncated to top_k), preserving SQL-stage ranking order so
search_v1 never returns a 500 to the mobile client.

A local self-host path is preserved behind `embedding_provider == "local"`,
exercising sentence-transformers' CrossEncoder API — not loaded by default.
"""

from __future__ import annotations

import asyncio
import logging
import math as _math
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """
    Async reranker backed by DeepInfra's dedicated /inference/<model> endpoint
    for rerankers. No torch/CrossEncoder loaded at runtime in serverless mode.
    """

    def __init__(self) -> None:
        self._http = None  # httpx.AsyncClient
        self._local_model = None
        self._local_loaded = False

    def load(self) -> None:
        """Called at FastAPI startup. In serverless mode, just prime the HTTP client."""
        if not settings.enable_reranker:
            logger.info("Reranker disabled by settings.enable_reranker=False")
            return

        if settings.embedding_provider == "local":
            self._load_local()
        else:
            logger.info(
                f"Reranker provider={settings.embedding_provider} "
                f"model={settings.reranker_model} — no local weights loaded."
            )

    def _ensure_http(self) -> None:
        if self._http is not None:
            return
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError("httpx required for reranker (DeepInfra mode).") from e
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.embedding_request_timeout_sec),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

    async def rerank_async(
        self,
        query: str,
        candidates: list[dict],
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """
        Async variant. sort candidates desc by fused final_score.
        Returns up to `top_k` (defaults to settings.reranker_final_k).
        """
        if not settings.enable_reranker or not candidates:
            return candidates[: (top_k or settings.reranker_final_k)]

        if settings.embedding_provider == "local" and self._local_model is not None:
            return self._rerank_local(query, candidates, top_k)

        self._ensure_http()
        url = (
            f"{settings.deepinfra_api_base}/inference/{settings.reranker_model}"
        )
        headers = {
            "Authorization": f"Bearer {settings.deepinfra_api_key}",
            "Content-Type": "application/json",
        }
        # DeepInfra expects one query per document (parallel lists).
        queries = [query] * len(candidates)
        documents = [c["text"] for c in candidates]
        payload = {
            "queries": queries,
            "documents": documents,
            "instruction": settings.reranker_instruction,
        }

        try:
            resp = await self._http.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # DeepInfra returns either {"results": [...]} or a bare list.
            if isinstance(data, dict):
                scores = data.get("results") or data.get("scores") or []
            else:
                scores = data
            if not isinstance(scores, list):
                scores = [scores]

            for c, s in zip(candidates, scores):
                prior = float(c.get("final_score", c.get("semantic_score") or 0.0))
                if _math.isnan(prior) or _math.isinf(prior):
                    prior = 0.0
                try:
                    s_val = float(s)
                except (TypeError, ValueError):
                    s_val = 0.0
                if _math.isnan(s_val) or _math.isinf(s_val):
                    s_val = 0.0
                c["rerank_score"] = s_val
                c["final_score"] = round(0.6 * s_val + 0.4 * prior, 4)

            reranked = sorted(candidates, key=lambda r: r["final_score"], reverse=True)
            return reranked[: (top_k or settings.reranker_final_k)]
        except Exception as e:
            logger.error(
                f"DeepInfra rerank failed ({len(candidates)} pairs): {e}. "
                f"Returning SQL-stage ranking.",
                exc_info=True,
            )
            return candidates[: (top_k or settings.reranker_final_k)]

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: Optional[int] = None,
    ) -> list[dict]:
        """Sync wrapper for callers that aren't async (test harness, scripts)."""
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "rerank() called from within an event loop. Use `await rerank_async()`."
            )
        except RuntimeError as e:
            if "no running event loop" not in str(e).lower() and "rerank() called" not in str(e):
                raise
        return asyncio.run(self.rerank_async(query, candidates, top_k=top_k))

    # ── Legacy local path (only when provider == "local") ───────
    def _load_local(self) -> None:
        if self._local_loaded:
            return
        try:
            from sentence_transformers import CrossEncoder
            import torch
            kwargs = {"trust_remote_code": True}
            if settings.reranker_device == "cuda" and torch.cuda.is_available():
                kwargs["device"] = "cuda"
                kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
            else:
                kwargs["device"] = "cpu"
            self._local_model = CrossEncoder(
                settings.reranker_model,
                max_length=settings.reranker_max_length,
                prompts={"query": settings.reranker_instruction},
                default_prompt_name="query",
                **kwargs,
            )
            self._local_loaded = True
        except Exception as e:
            logger.warning(f"Failed to load local reranker: {e}")

    def _rerank_local(
        self, query: str, candidates: list[dict], top_k: Optional[int] = None
    ) -> list[dict]:
        try:
            import torch
            pairs = [[query, c["text"]] for c in candidates]
            scores = self._local_model.predict(
                pairs, activation_fn=torch.nn.Sigmoid(), batch_size=16
            )
            if hasattr(scores, "tolist"):
                scores = scores.tolist()
            for c, s in zip(candidates, scores):
                prior = float(c.get("final_score", c.get("semantic_score") or 0.0))
                c["rerank_score"] = float(s)
                c["final_score"] = round(0.6 * float(s) + 0.4 * prior, 4)
            return sorted(candidates, key=lambda r: r["final_score"], reverse=True)[
                : (top_k or settings.reranker_final_k)
            ]
        except Exception as e:
            logger.error(f"Local rerank failed: {e}", exc_info=True)
            return candidates[: (top_k or settings.reranker_final_k)]


# ── Singleton ──────────────────────────────────────────────────────
reranker_service = RerankerService()