"""
Local Embedding Provider using Hugging Face Transformers / Sentence Transformers.
Loads Qwen/Qwen3-Embedding-0.6B locally on GPU/CPU without any external API calls.

Applies official Qwen3 asymmetric query instruction formatting and L2 normalization:
  - Query: "Instruct: {instruction}\nQuery: {text}"
  - Document: "{text}"
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
import time
from typing import List, Optional, Union
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider:
    """
    Local embedding provider for Qwen3-Embedding-0.6B (1024-d).
    Executes inference via SentenceTransformers or PyTorch Transformers.
    """

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._device: str = "cpu"
        self._loaded: bool = False
        self._use_st: bool = True
        self._lock = asyncio.Lock()

    def _determine_device(self) -> str:
        req = (getattr(settings, "local_embed_device", "auto") or "auto").lower()
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
        from transformers import AutoConfig, AutoModel, AutoTokenizer
        from huggingface_hub import snapshot_download

        logger.info(f"Using direct safetensors load_file for '{model_name}' on device={self._device}...")
        
        # Download or locate local snapshot directory
        try:
            folder = snapshot_download(repo_id=model_name, local_files_only=True)
        except Exception:
            folder = snapshot_download(repo_id=model_name)

        safetensors_path = os.path.join(folder, "model.safetensors")
        self._tokenizer = AutoTokenizer.from_pretrained(folder, trust_remote_code=True)
        config = AutoConfig.from_pretrained(folder, trust_remote_code=True)
        
        self._model = AutoModel.from_config(config, trust_remote_code=True)
        state_dict = load_file(safetensors_path, device="cpu")
        self._model.load_state_dict(state_dict, strict=False)
        self._model = self._model.to(self._device)
        self._model.eval()
        self._use_st = False
        self._loaded = True
        logger.info(f"Direct safetensors load succeeded for '{model_name}' on device={self._device}.")

    def load_model(self) -> None:
        """Synchronously load the model into memory/VRAM with automatic CPU & direct safetensors fallback."""
        if self._loaded:
            return

        target_device = self._determine_device()
        model_name = settings.qwen_embed_model

        for device_candidate in [target_device, "cpu"]:
            try:
                self._device = device_candidate
                logger.info(
                    f"Attempting to load local embedding model '{model_name}' on device={self._device}..."
                )

                import torch
                from sentence_transformers import SentenceTransformer

                model_kwargs = {"trust_remote_code": True}
                dtype_str = getattr(settings, "local_embed_dtype", "auto")
                if self._device == "cuda":
                    if dtype_str in ("float16", "fp16"):
                        model_kwargs["torch_dtype"] = torch.float16
                    elif dtype_str in ("bfloat16", "bf16"):
                        model_kwargs["torch_dtype"] = torch.bfloat16

                self._model = SentenceTransformer(
                    model_name,
                    device=self._device,
                    model_kwargs=model_kwargs,
                    trust_remote_code=True,
                )
                if hasattr(self._model, "max_seq_length") and settings.local_embed_max_length:
                    self._model.max_seq_length = settings.local_embed_max_length
                self._use_st = True
                self._loaded = True
                logger.info(
                    f"Successfully loaded '{model_name}' via SentenceTransformer on {self._device}."
                )
                return
            except Exception as st_err:
                logger.warning(
                    f"SentenceTransformer load failed for '{model_name}' on {device_candidate}: {st_err}. "
                    "Attempting direct safetensors load..."
                )
                try:
                    self._load_via_direct_safetensors(model_name)
                    return
                except Exception as direct_err:
                    logger.warning(
                        f"Direct safetensors load failed for '{model_name}' on {device_candidate}: {direct_err}."
                    )
                    if device_candidate == "cpu":
                        msg = f"Failed to load local embedding model '{model_name}': {direct_err}"
                        logger.error(msg, exc_info=True)
                        raise RuntimeError(msg) from direct_err

    def _format_text(self, text: str, text_type: str = "document") -> str:
        """Apply official Qwen3 query vs document template."""
        text = text.strip() if text else ""
        if text_type == "query":
            instruction = getattr(
                settings,
                "embedding_query_instruction",
                "Retrieve relevant retail products or services for the given query.",
            )
            template = getattr(
                settings,
                "embedding_query_template",
                "Instruct: {instruction}\nQuery: {text}",
            )
            return template.format(instruction=instruction, text=text)
        else:
            template = getattr(settings, "embedding_document_template", "{text}")
            return template.format(text=text)

    def _encode_sync(
        self, formatted_texts: List[str]
    ) -> np.ndarray:
        """Run batch inference synchronously."""
        if not self._loaded or self._model is None:
            self.load_model()

        if self._use_st:
            batch_size = getattr(settings, "local_embed_batch_size", 8)
            embeddings = self._model.encode(
                formatted_texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,
            )
        else:
            import torch
            max_len = getattr(settings, "local_embed_max_length", 512)
            inputs = self._tokenizer(
                formatted_texts,
                padding=True,
                truncation=True,
                max_length=max_len,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                attention_mask = inputs["attention_mask"].unsqueeze(-1)
                token_embeddings = outputs[0]
                sum_embeddings = torch.sum(token_embeddings * attention_mask, dim=1)
                sum_mask = torch.clamp(attention_mask.sum(dim=1), min=1e-9)
                embeddings = (sum_embeddings / sum_mask).cpu().numpy()

        embeddings = np.asarray(embeddings, dtype=np.float32)

        if getattr(settings, "local_embed_normalize", True):
            norms = np.linalg.norm(embeddings, axis=-1, keepdims=True)
            norms = np.where(norms == 0, 1e-12, norms)
            embeddings = embeddings / norms

        return embeddings

    async def embed_texts_batch(
        self, texts: List[str], text_type: str = "document"
    ) -> List[List[float]]:
        if not texts:
            return []

        formatted = [self._format_text(t, text_type=text_type) for t in texts]
        embeddings = await asyncio.to_thread(self._encode_sync, formatted)
        return embeddings.tolist()

    async def embed_query(self, text: str) -> List[float]:
        res = await self.embed_texts_batch([text], text_type="query")
        return res[0] if res else [0.0] * settings.text_embedding_dim

    async def embed_document(self, text: str) -> List[float]:
        res = await self.embed_texts_batch([text], text_type="document")
        return res[0] if res else [0.0] * settings.text_embedding_dim


local_embedding_provider = LocalEmbeddingProvider()
