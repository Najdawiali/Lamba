"""Unit tests for Search V1 API endpoints, testing route functions directly with mocked embedding and database sessions."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import numpy as np
from datetime import datetime, timezone

# Add backend directory to sys.path to allow imports of app
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.search_v1 import hybrid_search, double_check_search
from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.schemas.search_v1 import (
    HybridSearchRequest,
    DoubleCheckSearchRequest,
    HybridSearchResponse,
    HybridSearchResultItem,
)


class TestSearchV1API(unittest.IsolatedAsyncioTestCase):
    
    def setUp(self):
        # Create a mock 384-dimensional vector
        self.mock_vector = np.random.rand(384).astype(np.float32)
        
    @patch("app.api.search_v1.embedding_service")
    async def test_hybrid_search_global_success(self, mock_embedding_service):
        """Test hybrid search globally across all shops with weighted scoring."""
        # 1. Mock embedding service to return a fixed vector
        mock_embedding_service.encode_text_384.return_value = self.mock_vector
        
        # 2. Prepare mock database rows
        mock_db = AsyncMock()
        mock_market = Market(
            id=uuid.uuid4(),
            merchant_id=uuid.uuid4(),
            name="Super Market",
            address="Olaya Riyadh",
            created_at=datetime.now(timezone.utc)
        )
        mock_global_item = GlobalItem(
            id=uuid.uuid4(),
            name="Premium Lavender Water",
            description="Soothing organic lavender extract",
            category="Spices",
            image_url="/uploads/lavender.jpg"
        )
        mock_market_item = MarketItem(
            id=uuid.uuid4(),
            market_id=mock_market.id,
            item_id=mock_global_item.id,
            stock_count=12,
            status=True
        )
        
        # Plain tuple for clean unpacking in _execute_hybrid_query
        mock_row = (
            mock_market_item,
            mock_global_item,
            mock_market,
            24.7136,
            46.6753,
            2.5,        # distance_km
            0.85,       # semantic_score
            0.5,        # proximity_score (1.0 - 2.5 / 5.0)
            0.745       # final_score (0.7 * 0.85 + 0.3 * 0.5)
        )
        
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db.execute.return_value = mock_result
        
        # 3. Build request
        req = HybridSearchRequest(
            query_text="lavender spray",
            latitude=24.7100,
            longitude=46.6700,
            market_id=None  # Global
        )
        
        # 4. Invoke endpoint
        response = await hybrid_search(request=req, db=mock_db)
        
        # 5. Assertions
        mock_embedding_service.encode_text_384.assert_called_once_with("lavender spray")
        self.assertTrue(mock_db.execute.called)
        self.assertTrue(response.found)
        self.assertIsNone(response.action)
        self.assertEqual(len(response.results), 1)
        
        result_item = response.results[0]
        self.assertEqual(result_item.item_id, mock_global_item.id)
        self.assertEqual(result_item.market_item_id, mock_market_item.id)
        self.assertEqual(result_item.market_name, "Super Market")
        self.assertEqual(result_item.distance_km, 2.5)
        self.assertEqual(result_item.semantic_score, 0.85)
        self.assertEqual(result_item.proximity_score, 0.5)
        self.assertEqual(result_item.final_score, 0.745)

    @patch("app.api.search_v1.embedding_service")
    async def test_hybrid_search_local_success(self, mock_embedding_service):
        """Test local shop search using pure 100% semantic score weight."""
        mock_embedding_service.encode_text_384.return_value = self.mock_vector
        mock_db = AsyncMock()
        market_id = uuid.uuid4()
        
        mock_market = Market(
            id=market_id,
            merchant_id=uuid.uuid4(),
            name="Local Shop Only",
            address="Exit 5 Riyadh",
            created_at=datetime.now(timezone.utc)
        )
        mock_global_item = GlobalItem(
            id=uuid.uuid4(),
            name="Organic Saffron Honey",
            description="Pure Sidr honey with organic saffron threads",
            category="Honey"
        )
        mock_market_item = MarketItem(
            id=uuid.uuid4(),
            market_id=market_id,
            item_id=mock_global_item.id,
            stock_count=5,
            status=True
        )
        
        mock_row = (
            mock_market_item,
            mock_global_item,
            mock_market,
            24.7136,
            46.6753,
            0.0,
            0.92,       # semantic_score
            1.0,
            0.92        # pure semantic final_score
        )
        
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db.execute.return_value = mock_result
        
        req = HybridSearchRequest(
            query_text="saffron honey",
            latitude=24.7136,
            longitude=46.6753,
            market_id=market_id
        )
        
        response = await hybrid_search(request=req, db=mock_db)
        
        self.assertTrue(response.found)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].final_score, 0.92)  # Matches pure semantic_score

    @patch("app.api.search_v1.embedding_service")
    async def test_hybrid_search_empty_details_trigger(self, mock_embedding_service):
        """Test zero-result empty trigger state requesting details from mobile app UI."""
        mock_embedding_service.encode_text_384.return_value = self.mock_vector
        mock_db = AsyncMock()
        
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No matches
        mock_db.execute.return_value = mock_result
        
        req = HybridSearchRequest(
            query_text="unfindable exotic product",
            latitude=24.7100,
            longitude=46.6700
        )
        
        response = await hybrid_search(request=req, db=mock_db)
        
        self.assertFalse(response.found)
        self.assertEqual(response.action, "request_more_details")
        self.assertEqual(len(response.results), 0)

    @patch("app.api.search_v1.embedding_service")
    async def test_double_check_search_success(self, mock_embedding_service):
        """Test secondary fallback double-check search using concatenated refined parameters."""
        mock_embedding_service.encode_text_384.return_value = self.mock_vector
        mock_db = AsyncMock()
        
        mock_market = Market(id=uuid.uuid4(), merchant_id=uuid.uuid4(), name="Shop", address="A")
        mock_gi = GlobalItem(id=uuid.uuid4(), name="Sidr Honey Jar", description="Raw honey")
        mock_mi = MarketItem(id=uuid.uuid4(), market_id=mock_market.id, item_id=mock_gi.id, stock_count=5, status=True)
        
        mock_row = (
            mock_mi,
            mock_gi,
            mock_market,
            24.7,
            46.7,
            0.1,
            0.88,
            0.9,
            0.886
        )
        
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db.execute.return_value = mock_result
        
        req = DoubleCheckSearchRequest(
            original_query_text="honey",
            user_refined_details="organic raw Sidr brand packaging",
            latitude=24.7100,
            longitude=46.6700
        )
        
        response = await double_check_search(request=req, db=mock_db)
        
        # Verify text concatenation logic
        mock_embedding_service.encode_text_384.assert_called_once_with("honey organic raw Sidr brand packaging")
        self.assertTrue(response.found)
        self.assertEqual(len(response.results), 1)


if __name__ == "__main__":
    unittest.main()
