"""
Tests for public vs protected endpoints in Customer and Search APIs.
"""

import os
import sys
import unittest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.main import app


class TestCustomerAuth(unittest.IsolatedAsyncioTestCase):
    async def test_public_customer_endpoints_do_not_require_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. /categories should return 200 without token
            res = await client.get("/api/v1/customer/categories")
            self.assertNotEqual(res.status_code, 401)
            self.assertNotEqual(res.status_code, 403)
            self.assertEqual(res.status_code, 200)

            # 2. /near-markets should not return 401 or 403
            res = await client.get("/api/v1/customer/near-markets?latitude=32.0385&longitude=35.7275&radius_km=10")
            self.assertNotEqual(res.status_code, 401)
            self.assertNotEqual(res.status_code, 403)

            # 3. /offers should not return 401 or 403
            res = await client.get("/api/v1/customer/offers?latitude=32.0385&longitude=35.7275")
            self.assertNotEqual(res.status_code, 401)
            self.assertNotEqual(res.status_code, 403)

    async def test_protected_customer_endpoints_require_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # /alerts requires authentication -> should return 401
            res = await client.get("/api/v1/customer/alerts")
            self.assertEqual(res.status_code, 401)

            # /search-history requires authentication -> should return 401
            res = await client.get("/api/v1/customer/search-history")
            self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
