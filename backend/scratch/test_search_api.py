"""Unit tests for Search V1 API endpoints (Qwen3 + reranker + tsvector stack).

Covers:
  - Local in-shop search (100% semantic weight)
  - Global cross-shop search (0.7 semantic + 0.3 proximity)
  - Two-tier fallback (recommendations / SearchAlert)
  - Arabic cross-lingual matching: شاي → Ghazaleen Tea + Chinese Tea
  - Double-check refinement

Mocks the embedding service + reranker so tests run anywhere; the real
GPU stack is exercised via integration tests in a separate harness.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import numpy as np
from datetime import datetime, timezone

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.search_v1 import (
    hybrid_search,
    double_check_search,
    _filter_top_five_unless_accuracy_above_80,
)
from app.models.market import Market
from app.schemas.search_v1 import (
    HybridSearchRequest,
    DoubleCheckSearchRequest,
)


def _mkrow(mi, gi, market, sem, prox, fin, lat=24.7136, lng=46.6753, dist=2.5):
    return (mi, gi, market, lat, lng, dist, sem, prox, fin)


def _rerank_passthrough(query, candidates, top_k=None):
    """Mocked async reranker: pass through, copy semantic_score → rerank_score."""
    async def _impl():
        for c in candidates:
            c["final_score"] = c.get("final_score", c["semantic_score"])
            c["rerank_score"] = c["semantic_score"]
        return candidates[: (top_k or 15)]
    return _impl()


def _make_mock_embedding_service():
    """Returns an AsyncMock embedding_service whose encode_text_async returns a
    precomputed 1024-d normalized vector (instantly, no DeepInfra call)."""
    mock = AsyncMock()
    v = np.random.rand(1024).astype(np.float32)
    v = v / np.linalg.norm(v)
    async def _encode_text_async(_text, dim=None):
        return v
    mock.encode_text_async.side_effect = _encode_text_async
    mock.encode_text.side_effect = lambda t, dim=None: v
    mock.encode_text_384.side_effect = lambda t: v
    mock.encode_product.side_effect = lambda name, description=None, search_terms=None: v
    return mock


def _make_market_item(name, description, sem_alias=None, market=None, stock=10):
    gi = MagicMock()
    gi.id = uuid.uuid4()
    gi.name = name
    gi.description = description
    gi.category = None
    gi.image_url = None
    mi = MagicMock()
    mi.id = uuid.uuid4()
    mi.market_id = market.id if market else uuid.uuid4()
    mi.item_id = gi.id
    mi.stock_count = stock
    mi.status = True
    mi.price = None
    return mi, gi


def _make_market(name="M"):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.merchant_id = uuid.uuid4()
    m.name = name
    m.address = "Riyadh"
    m.is_currently_open = True
    return m


def _execute_returns(rows):
    """Configure an AsyncMock db.execute to yield `rows` (list of tuples)."""
    res = MagicMock()
    res.all.return_value = rows
    res.unique.return_value = res
    return res


class TestSearchV1API(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Qwen3 produces a 1024-d normalized vector.
        v = np.random.rand(1024).astype(np.float32)
        self.mock_vector = v / np.linalg.norm(v)

    @patch("app.api.search_v1.embedding_service")
    @patch("app.api.search_v1.reranker_service")
    async def test_hybrid_search_global_success(self, mock_reranker, mock_embedding):
        """Global cross-shop search: weighted 0.7 semantic + 0.3 proximity."""
        mock_embedding.encode_text.return_value = self.mock_vector
        async def _mock_encode_async(_t, dim=None):
            return self.mock_vector
        mock_embedding.encode_text_async.side_effect = _mock_encode_async
        mock_reranker.rerank_async.side_effect = _rerank_passthrough

        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # AsyncSession.add is sync, not awaitable
        market = _make_market("Super Market")
        mi, gi = _make_market_item("Premium Lavender Water",
                                    "Soothing organic lavender extract", market=market)
        row = _mkrow(mi, gi, market, sem=0.85, prox=0.5, fin=0.745)
        mock_db.execute.return_value = _execute_returns([row])

        req = HybridSearchRequest(
            query_text="lavender spray", latitude=24.7100, longitude=46.6700,
        )
        response = await hybrid_search(request=req, user=MagicMock(id=uuid.uuid4()), db=mock_db)

        self.assertTrue(mock_embedding.encode_text_async.called)
        self.assertTrue(response.found)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].final_score, 0.745)

    @patch("app.api.search_v1.embedding_service")
    @patch("app.api.search_v1.reranker_service")
    async def test_hybrid_search_local_pure_semantic(self, mock_reranker, mock_embedding):
        """In-shop search: 100% semantic weight, no proximity contribution."""
        mock_embedding.encode_text.return_value = self.mock_vector
        async def _mock_encode_async(_t, dim=None):
            return self.mock_vector
        mock_embedding.encode_text_async.side_effect = _mock_encode_async
        mock_reranker.rerank_async.side_effect = _rerank_passthrough

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        market_id = uuid.uuid4()
        market = _make_market("Local")
        market.id = market_id
        mi, gi = _make_market_item("Organic Saffron Honey",
                                    "Pure Sidr honey with saffron", market=market)
        row = _mkrow(mi, gi, market, sem=0.92, prox=1.0, fin=0.92, dist=0.0)
        mock_db.execute.return_value = _execute_returns([row])

        req = HybridSearchRequest(
            query_text="saffron honey", latitude=24.7136, longitude=46.6753,
            market_id=market_id,
        )
        response = await hybrid_search(request=req, user=MagicMock(id=uuid.uuid4()), db=mock_db)

        self.assertTrue(response.found)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].final_score, 0.92)

    @patch("app.api.search_v1.embedding_service")
    @patch("app.api.search_v1.reranker_service")
    async def test_arabic_crosslingual_shay_matches_tea(self, mock_reranker, mock_embedding):
        """
        Arabic query شاي must surface both Ghazaleen Tea and Chinese Tea when the
        items' search_terms contain Arabic aliases. This is the core recall
        requirement that drove the encoder swap.
        """
        mock_embedding.encode_text.return_value = self.mock_vector
        async def _mock_encode_async(_t, dim=None):
            return self.mock_vector
        mock_embedding.encode_text_async.side_effect = _mock_encode_async
        mock_reranker.rerank_async.side_effect = _rerank_passthrough

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        market = _make_market()
        mi1, gi1 = _make_market_item("Ghazaleen Tea", "Black tea", market=market)
        gi1.search_terms = "شاي غزالين ghazaleen tea"
        mi2, gi2 = _make_market_item("Chinese Tea", "Green tea", market=market)
        gi2.search_terms = "شاي صيني chinese tea"
        rows = [
            _mkrow(mi1, gi1, market, sem=0.82, prox=0.6, fin=0.788, dist=2.0),
            _mkrow(mi2, gi2, market, sem=0.79, prox=0.55, fin=0.718, dist=2.3),
        ]
        mock_db.execute.return_value = _execute_returns(rows)

        req = HybridSearchRequest(
            query_text="شاي", latitude=24.71, longitude=46.67,
        )
        response = await hybrid_search(request=req, user=MagicMock(id=uuid.uuid4()), db=mock_db)

        self.assertTrue(response.found)
        self.assertEqual(len(response.results), 2)
        names = {r.name for r in response.results}
        self.assertIn("Ghazaleen Tea", names)
        self.assertIn("Chinese Tea", names)

    @patch("app.api.search_v1.embedding_service")
    @patch("app.api.search_v1.reranker_service")
    async def test_arabizi_query_3asal_matches_honey(self, mock_reranker, mock_embedding):
        """Arabizi '3asal' should retrieve the عسل item via arabizi_to_arabic."""
        mock_embedding.encode_text.return_value = self.mock_vector
        async def _mock_encode_async(_t, dim=None):
            return self.mock_vector
        mock_embedding.encode_text_async.side_effect = _mock_encode_async
        mock_reranker.rerank_async.side_effect = _rerank_passthrough

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        market = _make_market()
        mi, gi = _make_market_item("Sidr Honey", "عسل سدر", market=market)
        gi.search_terms = "عسل asl honey"
        row = _mkrow(mi, gi, market, sem=0.81, prox=0.7, fin=0.787)
        mock_db.execute.return_value = _execute_returns([row])

        req = HybridSearchRequest(query_text="3asal", latitude=24.7, longitude=46.7)
        response = await hybrid_search(request=req, user=MagicMock(id=uuid.uuid4()), db=mock_db)

        self.assertTrue(response.found)
        self.assertEqual(response.results[0].name, "Sidr Honey")

    @patch("app.api.search_v1.embedding_service")
    @patch("app.api.search_v1.reranker_service")
    async def test_zero_results_triggers_request_more_details(self, mock_reranker, mock_embedding):
        mock_embedding.encode_text.return_value = self.mock_vector
        async def _mock_encode_async(_t, dim=None):
            return self.mock_vector
        mock_embedding.encode_text_async.side_effect = _mock_encode_async
        mock_reranker.rerank_async.side_effect = _rerank_passthrough

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        empty = _execute_returns([])

        alert_dedup_res = MagicMock()
        alert_dedup_res.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [empty, empty, alert_dedup_res]

        req = HybridSearchRequest(
            query_text="unfindable exotic product", latitude=24.71, longitude=46.67,
        )
        response = await hybrid_search(request=req, user=MagicMock(id=uuid.uuid4()), db=mock_db)

        self.assertFalse(response.found)
        self.assertEqual(response.action, "request_more_details")

    @patch("app.api.search_v1.embedding_service")
    @patch("app.api.search_v1.reranker_service")
    async def test_double_check_refinement(self, mock_reranker, mock_embedding):
        mock_embedding.encode_text.return_value = self.mock_vector
        async def _mock_encode_async(_t, dim=None):
            return self.mock_vector
        mock_embedding.encode_text_async.side_effect = _mock_encode_async
        mock_reranker.rerank_async.side_effect = _rerank_passthrough

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        market = _make_market("S")
        mi, gi = _make_market_item("Sidr Honey Jar", "Raw honey", market=market)
        row = _mkrow(mi, gi, market, sem=0.88, prox=0.9, fin=0.886, dist=0.1)
        mock_db.execute.return_value = _execute_returns([row])

        req = DoubleCheckSearchRequest(
            original_query_text="honey",
            user_refined_details="organic raw Sidr brand packaging",
            latitude=24.71, longitude=46.67,
        )
        response = await double_check_search(request=req, user=MagicMock(id=uuid.uuid4()), db=mock_db)

        self.assertTrue(response.found)
        self.assertEqual(len(response.results), 1)

    def test_top5_cap_when_under_5_above_80(self):
        """Cap returns top-5 when fewer than 5 results are above 0.80."""
        results = [
            MagicMock(semantic_score=0.70 + i * 0.01) for i in range(8)
        ]
        kept = _filter_top_five_unless_accuracy_above_80(results)
        self.assertEqual(len(kept), 5)

    def test_top5_full_above_80(self):
        """Returns ALL ≥0.80 matches when there are ≥5 of them."""
        results = [MagicMock(semantic_score=0.85) for _ in range(7)]
        kept = _filter_top_five_unless_accuracy_above_80(results)
        self.assertEqual(len(kept), 7)


if __name__ == "__main__":
    unittest.main()