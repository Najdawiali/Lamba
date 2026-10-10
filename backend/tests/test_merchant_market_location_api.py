"""
HTTP-level tests for creating a store with a structured address and for PUT /market/location
(the lock policy, the audit row, the responses). Same style as test_merchant_market_profile_api.py:
the real app, with the database and the signed-in user replaced by mocks.

Needs the full backend dependencies (it imports app.main). The rules themselves are also covered
without them in test_market_location.py, and the schemas in test_store_location_schemas.py.
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
from app.models.market_location_change import MarketLocationChange
from app.database import get_db

LAT, LNG = 32.04, 35.73              # Salt
METRES_PER_DEGREE_LAT = 111194.9


def north_of(lat, metres):
    return lat + metres / METRES_PER_DEGREE_LAT


def location_body(**overrides):
    body = dict(
        latitude=LAT, longitude=LNG, governorate="balqa", area="المدينة الرياضية",
        street="شارع الجامعة", landmark=None,
    )
    body.update(overrides)
    return body


class LocationApiCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=uuid.uuid4(), email="merchant@test.com", user_type="merchant")
        self.market = Market(
            id=uuid.uuid4(), merchant_id=self.user.id, name="My Store",
            address="شارع الجامعة، المدينة الرياضية، البلقاء",
            governorate="balqa", area="المدينة الرياضية", street="شارع الجامعة", landmark=None,
            employees=[], is_currently_open=True, is_manual_override=False,
            created_at=datetime.now(timezone.utc),
        )
        self.db = AsyncMock()
        self.db.add = MagicMock()  # Session.add is synchronous
        result = MagicMock()
        result.first.return_value = (self.market, LAT, LNG)
        result.scalar_one_or_none.return_value = None
        self.db.execute.return_value = result
        self.result = result
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.clear()

    def client(self):
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestUpdateLocation(LocationApiCase):
    async def test_requires_auth(self):
        app.dependency_overrides.clear()
        async with self.client() as client:
            res = await client.put("/api/v1/merchant/market/location", json=location_body())
        self.assertEqual(res.status_code, 401)

    async def test_a_customer_is_refused(self):
        self.user.user_type = "customer"
        async with self.client() as client:
            res = await client.put("/api/v1/merchant/market/location", json=location_body())
        self.assertEqual(res.status_code, 403)
        self.db.commit.assert_not_awaited()

    async def test_no_market_is_404(self):
        self.result.first.return_value = None
        async with self.client() as client:
            res = await client.put("/api/v1/merchant/market/location", json=location_body())
        self.assertEqual(res.status_code, 404)

    async def test_a_small_move_and_new_text_are_accepted_and_logged(self):
        body = location_body(latitude=north_of(LAT, 150), area="الجامعة", street=None, landmark="مقابل البنك")
        async with self.client() as client:
            res = await client.put("/api/v1/merchant/market/location", json=body)
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertAlmostEqual(data["latitude"], body["latitude"])
        self.assertEqual(data["longitude"], LNG)
        self.assertEqual((data["governorate"], data["area"], data["street"], data["landmark"]),
                         ("balqa", "الجامعة", None, "مقابل البنك"))
        self.assertEqual(data["address"], "الجامعة، البلقاء")
        for gone in ("address_ar", "is_address_locked", "is_profile_locked", "address_edited_at"):
            self.assertNotIn(gone, data)

        self.db.commit.assert_awaited_once()
        ((logged,), _) = self.db.add.call_args
        self.assertIsInstance(logged, MarketLocationChange)
        self.assertEqual((logged.market_id, logged.user_id), (self.market.id, self.user.id))
        self.assertEqual((logged.old_latitude, logged.old_longitude), (LAT, LNG))
        self.assertAlmostEqual(logged.new_latitude, body["latitude"])
        self.assertAlmostEqual(logged.moved_m, 150, delta=1.0)
        self.assertEqual(logged.old_fields["area"], "المدينة الرياضية")
        self.assertEqual(logged.new_fields["landmark"], "مقابل البنك")
        self.assertIsNotNone(self.market.address_edited_at)

    async def test_editing_only_the_text_is_free_and_logged(self):
        async with self.client() as client:
            res = await client.put("/api/v1/merchant/market/location", json=location_body(landmark="قرب الدوار"))
        self.assertEqual(res.status_code, 200, res.text)
        ((logged,), _) = self.db.add.call_args
        self.assertEqual(logged.moved_m, 0.0)

    async def test_a_big_move_goes_through_support(self):
        async with self.client() as client:
            res = await client.put(
                "/api/v1/merchant/market/location", json=location_body(latitude=north_of(LAT, 1000)),
            )
        self.assertEqual(res.status_code, 403)
        detail = res.json()["detail"]
        self.assertIn("support@lambajo.com", detail)
        self.assertEqual(len(detail.split("\n")), 2)  # Arabic line, English line
        self.db.add.assert_not_called()
        self.db.commit.assert_not_awaited()
        self.assertEqual(self.market.street, "شارع الجامعة")

    async def test_a_different_governorate_goes_through_support(self):
        async with self.client() as client:
            res = await client.put("/api/v1/merchant/market/location", json=location_body(governorate="amman"))
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.market.governorate, "balqa")
        self.db.add.assert_not_called()

    async def test_the_same_location_again_changes_and_logs_nothing(self):
        async with self.client() as client:
            res = await client.put("/api/v1/merchant/market/location", json=location_body())
        self.assertEqual(res.status_code, 200)
        self.db.add.assert_not_called()
        self.db.commit.assert_not_awaited()

    async def test_a_pin_outside_jordan_is_rejected_before_anything_happens(self):
        async with self.client() as client:
            res = await client.put(
                "/api/v1/merchant/market/location", json=location_body(latitude=0.0, longitude=0.0),
            )
        self.assertEqual(res.status_code, 422)
        self.db.execute.assert_not_awaited()

    async def test_an_unknown_governorate_or_blank_area_is_rejected(self):
        async with self.client() as client:
            for bad in (location_body(governorate="As-Salt"), location_body(area="  ")):
                res = await client.put("/api/v1/merchant/market/location", json=bad)
                self.assertEqual(res.status_code, 422)


class TestCreateStore(LocationApiCase):
    async def test_a_store_is_created_with_the_structured_address_and_a_composed_line(self):
        added = []
        self.db.add.side_effect = added.append

        async def fake_flush():  # what the database would fill in
            added[0].id = uuid.uuid4()
            added[0].created_at = datetime.now(timezone.utc)
            added[0].is_manual_override = False
            added[0].employees = []

        self.db.flush.side_effect = fake_flush
        body = dict(
            name="سوبرماركت القدس", latitude=LAT, longitude=LNG, governorate="balqa",
            area="المدينة الرياضية", street="شارع الجامعة", landmark="مقابل البنك",
        )
        async with self.client() as client:
            res = await client.post("/api/v1/merchant/market", json=body)
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertEqual(data["address"], "شارع الجامعة، المدينة الرياضية، البلقاء")
        self.assertEqual((data["governorate"], data["area"], data["street"], data["landmark"]),
                         ("balqa", "المدينة الرياضية", "شارع الجامعة", "مقابل البنك"))
        self.assertEqual((data["latitude"], data["longitude"]), (LAT, LNG))
        self.assertTrue(data["access_token"])
        (market,) = added
        self.assertEqual((market.governorate, market.area, market.street, market.landmark),
                         ("balqa", "المدينة الرياضية", "شارع الجامعة", "مقابل البنك"))

    async def test_a_pin_outside_jordan_or_missing_parts_are_rejected(self):
        good = dict(name="Store", latitude=LAT, longitude=LNG, governorate="balqa", area="الجامعة")
        bad_bodies = [
            {**good, "latitude": 0.0, "longitude": 0.0},
            {**good, "latitude": LNG, "longitude": LAT},  # swapped
            {k: v for k, v in good.items() if k != "governorate"},
            {k: v for k, v in good.items() if k != "area"},
            {"name": "Store", "address": "Amman, Jordan", "latitude": 31.95, "longitude": 35.91},  # old shape
        ]
        async with self.client() as client:
            for body in bad_bodies:
                res = await client.post("/api/v1/merchant/market", json=body)
                self.assertEqual(res.status_code, 422, body)
        self.db.add.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
