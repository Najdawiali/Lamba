"""
Application configuration loaded from environment variables.
Uses Pydantic Settings for validation and type coercion.
"""

from typing import Dict, Any, List
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Model Registries ──────────────────────────────────────────────
SUPPORTED_EMBEDDING_MODELS: Dict[str, Dict[str, Any]] = {
    "Qwen/Qwen3-Embedding-0.6B": {
        "dim": 1024,
        "provider": "local_transformers",
        "status": "primary",
    },
    "Qwen/Qwen3-Embedding-4B": {
        "dim": 2560,
        "provider": "local_quantized_or_transformers",
        "status": "future_upgrade",
    },
    "BAAI/bge-m3": {
        "dim": 1024,
        "provider": "local_or_api",
        "status": "experimental",
    },
    "intfloat/multilingual-e5-large-instruct": {
        "dim": 1024,
        "provider": "local_or_api",
        "status": "not_recommended",
    },
}

SUPPORTED_RERANKER_MODELS: Dict[str, Dict[str, Any]] = {
    "Qwen/Qwen3-Reranker-0.6B": {
        "provider": "local_transformers",
        "status": "primary",
    },
    "Qwen/Qwen3-Reranker-4B": {
        "provider": "local_quantized_or_transformers",
        "status": "future_upgrade",
    },
}


class Settings(BaseSettings):
    """Central configuration for the Eagle Vision API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── PostgreSQL ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://eagle:eagle_secret@localhost:5432/eagle_vision"

    # ── JWT ─────────────────────────────────────────────────────
    jwt_secret: str = "change-me-to-a-real-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours

    # ── Security & CORS ─────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8081"]

    # ── CLIP Model (image search — disabled in text-only phase) ──
    clip_model_name: str = "clip-ViT-B-32"
    enable_image_search: bool = False  # When False, /image route returns 410 Gone

    # ── Embedding Provider & Model Configuration ─────────────────
    embedding_provider: str = "deepinfra"  # "local_transformers", "deepinfra"
    qwen_embed_model: str = "Qwen/Qwen3-Embedding-0.6B"
    text_embedding_dim: int = 1024

    # Local embedding configuration:
    local_model_cache_dir: str = "./models"
    local_embed_model_path: str = ""
    local_embed_device: str = "auto"
    local_embed_max_length: int = 512
    local_embed_batch_size: int = 8
    local_embed_normalize: bool = True
    local_embed_pooling: str = "auto"
    local_embed_dtype: str = "auto"

    # Instruction & Template Configuration for Qwen3-Embedding:
    embedding_query_instruction: str = "Retrieve relevant retail products or services for the given query."
    embedding_query_template: str = "Instruct: {instruction}\nQuery: {text}"
    embedding_document_template: str = "{text}"

    # Embedding Strict Modes:
    embedding_strict_mode: bool = False
    embedding_strict_indexing_mode: bool = True

    # Legacy / Remote API settings (only used when provider is API-based):
    deepinfra_api_key: str = ""
    deepinfra_api_base: str = "https://api.deepinfra.com/v1"
    embedding_request_timeout_sec: float = 15.0
    embedding_max_retries: int = 3
    embedding_api_path: str = "/openai/embeddings"

    # Legacy self-hosted-GPU settings:
    qwen_embed_device: str = "cuda"
    qwen_embed_dtype: str = "float16"

    # ── Embedding Cache Configuration (Option 0) ─────────────────
    embedding_cache_enabled: bool = True
    embedding_cache_backend: str = "memory"  # "memory" or "redis"
    embedding_cache_size: int = 2048
    embedding_cache_max_size: int = 2048
    embedding_cache_ttl_sec: int = 3600
    embedding_cache_redis_url: str = ""
    embedding_batch_size: int = 32

    # ── Reranker Provider & Model Configuration ──────────────────
    reranker_provider: str = "deepinfra"  # "local_transformers", "local", "deepinfra"
    enable_reranker: bool = True
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    local_rerank_model_path: str = ""
    local_rerank_device: str = "auto"
    local_rerank_max_length: int = 512
    local_rerank_batch_size: int = 16
    local_rerank_dtype: str = "auto"

    reranker_strict_mode: bool = False
    reranker_fallback_to_fusion: bool = True
    reranker_score_normalization: str = "auto"  # "auto", "sigmoid", "softmax", "none"

    reranker_top_k: int = 30          # How many fused candidates to cross-encode
    reranker_final_k: int = 15        # Final results returned after reranking
    reranker_weight: float = 0.7
    prior_weight: float = 0.3
    reranker_instruction_enabled: bool = False

    # Reranker Cache Configuration:
    reranker_cache_enabled: bool = True
    reranker_cache_backend: str = "memory"
    reranker_cache_max_size: int = 2048
    reranker_cache_ttl_sec: int = 3600

    # Instruction used for cross-encoder reranking:
    reranker_instruction: str = "Given a user search for local products and services, judge whether this listing is relevant."
    reranker_query_template: str = ""
    reranker_document_template: str = ""
    reranker_pair_template: str = ""
    reranker_device: str = "cuda"
    reranker_max_length: int = 8192

    # ── Post-rerank guards (Phase 1 false-positive filter) ──────
    reranker_score_gap_threshold: float = 0.15  # |score_top - score_cand|
    reranker_token_overlap_min: int = 1         # shared tokens required to NOT demote
    reranker_min_keep_score: float = 0.30       # absolute floor; below = dropped (lowered for blended scores)
    reranker_strong_confidence: float = 0.70    # ≥5 above this bar → return all

    # ── LLM Query Expansion (multi-query retrieval) ─────────────
    enable_query_expansion: bool = False
    expansion_provider: str = "disabled"  # "disabled", "local_transformers", "api"
    expansion_model: str = "Qwen/Qwen2.5-7B-Instruct"
    expansion_max_variants: int = 3
    expansion_timeout_sec: float = 20.0
    expansion_cache_size: int = 4096
    expansion_cache_max_size: int = 4096
    expansion_cache_ttl_sec: int = 86400

    # ── LLM Query Understanding ──────────────────────────────
    query_llm_model: str = "Qwen/Qwen3.6-35B-A3B"
    query_llm_fallback_model: str = "Qwen/Qwen2.5-7B-Instruct"

    # ── Hybrid fusion (RRF) & tiering ───────────────────────────
    rrf_k: int = 60
    retrieval_per_branch: int = 50
    exact_tier_threshold: float = 0.60
    recommendation_tier_threshold: float = 0.35
    language_match_boost: float = 0.05

    # ── Search ──────────────────────────────────────────────────
    default_search_radius_km: float = 5.0
    max_search_results: int = 50

    # ── Uploads ─────────────────────────────────────────────────
    upload_dir: str = "./uploads"

    def model_post_init(self, __context) -> None:
        import os
        # Docker environment URL overrides
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "true"
        if not in_docker:
            if "postgres" in self.database_url and "@postgres:" in self.database_url:
                self.database_url = self.database_url.replace("@postgres:", "@localhost:")


settings = Settings()
