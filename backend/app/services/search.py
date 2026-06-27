"""
Search Service — Elasticsearch kNN + Hybrid Ranking

Builds kNN queries with geo-distance pre-filtering and applies
the hybrid ranking formula:

    hybrid_score = 0.7 × cosine_similarity + 0.3 × (1 - d / d_max)

Where:
    - cosine_similarity comes from the Elasticsearch kNN score
    - d is the distance from the user to the shop (km)
    - d_max is the search radius (km)
"""

import logging
import uuid

import numpy as np
from elasticsearch import AsyncElasticsearch

from app.config import settings

logger = logging.getLogger(__name__)

# ── Ranking weights ─────────────────────────────────────────────
SEMANTIC_WEIGHT = 0.7
PROXIMITY_WEIGHT = 0.3


class SearchService:
    """Handles vector search queries against Elasticsearch."""

    def __init__(self, es_client: AsyncElasticsearch):
        self.es = es_client
        self.index = settings.elasticsearch_index

    async def search_by_vector(
        self,
        vector: np.ndarray,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
        in_stock_only: bool = True,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Perform a kNN vector search with geo-distance pre-filtering.

        The query uses Elasticsearch's native kNN search with HNSW
        (Hierarchical Navigable Small World) graphs. The geo_distance
        filter is applied as a PRE-filter during graph traversal, ensuring
        only nearby products are considered.

        Args:
            vector: 512-d query vector (text or image embedding)
            latitude: User's current latitude
            longitude: User's current longitude
            radius_km: Search radius in kilometers
            in_stock_only: If True, only return in-stock products
            category: Optional category filter
            limit: Max results to return

        Returns:
            List of dicts with product_id, shop_id, score, and metadata
        """
        # ── Build pre-filter ────────────────────────────────────
        filters = [
            {
                "geo_distance": {
                    "distance": f"{radius_km}km",
                    "location": {
                        "lat": latitude,
                        "lon": longitude,
                    },
                }
            }
        ]

        if in_stock_only:
            filters.append({"term": {"in_stock": True}})

        if category:
            filters.append({"term": {"category": category}})

        # ── kNN query with pre-filtering ────────────────────────
        # Pre-filtering is critical: it limits the HNSW graph traversal
        # to only documents matching the geo + stock filters BEFORE
        # computing vector similarity. This ensures we always get
        # `k` results within the radius.
        query_body = {
            "knn": {
                "field": "embedding",
                "query_vector": vector.tolist(),
                "k": limit,
                "num_candidates": limit * 5,  # Over-fetch for better recall
                "filter": {
                    "bool": {
                        "must": filters,
                    }
                },
            },
            "size": limit,
            "_source": [
                "product_id", "shop_id", "name", "description",
                "price", "category", "image_url", "in_stock", "location",
            ],
        }

        response = await self.es.search(index=self.index, body=query_body)

        # ── Extract and enrich results ──────────────────────────
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            cosine_score = hit["_score"]  # ES kNN returns cosine similarity

            # Calculate geographic distance
            shop_lat = source["location"]["lat"]
            shop_lon = source["location"]["lon"]
            distance_km = self._haversine(latitude, longitude, shop_lat, shop_lon)

            # Hybrid ranking formula
            proximity_score = max(0.0, 1.0 - (distance_km / radius_km))
            hybrid_score = (
                SEMANTIC_WEIGHT * cosine_score
                + PROXIMITY_WEIGHT * proximity_score
            )

            results.append({
                "product_id": source["product_id"],
                "shop_id": source["shop_id"],
                "name": source["name"],
                "description": source.get("description"),
                "price": source.get("price"),
                "category": source.get("category"),
                "image_url": source.get("image_url"),
                "in_stock": source.get("in_stock", True),
                "location": source["location"],
                "distance_km": round(distance_km, 2),
                "semantic_score": round(cosine_score, 4),
                "hybrid_score": round(hybrid_score, 4),
            })

        # Re-sort by hybrid score (ES sorts by cosine only)
        results.sort(key=lambda r: r["hybrid_score"], reverse=True)
        return results

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great-circle distance between two points on Earth.

        Uses the Haversine formula for accuracy at short distances.

        Returns:
            Distance in kilometers
        """
        import math

        R = 6371.0  # Earth's radius in km

        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
