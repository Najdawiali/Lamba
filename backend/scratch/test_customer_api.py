"""Unit tests for Customer V1 API endpoints, testing route functions directly with mocked database sessions."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
import uuid
from datetime import datetime, timezone

# Add backend directory to sys.path to allow imports of app
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.customer_v1 import get_near_markets, get_market_catalog
from app.models.market import Market
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.schemas.customer_v1 import NearMarketResponse, CustomerItemResponse


class TestCustomerV1API(unittest.IsolatedAsyncioTestCase):
    
    async def test_get_near_markets_success(self):
        """Test near-markets endpoint returning list of markets sorted by distance."""
        mock_db = AsyncMock()
        
        # Prepare mock return data for database query
        mock_market = Market(
            id=uuid.uuid4(),
            merchant_id=uuid.uuid4(),
            name="Near Shop",
            address="Near Street 123",
            created_at=datetime.now(timezone.utc)
        )
        # SQLAlchemy select returns rows (market, lat, lng, distance_km)
        mock_row = MagicMock()
        mock_row.__getitem__.side_effect = lambda idx: {
            0: mock_market,
            1: 24.7136,
            2: 46.6753,
            3: 1.25
        }[idx]
        
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_db.execute.return_value = mock_result
        
        # Invoke endpoint function
        response = await get_near_markets(
            latitude=24.7100,
            longitude=46.6700,
            radius_km=5.0,
            db=mock_db
        )
        
        # Verify db was queried
        self.assertTrue(mock_db.execute.called)
        
        # Verify response matches NearMarketResponse
        self.assertEqual(len(response), 1)
        self.assertIsInstance(response[0], NearMarketResponse)
        self.assertEqual(response[0].id, mock_market.id)
        self.assertEqual(response[0].name, "Near Shop")
        self.assertEqual(response[0].distance_km, 1.25)
        self.assertEqual(response[0].latitude, 24.7136)
        self.assertEqual(response[0].longitude, 46.6753)

    async def test_get_market_catalog_success(self):
        """Test market-catalog endpoint grouping active/in-stock products by category."""
        mock_db = AsyncMock()
        market_id = uuid.uuid4()
        
        # Mock market existence check
        mock_market_exists_result = MagicMock()
        mock_market_exists_result.scalar_one_or_none.return_value = Market(id=market_id)
        
        # Mock items query return
        item_id_1 = uuid.uuid4()
        market_item_id_1 = uuid.uuid4()
        gi_1 = GlobalItem(
            id=item_id_1,
            name="Matcha Green Tea",
            description="Premium organic matcha",
            category="Tea",
            image_url="/uploads/matcha.jpg"
        )
        mi_1 = MarketItem(
            id=market_item_id_1,
            market_id=market_id,
            item_id=item_id_1,
            stock_count=10,
            status=True
        )
        
        item_id_2 = uuid.uuid4()
        market_item_id_2 = uuid.uuid4()
        gi_2 = GlobalItem(
            id=item_id_2,
            name="Arabica Espresso",
            description="Dark roast espresso beans",
            category="Coffee",
            image_url="/uploads/coffee.jpg"
        )
        mi_2 = MarketItem(
            id=market_item_id_2,
            market_id=market_id,
            item_id=item_id_2,
            stock_count=5,
            status=True
        )

        item_id_3 = uuid.uuid4()
        market_item_id_3 = uuid.uuid4()
        gi_3 = GlobalItem(
            id=item_id_3,
            name="Wild Honey",
            description="Natural raw honey",
            category=None,  # Tests fallback category "Grocery"
            image_url=None
        )
        mi_3 = MarketItem(
            id=market_item_id_3,
            market_id=market_id,
            item_id=item_id_3,
            stock_count=8,
            status=True
        )
        
        # Mocking db execute results
        mock_items_result = MagicMock()
        mock_items_result.all.return_value = [
            (mi_1, gi_1),
            (mi_2, gi_2),
            (mi_3, gi_3)
        ]
        
        # db.execute side effect for: 1. check market exists, 2. fetch items
        mock_db.execute.side_effect = [mock_market_exists_result, mock_items_result]
        
        # Invoke endpoint function
        response = await get_market_catalog(market_id=market_id, db=mock_db)
        
        # Verify db was queried twice
        self.assertEqual(mock_db.execute.call_count, 2)
        
        # Verify response structure and categorization
        self.assertIn("Tea", response)
        self.assertIn("Coffee", response)
        self.assertIn("Grocery", response)  # Fallback
        
        self.assertEqual(len(response["Tea"]), 1)
        self.assertEqual(response["Tea"][0].name, "Matcha Green Tea")
        self.assertEqual(response["Tea"][0].id, item_id_1)
        self.assertEqual(response["Tea"][0].market_item_id, market_item_id_1)
        self.assertEqual(response["Tea"][0].stock_count, 10)
        self.assertTrue(response["Tea"][0].in_stock)
        
        self.assertEqual(len(response["Coffee"]), 1)
        self.assertEqual(response["Coffee"][0].name, "Arabica Espresso")
        
        self.assertEqual(len(response["Grocery"]), 1)
        self.assertEqual(response["Grocery"][0].name, "Wild Honey")
        self.assertEqual(response["Grocery"][0].category, "Grocery")


if __name__ == "__main__":
    unittest.main()
