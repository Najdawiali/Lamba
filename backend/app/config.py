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

    # ── CLIP Model ──────────────────────────────────────────────
    clip_model_name: str = "clip-ViT-B-32"

    # ── Search ──────────────────────────────────────────────────
    default_search_radius_km: float = 5.0
    max_search_results: int = 50

    # ── Uploads ─────────────────────────────────────────────────
    upload_dir: str = "./uploads"


settings = Settings()
