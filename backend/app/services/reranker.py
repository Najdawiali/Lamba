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
    ) -> List[float]:
        """Call DeepInfra reranker API with retry logic."""
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

        max_retries = getattr(settings, "embedding_max_retries", 3)
        timeout = getattr(settings, "embedding_request_timeout_sec", 15.0)
        last_error = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        raise Exception(f"Retryable HTTP {resp.status_code}")
                    resp.raise_for_status()
                    data = resp.json()
                    raw_scores = data["scores"]

                    # ── Diagnostic: log raw API response ──────────────
                    logger.debug(
                        "[RERANKER API] Raw scores from DeepInfra: %s",
                        [round(s, 6) for s in raw_scores],
                    )
                    return raw_scores
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
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
                scores = await self._call_deepinfra_reranker(query, candidates)
                k = top_k or getattr(settings, "reranker_final_k", 15)

                # ── Diagnostic: log raw scores before any processing ──
                logger.debug(
                    "[RERANKER DEBUG] provider=deepinfra  query=%r  "
                    "instruction_enabled=%s  num_docs=%d",
                    query,
                    getattr(settings, "reranker_instruction_enabled", False),
                    len(candidates),
                )
                for idx, (c_item, raw_s) in enumerate(zip(candidates, scores)):
                    doc_text = c_item.get("text", c_item.get("name", ""))
                    logger.debug(
                        "[RERANKER DEBUG]  doc#%d  raw_score=%.6f  text=%r",
                        idx, raw_s, doc_text[:120],
                    )

                # ── Normalize scores ──────────────────────────────────
                # DeepInfra may return raw logits OR pre-sigmoid values.
                # Either way, if the spread is tiny the scores are useless
                # for ranking. Apply min-max normalization across the batch
                # to restore discrimination.
                import math as _math
                norm_method = getattr(settings, "reranker_score_normalization", "auto").lower()

                # Step 1: If scores look like raw logits (any outside [0,1]),
                # apply sigmoid first to get them into [0,1].
                normalized = []
                needs_sigmoid = any(s < 0.0 or s > 1.0 for s in scores)
                for s in scores:
                    v = float(s)
                    if norm_method == "sigmoid" or (norm_method == "auto" and needs_sigmoid):
                        v = 1.0 / (1.0 + _math.exp(-v))
                    normalized.append(v)

                # Step 2: Check spread & max score before rescaling.
                # If all scores are near zero (max_score < 0.10), nothing in the catalog matched.
                # Do NOT rescale in that case — let them fall below the 0.50 guard floor naturally.
                lo, hi = min(normalized), max(normalized)
                spread = hi - lo
                if spread < 0.05 and hi < 0.10:
                    logger.debug(
                        "[RERANKER DEBUG] All scores are near zero (max=%.4f, spread=%.4f). "
                        "Preserving raw scores so guard filter drops them.",
                        hi, spread,
                    )
                elif spread < 0.05 and hi >= 0.10 and len(normalized) > 1:
                    logger.debug(
                        "[RERANKER DEBUG] Score spread=%.6f is compressed (range %.4f–%.4f). "
                        "Applying min-max rescaling to [0.3, 1.0].",
                        spread, lo, hi,
                    )
                    # Rescale to [0.3, 1.0] so floor guard (0.50) still works
                    for j in range(len(normalized)):
                        normalized[j] = 0.3 + 0.7 * ((normalized[j] - lo) / spread) if spread > 0 else 0.5
                else:
                    logger.debug(
                        "[RERANKER DEBUG] Score spread=%.6f OK (range %.4f–%.4f).",
                        spread, lo, hi,
                    )

                for idx, (c_item, norm_s) in enumerate(zip(candidates, normalized)):
                    logger.debug(
                        "[RERANKER DEBUG]  doc#%d  normalized_score=%.6f  name=%r",
                        idx, norm_s,
                        c_item.get("result", {}).name if hasattr(c_item.get("result", {}), "name") else "?",
                    )

                for i, c in enumerate(candidates):
                    c["rerank_score"] = normalized[i] if i < len(normalized) else 0.0
                    c["reranker_available"] = True
                    c["reranker_fallback"] = False
                # Sort by rerank_score descending
                candidates.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
                return candidates[:k]
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