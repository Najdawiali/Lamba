"""
Unit and integration tests for Merchant Offers API endpoints.
"""

import os
import sys
import unittest
import uuid
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import app
from app.api.auth import get_current_user
from app.models.user import User
from app.models.market import Market
from app.models.market_item import MarketItem
from app.models.global_item import GlobalItem
from app.models.offer import Offer
from app.database import get_db


class TestMerchantOffersAPI(unittest.IsolatedAsyncioTestCase):
    async def test_merchant_offers_endpoints_require_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/merchant/offers")
            self.assertEqual(res.status_code, 401)

            res = await client.post(
                "/api/v1/merchant/offers",
                json={
                    "market_item_id": str(uuid.uuid4()),
                    "offer_type": "percentage",
                    "config": {"percent": 20},
                },
            )
            self.assertEqual(res.status_code, 401)

            res = await client.patch(
                f"/api/v1/merchant/offers/{uuid.uuid4()}",
                json={"is_active": False},
            )
            self.assertEqual(res.status_code, 401)

            res = await client.delete(f"/api/v1/merchant/offers/{uuid.uuid4()}")
            self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
