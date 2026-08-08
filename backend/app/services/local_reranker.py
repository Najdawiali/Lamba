"""
Local Reranker Provider using Qwen/Qwen3-Reranker-0.6B via SentenceTransformers CrossEncoder
or Hugging Face AutoModelForSequenceClassification.

Runs locally on GPU/CPU for zero per-query API cost.
Fuses cross-encoder relevance with SQL-stage prior score:
  final_score = 0.7 * rerank_score + 0.3 * prior_score
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("SAFETENSORS_DISABLE_MMAP", "1")

import asyncio
import logging
import math
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class LocalRerankerProvider:
    """
    Local cross-encoder reranker for Qwen/Qwen3-Reranker-0.6B.
    """

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._device: str = "cpu"
        self._loaded: bool = False
        self._use_ce: bool = True
        self._lock = asyncio.Lock()

    def _determine_device(self) -> str:
        req = (getattr(settings, "local_rerank_device", "auto") or "auto").lower()
        if req != "auto":
            return req
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"

    def _load_via_direct_safetensors(self, model_name: str) -> None:
        """Fallback loader using safetensors.torch.load_file directly to avoid Windows mmap errors."""
        import torch
        from safetensors.torch import load_file
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
        from huggingface_hub import snapshot_download

        logger.info(f"Using direct safetensors load_file for reranker '{model_name}' on device={self._device}...")

        try:
            folder = snapshot_download(repo_id=model_name, local_files_only=True)
        except Exception:
            folder = snapshot_download(repo_id=model_name)

        safetensors_path = os.path.join(folder, "model.safetensors")
        self._tokenizer = AutoTokenizer.from_pretrained(folder, trust_remote_code=True)
        config = AutoConfig.from_pretrained(folder, trust_remote_code=True)

        self._model = AutoModelForSequenceClassification.from_config(config, trust_remote_code=True)
        state_dict = load_file(safetensors_path, device="cpu")
        self._model.load_state_dict(state_dict, strict=False)
        self._model = self._model.to(self._device)
        self._model.eval()
        self._use_ce = False
        self._loaded = True
        logger.info(f"Direct safetensors load succeeded for reranker '{model_name}' on device={self._device}.")

    def load_model(self) -> None:
        """Synchronously load the cross-encoder model with CPU and direct safetensors fallback."""
        if self._loaded:
            return

        target_device = self._determine_device()
        model_name = settings.reranker_model

        for device_candidate in [target_device, "cpu"]:
            try:
                self._device = device_candidate
                logger.info(
                    f"Attempting to load local reranker model '{model_name}' on device={self._device}..."
                )

                import torch
                from sentence_transformers import CrossEncoder

                kwargs: Dict[str, Any] = {"trust_remote_code": True}
                dtype_str = getattr(settings, "local_rerank_dtype", "auto")
                if self._device == "cuda":
                    kwargs["device"] = "cuda"
                    if dtype_str in ("float16", "fp16"):
                        kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
                else:
                    kwargs["device"] = "cpu"

                max_len = getattr(settings, "local_rerank_max_length", 512)
                self._model = CrossEncoder(
                    model_name,
                    max_length=max_len,
                    trust_remote_code=True,
                    **kwargs,
                )
                self._use_ce = True
                self._loaded = True
                logger.info(
                    f"Successfully loaded '{model_name}' via CrossEncoder on {self._device}."
                )
                return
            except Exception as ce_err:
                logger.warning(
                    f"CrossEncoder load failed for '{model_name}' on {device_candidate}: {ce_err}. "
                    "Attempting direct safetensors load..."
                )
                try:
                    self._load_via_direct_safetensors(model_name)
                    return
                except Exception as direct_err:
                    logger.warning(
                        f"Direct safetensors load failed for reranker '{model_name}' on {device_candidate}: {direct_err}."
                    )
                    if device_candidate == "cpu":
                        msg = f"Failed to load local reranker model '{model_name}': {direct_err}"
                        logger.error(msg, exc_info=True)
                        raise RuntimeError(msg) from direct_err

    def _score_pairs_sync(
        self, pairs: List[List[str]]
    ) -> List[float]:
        """Compute cross-encoder scores synchronously."""
        if not self._loaded or self._model is None:
            self.load_model()

        if not pairs:
            return []

        batch_size = getattr(settings, "local_rerank_batch_size", 16)
        norm_method = getattr(settings, "reranker_score_normalization", "auto").lower()

        if self._use_ce:
            import torch
            raw_scores = self._model.predict(
                pairs,
                batch_size=batch_size,
                show_progress_bar=False,
            )
            if hasattr(raw_scores, "tolist"):
                raw_scores = raw_scores.tolist()

            scores = []
            for s in raw_scores:
                val = float(s[0]) if isinstance(s, (list, tuple, np.ndarray)) else float(s)
                if norm_method == "sigmoid" or (norm_method == "auto" and (val < 0.0 or val > 1.0)):
                    val = 1.0 / (1.0 + math.exp(-val))
                scores.append(val)
            return scores
        else:
            import torch
            max_len = getattr(settings, "local_rerank_max_length", 512)
            scores = []

            for i in range(0, len(pairs), batch_size):
                batch_pairs = pairs[i : i + batch_size]
                queries = [p[0] for p in batch_pairs]
                docs = [p[1] for p in batch_pairs]

                inputs = self._tokenizer(
                    queries,
                    docs,
                    padding=True,
                    truncation=True,
                    max_length=max_len,
                    return_tensors="pt",
                ).to(self._device)

                with torch.no_grad():
                    logits = self._model(**inputs).logits
                    if logits.shape[-1] == 1:
                        batch_scores = logits.squeeze(-1)
                    else:
                        batch_scores = logits[:, -1]

                    if norm_method in ("sigmoid", "auto"):
                        batch_scores = torch.sigmoid(batch_scores)
                    
                    scores.extend(batch_scores.cpu().tolist())

            return scores

    async def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Asynchronously rerank candidates.
        """
        if not candidates:
            return []

        top_k = top_k or getattr(settings, "reranker_final_k", 15)

        try:
            pairs = [[query, c.get("text", "")] for c in candidates]
            scores = await asyncio.to_thread(self._score_pairs_sync, pairs)

            if len(scores) >= 3:
                spread = max(scores) - min(scores)
                if spread < 0.02:
                    logger.warning(
                        f"Reranker scores degenerate (spread={spread:.4f}). "
                        "Falling back to SQL-stage fusion order."
                    )
                    if getattr(settings, "reranker_fallback_to_fusion", True):
                        return self._fallback_candidates(candidates, top_k)

            w_rerank = getattr(settings, "reranker_weight", 0.7)
            w_prior = getattr(settings, "prior_weight", 0.3)

            scored_candidates = []
            for candidate, score in zip(candidates, scores):
                c = dict(candidate)
                prior = float(c.get("final_score", c.get("prior_score", c.get("semantic_score", 0.0))))
                c["rerank_score"] = round(float(score), 4)
                c["final_score"] = round(w_rerank * float(score) + w_prior * prior, 4)
                c["reranker_available"] = True
                c["reranker_fallback"] = False
                scored_candidates.append(c)

            scored_candidates.sort(key=lambda x: x["final_score"], reverse=True)

            for rank, c in enumerate(scored_candidates, 1):
                c["rerank_rank"] = rank

            return scored_candidates[:top_k]

        except Exception as e:
            logger.error(f"Local reranker failed: {e}", exc_info=True)
            if getattr(settings, "reranker_strict_mode", False):
                raise RuntimeError(f"Reranker failed under strict mode: {e}") from e

            if getattr(settings, "reranker_fallback_to_fusion", True):
                return self._fallback_candidates(candidates, top_k)
            raise

    def _fallback_candidates(
        self, candidates: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        """Order candidates by prior score when reranker fails."""
        results = []
        for rank, candidate in enumerate(candidates, 1):
            c = dict(candidate)
            c["rerank_score"] = 0.0
            c["rerank_rank"] = rank
            c["reranker_available"] = False
            c["reranker_fallback"] = True
            results.append(c)
        return results[:top_k]


local_reranker_provider = LocalRerankerProvider()
