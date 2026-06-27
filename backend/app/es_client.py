"""
Elasticsearch client provider.
Separated from main.py to avoid circular imports with API routes.
"""

from elasticsearch import AsyncElasticsearch
from app.config import settings

_es_client: AsyncElasticsearch | None = None


def init_es_client() -> AsyncElasticsearch:
    """Initialize the Elasticsearch async client. Called once at startup."""
    global _es_client
    _es_client = AsyncElasticsearch(hosts=[settings.elasticsearch_url])
    return _es_client


def get_es_client() -> AsyncElasticsearch:
    """Get the shared Elasticsearch client instance."""
    if _es_client is None:
        raise RuntimeError("Elasticsearch client not initialized. Call init_es_client() first.")
    return _es_client


async def close_es_client() -> None:
    """Close the Elasticsearch client. Called at shutdown."""
    global _es_client
    if _es_client:
        await _es_client.close()
        _es_client = None
