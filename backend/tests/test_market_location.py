"""The lock policy for moving a store's location. Standard library only (no database)."""

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import market_location as ml

ARABIC_FIRST, ARABIC_LAST = chr(0x0600), chr(0x06FF)
LAT, LNG = 32.04, 35.73              # Salt
METRES_PER_DEGREE_LAT = 111194.9     # 6371008.8 m * pi / 180


def north_of(lat, metres):
    return lat + metres / METRES_PER_DEGREE_LAT


def market(**overrides):
    fields = dict(
        governorate="balqa", area="المدينة الرياضية", street="شارع الجامعة", landmark=None,
        address="شارع الجامعة، المدينة الرياضية، البلقاء",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def update(**overrides):
    fields = dict(
        latitude=LAT, longitude=LNG, governorate="balqa", area="المدينة الرياضية",
        street="شارع الجامعة", landmark=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestDistance(unittest.TestCase):
    def test_zero_for_the_same_point(self):
        self.assertEqual(ml.distance_m(LAT, LNG, LAT, LNG), 0.0)

    def test_one_degree_of_latitude(self):
        self.assertAlmostEqual(ml.distance_m(31.0, 35.0, 32.0, 35.0), METRES_PER_DEGREE_LAT, delta=1.0)

    def test_is_symmetric(self):
        a = ml.distance_m(31.95, 35.91, 32.04, 35.73)
        b = ml.distance_m(32.04, 35.73, 31.95, 35.91)
        self.assertAlmostEqual(a, b, places=6)

    def test_amman_to_salt_is_about_twenty_kilometres(self):
        d = ml.distance_m(31.95, 35.91, 32.04, 35.73)
        self.assertTrue(19_000 < d < 23_000, d)

    def test_a_longitude_degree_is_shorter_at_this_latitude(self):
        d = ml.distance_m(LAT, 35.0, LAT, 36.0)
        self.assertTrue(90_000 < d < 100_000, d)


class TestMovingThePin(unittest.TestCase):
    def test_a_small_move_is_allowed_and_recorded(self):
        m = market()
        change = ml.apply_location_update(m, LAT, LNG, update(latitude=north_of(LAT, 150)))
        self.assertTrue(change.changed)
        self.assertAlmostEqual(change.moved_m, 150, delta=1.0)
        self.assertEqual((change.old_latitude, change.old_longitude), (LAT, LNG))
        self.assertEqual(change.new_longitude, LNG)

    def test_just_under_the_limit_is_allowed(self):
        change = ml.apply_location_update(market(), LAT, LNG, update(latitude=north_of(LAT, 199)))
        self.assertTrue(change.changed)

    def test_just_over_the_limit_is_refused(self):
        m = market()
        with self.assertRaises(ml.LocationChangeRefused) as ctx:
            ml.apply_location_update(m, LAT, LNG, update(latitude=north_of(LAT, 201)))
        self.assertEqual(ctx.exception.reason, ml.REASON_PIN_TOO_FAR)
        self.assertAlmostEqual(ctx.exception.moved_m, 201, delta=1.0)

    def test_a_refusal_changes_nothing(self):
        m = market()
        before = dict(vars(m))
        with self.assertRaises(ml.LocationChangeRefused):
            ml.apply_location_update(
                m, LAT, LNG, update(latitude=north_of(LAT, 5000), area="مكان آخر", landmark="x"),
            )
        self.assertEqual(vars(m), before)

    def test_the_limit_is_200_metres(self):
        self.assertEqual(ml.FREE_MOVE_LIMIT_M, 200.0)


class TestEditingTheText(unittest.TestCase):
    def test_area_street_and_landmark_are_free_to_edit_without_moving(self):
        m = market()
        change = ml.apply_location_update(
            m, LAT, LNG, update(area="الجامعة", street=None, landmark="مقابل البنك"),
        )
        self.assertTrue(change.changed)
        self.assertEqual(change.moved_m, 0.0)
        self.assertEqual((m.area, m.street, m.landmark), ("الجامعة", None, "مقابل البنك"))
        self.assertEqual(m.address, "الجامعة، البلقاء")

    def test_the_old_and_new_fields_are_recorded(self):
        m = market()
        change = ml.apply_location_update(m, LAT, LNG, update(area="الجامعة", landmark="مقابل البنك"))
        self.assertEqual(
            change.old_fields,
            {"governorate": "balqa", "area": "المدينة الرياضية", "street": "شارع الجامعة", "landmark": None},
        )
        self.assertEqual(
            change.new_fields,
            {"governorate": "balqa", "area": "الجامعة", "street": "شارع الجامعة", "landmark": "مقابل البنك"},
        )

    def test_an_identical_request_is_not_a_change(self):
        m = market()
        before = dict(vars(m))
        change = ml.apply_location_update(m, LAT, LNG, update())
        self.assertFalse(change.changed)
        self.assertEqual(vars(m), before)

    def test_float_noise_in_the_pin_is_not_a_change(self):
        change = ml.apply_location_update(market(), LAT, LNG, update(latitude=LAT + 1e-12))
        self.assertFalse(change.changed)


class TestGovernorate(unittest.TestCase):
    def test_changing_a_set_governorate_is_refused_even_without_moving(self):
        m = market()
        with self.assertRaises(ml.LocationChangeRefused) as ctx:
            ml.apply_location_update(m, LAT, LNG, update(governorate="amman"))
        self.assertEqual(ctx.exception.reason, ml.REASON_GOVERNORATE_LOCKED)
        self.assertEqual(m.governorate, "balqa")

    def test_the_governorate_check_comes_first(self):
        with self.assertRaises(ml.LocationChangeRefused) as ctx:
            ml.apply_location_update(
                market(), LAT, LNG, update(governorate="amman", latitude=north_of(LAT, 5000)),
            )
        self.assertEqual(ctx.exception.reason, ml.REASON_GOVERNORATE_LOCKED)

    def test_setting_the_governorate_of_a_store_that_has_none_is_allowed(self):
        legacy = market(governorate=None, area=None, street=None, address="السلط")
        change = ml.apply_location_update(legacy, LAT, LNG, update(governorate="balqa", area="الجامعة", street=None))
        self.assertTrue(change.changed)
        self.assertEqual(legacy.governorate, "balqa")
        self.assertEqual(legacy.address, "الجامعة، البلقاء")

    def test_a_store_without_a_governorate_still_cannot_jump_far(self):
        legacy = market(governorate=None)
        with self.assertRaises(ml.LocationChangeRefused) as ctx:
            ml.apply_location_update(legacy, LAT, LNG, update(latitude=north_of(LAT, 1000)))
        self.assertEqual(ctx.exception.reason, ml.REASON_PIN_TOO_FAR)


class TestMessages(unittest.TestCase):
    def assert_bilingual(self, message):
        lines = message.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(any(ARABIC_FIRST <= c <= ARABIC_LAST for c in lines[0]))
        self.assertTrue(lines[1].isascii())
        self.assertIn(ml.SUPPORT_EMAIL, lines[0])
        self.assertIn(ml.SUPPORT_EMAIL, lines[1])

    def test_both_refusals_are_bilingual_and_point_to_support(self):
        self.assert_bilingual(ml.MSG_PIN_TOO_FAR)
        self.assert_bilingual(ml.MSG_GOVERNORATE_LOCKED)

    def test_the_pin_message_names_the_limit(self):
        self.assertIn("200", ml.MSG_PIN_TOO_FAR)

    def test_the_exception_carries_the_message(self):
        with self.assertRaises(ml.LocationChangeRefused) as ctx:
            ml.apply_location_update(market(), LAT, LNG, update(governorate="amman"))
        self.assertEqual(ctx.exception.message, ml.MSG_GOVERNORATE_LOCKED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
