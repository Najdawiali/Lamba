"""
Unit and integration tests for Merchant Market Profile & Employees API endpoints.
"""

import os
import sys
import unittest
import uuid
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import app
from app.api.auth import get_current_user
from app.models.user import User
from app.models.market import Market
from app.database import get_db


class TestMerchantMarketProfileAPI(unittest.IsolatedAsyncioTestCase):
    async def test_profile_endpoints_require_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/merchant/market/profile")
            self.assertEqual(res.status_code, 401)

            res = await client.patch(
                "/api/v1/merchant/market/profile",
                json={"contact_phone": "+962791112233"},
            )
            self.assertEqual(res.status_code, 401)

            res = await client.put(
                "/api/v1/merchant/market/employees",
                json={"employees": ["Staff A"]},
            )
            self.assertEqual(res.status_code, 401)

    async def test_profile_get_and_update_flows_with_auth(self):
        # Mock user & market
        user_id = uuid.uuid4()
        mock_user = User(
            id=user_id,
            email="merchant@test.com",
            user_type="merchant",
        )

        mock_market = Market(
            id=uuid.uuid4(),
            merchant_id=user_id,
            name="Original Market",
            address="Street 1",
            contact_phone=None,
            contact_email=None,
            employees=[],
            profile_edited_at=None,
            name_edited_at=None,
            address_edited_at=None,
        )

        # Mock DB session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_market
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. GET profile initially (unlocked for both name and address)
                res = await client.get("/api/v1/merchant/market/profile")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["name"], "Original Market")
                self.assertFalse(data["is_name_locked"])
                self.assertFalse(data["is_address_locked"])
                self.assertIsNone(data["name_edited_at"])
                self.assertIsNone(data["address_edited_at"])

                # 2. PATCH name only (first time) -> should succeed and lock name ONLY
                res = await client.patch(
                    "/api/v1/merchant/market/profile",
                    json={
                        "name": "Updated Name",
                        "contact_phone": "+962791234567",
                    },
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["name"], "Updated Name")
                self.assertEqual(data["contact_phone"], "+962791234567")
                self.assertTrue(data["is_name_locked"])
                self.assertFalse(data["is_address_locked"])
                self.assertIsNotNone(data["name_edited_at"])
                self.assertIsNone(data["address_edited_at"])

                # Ensure mock_market state updated
                mock_market.name = "Updated Name"
                mock_market.name_edited_at = datetime.now(timezone.utc)

                # 3. PATCH name second time -> must return 403 Forbidden
                res = await client.patch(
                    "/api/v1/merchant/market/profile",
                    json={"name": "Third Name"},
                )
                self.assertEqual(res.status_code, 403)
                self.assertIn("Store name can only be edited once", res.json()["detail"])

                # 4. PATCH address first time -> must SUCCEED because address is not locked yet
                res = await client.patch(
                    "/api/v1/merchant/market/profile",
                    json={"address": "New Location Street"},
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["address"], "New Location Street")
                self.assertTrue(data["is_name_locked"])
                self.assertTrue(data["is_address_locked"])
                self.assertIsNotNone(data["address_edited_at"])

                # Ensure mock_market state updated
                mock_market.address = "New Location Street"
                mock_market.address_edited_at = datetime.now(timezone.utc)

                # 5. PATCH address second time -> must return 403 Forbidden
                res = await client.patch(
                    "/api/v1/merchant/market/profile",
                    json={"address": "Another Address"},
                )
                self.assertEqual(res.status_code, 403)
                self.assertIn("Store address can only be edited once", res.json()["detail"])

                # 6. PATCH contact info only -> must SUCCEED even when both name & address are locked
                res = await client.patch(
                    "/api/v1/merchant/market/profile",
                    json={
                        "contact_phone": "0799998888",
                        "contact_email": "new.email@market.jo",
                    },
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["contact_phone"], "0799998888")
                self.assertEqual(data["contact_email"], "new.email@market.jo")
                self.assertTrue(data["is_name_locked"])
                self.assertTrue(data["is_address_locked"])

                # 7. PUT employees -> replaces employees list
                res = await client.put(
                    "/api/v1/merchant/market/employees",
                    json={"employees": ["Omar", "Lina", " Tariq "]},
                )
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual(data["employees"], ["Omar", "Lina", "Tariq"])

        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
