"""
Product Indexer Service (Decommissioned OpenSearch).
PostgreSQL pgvector + tsvector serve all search queries.
"""

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)


class IndexerService:
    """Stub indexer service (OpenSearch decommissioned)."""

    def __init__(self, es_client: Any = None):
        pass

    async def ensure_index(self) -> None:
        pass

    async def index_product(
        self,
        product_id: uuid.UUID,
        shop_id: uuid.UUID,
        name: str,
        description: Optional[str],
        price: Optional[float],
        category: Optional[str],
        image_url: Optional[str],
        in_stock: bool,
        latitude: float,
        longitude: float,
        embedding: Any = None,
        brand_id: Optional[str] = None,
    ) -> None:
        pass

    async def update_stock(self, product_id: uuid.UUID, in_stock: bool) -> None:
        pass

    async def delete_product(self, product_id: uuid.UUID) -> None:
        pass

    async def bulk_index(self, products: list[dict]) -> int:
        return 0
