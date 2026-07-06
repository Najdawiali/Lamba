"""
Application configuration loaded from environment variables.
Uses Pydantic Settings for validation and type coercion.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Eagle Vision API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── PostgreSQL ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://eagle:eagle_secret@localhost:5432/eagle_vision"

    # ── Elasticsearch ───────────────────────────────────────────
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "products"

    # ── JWT ─────────────────────────────────────────────────────
    jwt_secret: str = "change-me-to-a-real-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours

# ── CLIP Model (image search — disabled in text-only phase) ──
    clip_model_name: str = "clip-ViT-B-32"
    enable_image_search: bool = False  # When False, /image route returns 410 Gone

    # ── Embedding / Reranker provider ────────────────────────────
    # "deepinfra" (recommended) or "local" (legacy self-hosted GPU path).
    embedding_provider: str = "deepinfra"
    deepinfra_api_key: str = ""
    deepinfra_api_base: str = "https://api.deepinfra.com/v1"
    embedding_request_timeout_sec: float = 15.0
    embedding_max_retries: int = 2

    # ── Qwen3 Text Encoder (multilingual, Arabic-strong) ────────
    # Matryoshka embeddings — full 1024-d stored in pgvector.
    qwen_embed_model: str = "Qwen/Qwen3-Embedding-0.6B"
    text_embedding_dim: int = 1024
    # Legacy self-hosted-GPU settings (only used when embedding_provider == "local"):
    qwen_embed_device: str = "cuda"
    qwen_embed_dtype: str = "float16"

    # ── Query embedding cache ──────────────────────────────────
    # LRU over the last N normalized queries -> 1024-d vectors, 5-min TTL.
    # Cuts DeepInfra calls ~70% for repeat queries (e.g. "شاي", "milk", "bread").
    embedding_cache_size: int = 256
    embedding_cache_ttl_sec: int = 300

    # ── Qwen3 Re-ranker (cross-encoder, instruction-aware) ──
    enable_reranker: bool = True
    reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"
    # Legacy self-hosted-GPU setting (only used when embedding_provider == "local"):
    reranker_device: str = "cuda"
    reranker_top_k: int = 30          # How many candidates to cross-encode
    reranker_final_k: int = 15        # Final results returned after reranking
    # Qwen3-Reranker is instruction-aware. The string below is injected into the
    # model's chat template as the per-query <Instruct> field, signalling that
    # we are doing Arabic/mixed-script retail product retrieval. Qwen's own eval
    # shows a 1-5% recall lift from a task-tailored instruct.
    reranker_instruction: str = (
        "Given a customer search query in Arabic, Arabizi, or mixed Arabic/English, "
        "retrieve retail products sold by nearby shops."
    )
    # Legacy self-hosted-only:
    reranker_max_length: int = 8192

    # ── Search ──────────────────────────────────────────────────
    default_search_radius_km: float = 5.0
    max_search_results: int = 50

    # ── Uploads ─────────────────────────────────────────────────
    upload_dir: str = "./uploads"


settings = Settings()
