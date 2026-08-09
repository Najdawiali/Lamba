"""
Unit tests for the 4 search performance optimizations:
1. HTTP connection pooling (http_pool)
2. Batch embedding
3. Parallelized query expansion + embedding
4. Redis caching & serialization
"""

import asyncio
import unittest
import uuid
import numpy as np
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
from app.services.http_pool import get_client, close_client
from app.services.cache import (
    _cache_key,
    get_cached_expansion,
    cache_expansion,
    get_cached_search,
    cache_search,
    close_redis,
)
from app.schemas.search_v1 import HybridSearchResponse, HybridSearchResultItem


class TestHttpPool(unittest.IsolatedAsyncioTestCase):
    async def test_get_client_singleton(self):
        """get_client should return the same client instance on subsequent calls."""
        c1 = get_client()
        c2 = get_client()
        self.assertIs(c1, c2)
        self.assertFalse(c1.is_closed)

    async def test_close_client(self):
        """close_client should close the client and reset the singleton."""
        c1 = get_client()
        await close_client()
        self.assertTrue(c1.is_closed)
        c2 = get_client()
        self.assertIsNot(c1, c2)
        self.assertFalse(c2.is_closed)
        await close_client()


class TestRedisCaching(unittest.IsolatedAsyncioTestCase):
    def test_cache_key_generation(self):
        """Cache keys should be deterministic regardless of keyword ordering or casing."""
        k1 = _cache_key("search", "حليب", lat=31.954, lng=35.911, lt="product")
        k2 = _cache_key("search", "حليب ", lat=31.954, lng=35.911, lt="product")
        self.assertEqual(k1, k2)
        self.assertTrue(k1.startswith("lamba:search:"))

    async def test_search_response_serialization_with_pydantic_and_uuids(self):
        """cache_search should serialize Pydantic models with UUIDs and floats without crashing."""
        sample_item = HybridSearchResultItem(
            item_id=uuid.uuid4(),
            market_item_id=uuid.uuid4(),
            market_id=uuid.uuid4(),
            name="شاي أحمد 100 كيس",
            name_ar="شاي أحمد 100 كيس",
            name_en="Ahmad Tea 100 Bags",
            category="مشروبات",
            price=2.50,
            stock_count=10,
            in_stock=True,
            market_name="سوبرماركت المدينة",
            market_address="عمان - شارع الجامعة",
            latitude=31.954,
            longitude=35.911,
            market_is_open=True,
            distance_km=1.25,
            semantic_score=0.892,
            proximity_score=0.920,
            final_score=0.850,
            image_url=None,
            listing_type="product",
        )
        sample_resp = HybridSearchResponse(
            found=True,
            action=None,
            search_mode="exact_matches",
            results=[sample_item],
        )

        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch("app.services.cache.get_redis", return_value=mock_redis):
            # Should not raise exception
            await cache_search("شاي", 31.95, 35.91, "product", sample_resp)
            mock_redis.set.assert_awaited_once()

    async def test_redis_graceful_failure_when_down(self):
        """When Redis fails or is down, caching functions must return None without raising."""
        with patch("app.services.cache.get_redis", side_effect=ConnectionError("Redis connection refused")):
            exp = await get_cached_expansion("شاي")
            self.assertIsNone(exp)

            search = await get_cached_search("شاي", 31.95, 35.91, "product")
            self.assertIsNone(search)

            # Neither cache_expansion nor cache_search should raise
            await cache_expansion("شاي", ["tea", "شاي أسود"])
            await cache_search("شاي", 31.95, 35.91, "product", {"results": []})


class TestQueryExpansionCacheIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_expand_async_uses_cached_value(self):
        """expand_async should return cached variants without calling LLM."""
        from app.services.query_expansion import query_expansion_service

        with patch("app.services.query_expansion.settings") as ms, \
             patch("app.services.query_expansion.get_cached_expansion", new_callable=AsyncMock) as mock_get_cache, \
             patch("app.services.query_expansion.llm_adapter.complete_chat_full", new_callable=AsyncMock) as mock_llm:
            ms.enable_query_expansion = True
            ms.expansion_provider = "api"
            mock_get_cache.return_value = ["tea", "شاي أحمر"]

            variants = await query_expansion_service.expand_async("شاي")
            self.assertEqual(variants, ["tea", "شاي أحمر"])
            mock_llm.assert_not_awaited()


class TestBatchEmbedding(unittest.IsolatedAsyncioTestCase):
    async def test_embed_texts_batch_normalizes_output(self):
        """embed_texts_batch should normalize all vector outputs and use http pool."""
        from app.services.embedding import EmbeddingService

        svc = EmbeddingService()
        raw_vec = [3.0, 4.0] + [0.0] * 1022  # norm = 5.0
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"embedding": raw_vec},
                {"embedding": raw_vec},
            ]
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp

        with patch("app.services.embedding.settings") as ms, \
             patch("app.services.embedding.get_client", return_value=mock_client):
            ms.embedding_provider = "deepinfra"
            ms.deepinfra_api_key = "test-key"
            ms.deepinfra_api_base = "https://api.deepinfra.com/v1"
            ms.embedding_api_path = "/openai/embeddings"
            ms.qwen_embed_model = "Qwen/Qwen3-Embedding-0.6B"
            ms.text_embedding_dim = 1024
            ms.embedding_batch_size = 32
            ms.embedding_max_retries = 1
            ms.embedding_query_template = "Instruct: {instruction}\nQuery: {text}"
            ms.embedding_query_instruction = "Retrieve retail items"

            results = await svc.embed_texts_batch(["حليب", "milk"], text_type="query")
            self.assertEqual(len(results), 2)
            self.assertEqual(len(results[0]), 1024)
            # Verify unit norm: 3/5 = 0.6, 4/5 = 0.8
            self.assertAlmostEqual(results[0][0], 0.6, places=4)
            self.assertAlmostEqual(results[0][1], 0.8, places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
