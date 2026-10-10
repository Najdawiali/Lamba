"""
Request/response schemas for the structured store address: creating a store, the location update,
the removed address fields, and the address parts customers receive.

Needs pydantic (skipped without it). The schema modules are loaded under a stand-in `app.schemas`
package, so the package's __init__ (user schemas, which need email-validator) is not executed.
"""

import importlib
import os
import sys
import types
import unittest
import uuid
from datetime import datetime, timezone

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stub_modules import stubbed

try:
    import pydantic
    from pydantic import ValidationError
    HAVE_PYDANTIC = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_PYDANTIC = False

MODULES = ("address", "merchant_v1", "market_profile", "customer_v1", "search_v1", "special_offer")


def load_schemas():
    package = types.ModuleType("app.schemas")
    package.__path__ = [os.path.join(BACKEND, "app", "schemas")]
    fresh = tuple(f"app.schemas.{name}" for name in MODULES)
    with stubbed({"app.schemas": package}, fresh=fresh):
        return {name: importlib.import_module(f"app.schemas.{name}") for name in MODULES}


SCHEMAS = load_schemas() if HAVE_PYDANTIC else {}

GOOD = dict(
    name="سوبرماركت القدس", latitude=32.04, longitude=35.73,
    governorate="balqa", area="المدينة الرياضية",
)


def errors_text(ctx):
    return " | ".join(str(e["msg"]) for e in ctx.exception.errors())


@unittest.skipUnless(HAVE_PYDANTIC, "pydantic is not installed")
class TestMarketCreate(unittest.TestCase):
    def create(self, **overrides):
        return SCHEMAS["merchant_v1"].MarketCreate(**{**GOOD, **overrides})

    def test_a_complete_request_is_accepted_and_cleaned(self):
        m = self.create(area="  المدينة   الرياضية ", street=" شارع الجامعة ", landmark="مقابل البنك")
        self.assertEqual(m.area, "المدينة الرياضية")
        self.assertEqual(m.street, "شارع الجامعة")
        self.assertEqual(m.landmark, "مقابل البنك")
        self.assertEqual(m.governorate, "balqa")

    def test_the_merchants_words_are_not_changed(self):
        m = self.create(area="Sport City", street="University St")
        self.assertEqual((m.area, m.street), ("Sport City", "University St"))

    def test_street_and_landmark_are_optional_and_blank_becomes_none(self):
        m = self.create()
        self.assertEqual((m.street, m.landmark), (None, None))
        m = self.create(street="   ", landmark="")
        self.assertEqual((m.street, m.landmark), (None, None))

    def test_governorate_is_normalised_to_its_key(self):
        self.assertEqual(self.create(governorate=" Amman ").governorate, "amman")

    def test_an_unknown_governorate_is_rejected(self):
        for bad in ("As-Salt", "البلقاء", "", "gaza"):
            with self.assertRaises(ValidationError, msg=bad):
                self.create(governorate=bad)

    def test_governorate_and_area_are_required(self):
        payload = dict(GOOD)
        del payload["governorate"]
        with self.assertRaises(ValidationError):
            SCHEMAS["merchant_v1"].MarketCreate(**payload)
        payload = dict(GOOD)
        del payload["area"]
        with self.assertRaises(ValidationError):
            SCHEMAS["merchant_v1"].MarketCreate(**payload)

    def test_a_blank_area_is_rejected(self):
        for blank in ("", "   ", "\n"):
            with self.assertRaises(ValidationError, msg=repr(blank)) as ctx:
                self.create(area=blank)
            self.assertIn("Area is required", errors_text(ctx))

    def test_length_limits(self):
        self.create(area="ا" * 120, street="ش" * 160, landmark="م" * 200)
        for field, too_long in (("area", 121), ("street", 161), ("landmark", 201)):
            with self.assertRaises(ValidationError, msg=field):
                self.create(**{field: "x" * too_long})

    def test_extra_spaces_do_not_count_against_the_limit(self):
        self.assertEqual(len(self.create(area=("ا" * 60 + "   ") + "ب" * 59).area), 120)

    def test_a_pin_outside_jordan_is_rejected_with_a_bilingual_message(self):
        places = {"origin": (0.0, 0.0), "swapped": (35.73, 32.04), "Cairo": (30.04, 31.23), "Paris": (48.85, 2.35)}
        for name, (lat, lng) in places.items():
            with self.assertRaises(ValidationError, msg=name) as ctx:
                self.create(latitude=lat, longitude=lng)
            self.assertIn("must be inside Jordan", errors_text(ctx))
            self.assertIn("داخل الأردن", errors_text(ctx))

    def test_not_a_number_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.create(latitude=float("nan"))

    def test_a_legacy_address_only_request_is_rejected(self):
        with self.assertRaises(ValidationError):
            SCHEMAS["merchant_v1"].MarketCreate(
                name="Old", address="Amman, Jordan", latitude=31.95, longitude=35.91,
            )

    def test_an_address_sent_next_to_the_parts_is_ignored(self):
        m = self.create(address="whatever the client composed")
        self.assertFalse(hasattr(m, "address"))

    def test_the_other_fields_are_unchanged(self):
        m = self.create(phone="0791234567", business_nature="Bakery", is_currently_open=False)
        self.assertEqual((m.phone, m.business_nature, m.is_currently_open), ("0791234567", "Bakery", False))
        self.assertEqual(self.create().is_currently_open, True)


@unittest.skipUnless(HAVE_PYDANTIC, "pydantic is not installed")
class TestMarketLocationUpdate(unittest.TestCase):
    def update(self, **overrides):
        payload = {k: v for k, v in GOOD.items() if k != "name"}
        return SCHEMAS["merchant_v1"].MarketLocationUpdate(**{**payload, **overrides})

    def test_it_is_the_same_location_fields_without_a_name(self):
        u = self.update(street="شارع الجامعة", landmark=None)
        self.assertEqual((u.latitude, u.longitude, u.governorate, u.area, u.street, u.landmark),
                         (32.04, 35.73, "balqa", "المدينة الرياضية", "شارع الجامعة", None))
        self.assertNotIn("name", type(u).model_fields)

    def test_it_applies_the_same_rules(self):
        with self.assertRaises(ValidationError):
            self.update(latitude=0.0, longitude=0.0)
        with self.assertRaises(ValidationError):
            self.update(governorate="nowhere")
        with self.assertRaises(ValidationError):
            self.update(area=" ")


@unittest.skipUnless(HAVE_PYDANTIC, "pydantic is not installed")
class TestRemovedAddressFields(unittest.TestCase):
    def test_profile_update_no_longer_takes_an_address(self):
        update = SCHEMAS["market_profile"].MarketProfileUpdate(name="X", address="somewhere", address_ar="مكان")
        self.assertEqual(update.model_dump(exclude_unset=True), {"name": "X"})

    def test_profile_responses_have_no_address_or_address_lock_fields(self):
        for model in (SCHEMAS["market_profile"].MarketProfileResponse, SCHEMAS["merchant_v1"].MarketResponse):
            for gone in ("address_ar", "address_edited_at", "is_address_locked", "is_profile_locked"):
                self.assertNotIn(gone, model.model_fields, f"{model.__name__}.{gone}")
        self.assertNotIn("address", SCHEMAS["market_profile"].MarketProfileResponse.model_fields)

    def test_market_response_carries_the_structured_address(self):
        now = datetime.now(timezone.utc)
        resp = SCHEMAS["merchant_v1"].MarketResponse(
            id=uuid.uuid4(), merchant_id=uuid.uuid4(), name="My Store", address="شارع الجامعة، البلقاء",
            governorate="balqa", area="المدينة الرياضية", street="شارع الجامعة", landmark="مقابل البنك",
            latitude=32.04, longitude=35.73, is_currently_open=True, is_manual_override=False, created_at=now,
        )
        self.assertEqual((resp.governorate, resp.area, resp.street, resp.landmark),
                         ("balqa", "المدينة الرياضية", "شارع الجامعة", "مقابل البنك"))

    def test_a_row_without_structure_still_serialises(self):
        now = datetime.now(timezone.utc)
        resp = SCHEMAS["merchant_v1"].MarketResponse(
            id=uuid.uuid4(), merchant_id=uuid.uuid4(), name="Old", address="Amman",
            latitude=31.95, longitude=35.91, is_currently_open=True, is_manual_override=False, created_at=now,
        )
        self.assertEqual((resp.governorate, resp.area, resp.street, resp.landmark), (None, None, None, None))


@unittest.skipUnless(HAVE_PYDANTIC, "pydantic is not installed")
class TestCustomerAddressParts(unittest.TestCase):
    PARTS = {"governorate": "balqa", "area": "المدينة الرياضية", "street": None, "landmark": "مقابل البنك"}

    def test_address_parts_model(self):
        parts = SCHEMAS["address"].AddressParts(**self.PARTS)
        self.assertEqual(parts.model_dump(), self.PARTS)
        self.assertEqual(SCHEMAS["address"].AddressParts().model_dump(),
                         {"governorate": None, "area": None, "street": None, "landmark": None})

    def test_near_market_response(self):
        now = datetime.now(timezone.utc)
        base = dict(
            id=uuid.uuid4(), merchant_id=uuid.uuid4(), name="S", address="x", latitude=32.0, longitude=35.7,
            distance_km=1.0, is_currently_open=True, is_manual_override=False, created_at=now,
        )
        with_parts = SCHEMAS["customer_v1"].NearMarketResponse(**base, address_parts=self.PARTS)
        self.assertEqual(with_parts.address_parts.area, "المدينة الرياضية")
        self.assertIsNone(SCHEMAS["customer_v1"].NearMarketResponse(**base).address_parts)

    def test_shop_details(self):
        fields = SCHEMAS["customer_v1"].ShopDetails.model_fields
        self.assertIn("address_parts", fields)
        self.assertFalse(fields["address_parts"].is_required())

    def test_search_result_item(self):
        fields = SCHEMAS["search_v1"].HybridSearchResultItem.model_fields
        self.assertIn("market_address_parts", fields)
        self.assertFalse(fields["market_address_parts"].is_required())

    def test_special_offer_response(self):
        fields = SCHEMAS["special_offer"].CustomerSpecialOfferResponse.model_fields
        self.assertIn("shop_address_parts", fields)
        self.assertFalse(fields["shop_address_parts"].is_required())

    def test_a_dict_from_address_parts_of_validates_into_the_model(self):
        from app.jordan_geo import address_parts_of
        from types import SimpleNamespace
        row = SimpleNamespace(governorate="amman", area="عبدون", street=None, landmark=None)
        model = SCHEMAS["address"].AddressParts(**address_parts_of(row))
        self.assertEqual(model.governorate, "amman")


if __name__ == "__main__":
    unittest.main(verbosity=2)
