import logging
import time
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


class CircuitBreaker:
    def __init__(self, failure_threshold=3, cooldown_seconds=30):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_count = 0
        self.last_failure_time = 0
        self.is_open = False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            if not self.is_open:
                logger.warning(
                    f"Circuit breaker OPENED after {self.failure_count} consecutive failures. "
                    f"Cooldown: {self.cooldown_seconds}s"
                )
            self.is_open = True

    def record_success(self):
        if self.is_open:
            logger.info("Circuit breaker CLOSED after successful request.")
        self.failure_count = 0
        self.is_open = False

    def should_skip(self) -> bool:
        if not self.is_open:
            return False
        # Check if cooldown has passed
        if time.time() - self.last_failure_time > self.cooldown_seconds:
            logger.info("Circuit breaker cooldown passed. Allowing trial request.")
            self.is_open = False
            self.failure_count = 0
            return False
        return True


# Shared instance for all DeepInfra calls
deepinfra_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)


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


# Per-service circuit breakers — failures in one service
# don't block the others
deepinfra_llm_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
deepinfra_embedding_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
deepinfra_reranker_breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
# Catalog work (item classification + search-term enrichment) gets its own breaker so
# bulk jobs (CSV upload, catalog import) can never switch off search's LLM features.
deepinfra_catalog_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=30)
# Query understanding in the search path: its own breaker, so that a saturated small model can neither
# switch off search's other LLM features nor be held open by them; it re-tests after 20 s.
deepinfra_query_breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=20)
