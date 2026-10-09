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
    database_url: str = ""

    # ── JWT ─────────────────────────────────────────────────────
    jwt_secret: str = "INSECURE-CHANGE-ME-set-JWT_SECRET-in-env"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours: only for clients that don't support refresh tokens

    # Sessions for clients that send client_supports_refresh (see app/services/refresh_tokens.py):
    # short access token + rotating opaque refresh token.
    access_token_minutes: int = 30
    refresh_idle_days: int = 30        # a refresh token unused for this long is dead (sliding window)
    refresh_absolute_days: int = 90    # a session can't be renewed past this, whatever the activity
    refresh_reuse_leeway_seconds: int = 10  # replay of the just-rotated token is forgiven this long

    # ── Security & CORS ─────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8081"]

    # ── Email ───────────────────────────────────────────────
    email_provider: str = "mock"  # "mock" or "resend"
    resend_api_key: str = ""
    email_from: str = "Lamba <noreply@lambajo.com>"
    support_email: str = ""  # shown on /account-deletion; set SUPPORT_EMAIL in backend/.env

        # WhatsApp verification codes (Meta Cloud API); token and ids live in backend/.env
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_template_name: str = "lamba_verification"
    whatsapp_template_lang: str = "ar"
    whatsapp_api_version: str = "v25.0"
    phone_signup_enabled: bool = False
    
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
    reranker_model: str = "Qwen/Qwen3-Reranker-4B"
    local_rerank_model_path: str = ""
    local_rerank_device: str = "auto"
    local_rerank_max_length: int = 512
    local_rerank_batch_size: int = 16
    local_rerank_dtype: str = "auto"

    reranker_strict_mode: bool = False
    reranker_fallback_to_fusion: bool = True
    reranker_score_normalization: str = "auto"  # "auto", "sigmoid", "softmax", "none"

    reranker_top_k: int = 30          # How many fused candidates to cross-encode
    reranker_final_k: int = 8         # Final results returned after reranking
    reranker_weight: float = 0.7
    prior_weight: float = 0.3
    reranker_instruction_enabled: bool = True

    # Reranker Cache Configuration:
    reranker_cache_enabled: bool = True
    reranker_cache_backend: str = "memory"
    reranker_cache_max_size: int = 2048
    reranker_cache_ttl_sec: int = 3600

    # Instruction used for cross-encoder reranking:
    reranker_instruction: str = "Classify whether the document belongs to the same product category and type as the query. Variants like different colors or flavors of the same product are relevant."
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
    expansion_model: str = "google/gemma-4-26B-A4B-it"
    expansion_max_variants: int = 5
    expansion_timeout_sec: float = 20.0
    expansion_cache_size: int = 4096
    expansion_cache_max_size: int = 4096
    expansion_cache_ttl_sec: int = 86400

    # ── LLM Models (Real-time & Offline) ──────────────────────
    # Real-time LLM (fast, used during search)
    query_llm_model: str = "Qwen/Qwen3.6-35B-A3B"
    # The model query understanding actually uses in search. gemma-4-E4B-it was saturated at DeepInfra
    # (read timeouts and 429 "engine_overloaded", 2026-10-09); gemma-4-26B-A4B-it answered 24 of 24 calls,
    # median 1.8 s, and is what production runs through QUERY_LLM_FALLBACK_MODEL.
    query_llm_fallback_model: str = "google/gemma-4-26B-A4B-it"

    # ── Query understanding in the search path ─────────────────
    # Search waits at most this long, counted from the start of the first embedding, for the model; after
    # that it goes on with the rule-based attributes. Measured on the server (24 calls of the production
    # prompt): median 1.77 s, 90% within 2.1 s, 96% within 2.3 s, one outlier at 3.8 s.
    query_understanding_budget_seconds: float = 2.5
    # The model call itself may outlive the budget, so that a late answer still fills the cache.
    query_llm_call_timeout_seconds: float = 6.0
    # DeepInfra answers 429 at once instead of queueing the request when the model is at capacity.
    query_llm_fail_fast: bool = True
    # Model calls in flight at the same time; beyond that the rule-based attributes alone are used.
    query_llm_max_inflight: int = 8

    # Offline LLM (smarter, used for enrichment and batch processing)
    offline_llm_model: str = "google/gemma-4-31B-it"

    # Classifier: restriction check + category for items entering the catalog
    classifier_model: str = "google/gemma-4-26B-A4B-it"
    classifier_secondary_model: str = "google/gemma-4-31B-it"

    # ── Hybrid fusion (RRF) & tiering ───────────────────────────
    rrf_k: int = 60
    retrieval_per_branch: int = 200
    exact_tier_threshold: float = 0.60
    recommendation_tier_threshold: float = 0.35
    language_match_boost: float = 0.05

    # ── Redis Cache Configuration ───────────────────────────────
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""
    cache_expansion_ttl: int = 7200    # 2 hours — expansion results are stable
    cache_search_ttl: int = 300        # 5 minutes — results may change with new products
    cache_qu_ttl: int = 604800         # 7 days — what a query means does not change; the key holds model + prompt

    # ── Search ──────────────────────────────────────────────────
    default_search_radius_km: float = 5.0
    max_search_results: int = 50

    # ── Uploads ─────────────────────────────────────────────────
    upload_dir: str = "./uploads"

    # ── Storage Backend ─────────────────────────────────────────
    storage_backend: str = "local"  # "local" or "r2"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "lamba-images"
    r2_public_url: str = ""  # e.g. https://pub-xxx.r2.dev

    def model_post_init(self, __context) -> None:
        import os
        # Docker environment URL overrides
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "true"
        if not in_docker:
            if "postgres" in self.database_url and "@postgres:" in self.database_url:
                self.database_url = self.database_url.replace("@postgres:", "@localhost:")
            if self.redis_host == "redis":
                self.redis_host = "localhost"

        # ── Security: reject insecure JWT secret ──────────────────
        _insecure_defaults = {"change-me-to-a-real-secret-key", "secret", "changeme", "insecure-change-me-set-jwt_secret-in-env", ""}
        if self.jwt_secret.lower().strip() in _insecure_defaults or len(self.jwt_secret) < 32:
            import warnings
            warnings.warn(
                "JWT_SECRET is insecure (default or < 32 chars). "
                "Set a strong JWT_SECRET in your .env file. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\"",
                stacklevel=2,
            )


settings = Settings()
