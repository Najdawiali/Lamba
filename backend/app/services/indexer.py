"""
Product Indexer — Manages the Elasticsearch products index.

Handles:
  - Index creation with proper mapping (dense_vector + geo_point)
  - Single-document indexing (on product create/update)
  - Bulk indexing (for CSV imports)
  - Document deletion
"""

import logging
import uuid

import numpy as np
from elasticsearch import AsyncElasticsearch, NotFoundError

from app.config import settings
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)

# ── Index mapping ───────────────────────────────────────────────
INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,  # Single-node dev setup
    },
    "mappings": {
        "properties": {
            "product_id": {"type": "keyword"},
            "shop_id": {"type": "keyword"},
            "name": {"type": "text", "analyzer": "standard"},
            "description": {"type": "text", "analyzer": "standard"},
            "price": {"type": "float"},
            "category": {"type": "keyword"},
            "image_url": {"type": "keyword", "index": False},
            "in_stock": {"type": "boolean"},
            "embedding": {
                "type": "dense_vector",
                "dims": 512,
                "index": True,
                "similarity": "cosine",  # HNSW index with cosine similarity
            },
            "location": {
                "type": "geo_point",  # For geo_distance filtering
            },
        }
    },
}


class IndexerService:
    """Manages the Elasticsearch product index lifecycle."""

    def __init__(self, es_client: AsyncElasticsearch):
        self.es = es_client
        self.index = settings.elasticsearch_index

    async def ensure_index(self) -> None:
        """Create the products index if it doesn't exist."""
        exists = await self.es.indices.exists(index=self.index)
        if not exists:
            logger.info(f"Creating Elasticsearch index: {self.index}")
            await self.es.indices.create(index=self.index, body=INDEX_MAPPING)
            logger.info(f"Index '{self.index}' created successfully")
        else:
            logger.info(f"Index '{self.index}' already exists")

    async def index_product(
        self,
        product_id: uuid.UUID,
        shop_id: uuid.UUID,
        name: str,
        description: str | None,
        price: float | None,
        category: str | None,
        image_url: str | None,
        in_stock: bool,
        latitude: float,
        longitude: float,
        embedding: np.ndarray | None = None,
    ) -> None:
        """
        Index a single product document in Elasticsearch.

        If no pre-computed embedding is provided, one is generated
        from the product name + description using CLIP.

        Args:
            product_id: UUID of the product (used as document ID)
            shop_id: UUID of the shop that stocks this product
            name: Product name
            description: Optional product description
            price: Product price
            category: Optional category
            image_url: Optional image URL
            in_stock: Whether the product is currently in stock
            latitude: Shop latitude
            longitude: Shop longitude
            embedding: Optional pre-computed embedding vector
        """
        if embedding is None:
            embedding = embedding_service.encode_product(name, description)

        doc = {
            "product_id": str(product_id),
            "shop_id": str(shop_id),
            "name": name,
            "description": description or "",
            "price": float(price) if price is not None else None,
            "category": category,
            "image_url": image_url,
            "in_stock": in_stock,
            "embedding": embedding.tolist(),
            "location": {
                "lat": latitude,
                "lon": longitude,
            },
        }

        await self.es.index(
            index=self.index,
            id=str(product_id),
            document=doc,
        )
        logger.debug(f"Indexed product {product_id} ({name})")

    async def update_stock(self, product_id: uuid.UUID, in_stock: bool) -> None:
        """
        Update only the in_stock field of a product document.
        Uses partial update to avoid re-computing the embedding.
        """
        try:
            await self.es.update(
                index=self.index,
                id=str(product_id),
                doc={"in_stock": in_stock},
            )
            logger.debug(f"Updated stock for {product_id}: {in_stock}")
        except NotFoundError:
            logger.warning(f"Product {product_id} not found in ES index")

    async def delete_product(self, product_id: uuid.UUID) -> None:
        """Remove a product document from the index."""
        try:
            await self.es.delete(index=self.index, id=str(product_id))
            logger.debug(f"Deleted product {product_id} from index")
        except NotFoundError:
            logger.warning(f"Product {product_id} not found in ES index")

    async def bulk_index(self, products: list[dict]) -> int:
        """
        Bulk index multiple products.

        Args:
            products: List of dicts matching the index_product args

        Returns:
            Number of successfully indexed documents
        """
        if not products:
            return 0

        actions = []
        for p in products:
            embedding = p.get("embedding")
            if embedding is None:
                embedding = embedding_service.encode_product(
                    p["name"], p.get("description")
                )

            actions.append({"index": {"_index": self.index, "_id": str(p["product_id"])}})
            actions.append({
                "product_id": str(p["product_id"]),
                "shop_id": str(p["shop_id"]),
                "name": p["name"],
                "description": p.get("description", ""),
                "price": float(p["price"]) if p.get("price") is not None else None,
                "category": p.get("category"),
                "image_url": p.get("image_url"),
                "in_stock": p.get("in_stock", True),
                "embedding": embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
                "location": {
                    "lat": p["latitude"],
                    "lon": p["longitude"],
                },
            })

        response = await self.es.bulk(operations=actions)
        errors = response.get("errors", False)
        if errors:
            error_count = sum(
                1 for item in response["items"] if "error" in item.get("index", {})
            )
            logger.error(f"Bulk index had {error_count} errors")
            return len(products) - error_count

        logger.info(f"Bulk indexed {len(products)} products")
        return len(products)
