import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """
    Get or create a persistent httpx.AsyncClient singleton with connection pooling.
    Reuses TCP/TLS connections across calls to DeepInfra / remote endpoints.
    """
    global _client
    if _client is None or _client.is_closed:
        try:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                http2=True,
            )
        except Exception:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
    return _client


async def close_client():
    """Close the shared AsyncClient connection pool gracefully during shutdown."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
