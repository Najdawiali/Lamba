"""Jordan geography helpers: governorates, the bounding box, address text. Standard library only."""

import math
import os
import re
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import jordan_geo as geo

ARABIC_FIRST, ARABIC_LAST = chr(0x0600), chr(0x06FF)


class TestGovernorates(unittest.TestCase):
    def test_there_are_twelve_with_unique_keys_and_names(self):
        self.assertEqual(len(geo.GOVERNORATES), 12)
        self.assertEqual(len({g.key for g in geo.GOVERNORATES}), 12)
        self.assertEqual(len({g.name_ar for g in geo.GOVERNORATES}), 12)
        self.assertEqual(len({g.name_en for g in geo.GOVERNORATES}), 12)

    def test_keys_are_plain_lowercase_ascii(self):
        for g in geo.GOVERNORATES:
            self.assertRegex(g.key, r"^[a-z]+$")
            self.assertLessEqual(len(g.key), 20)  # markets.governorate is VARCHAR(20)

    def test_arabic_names_are_arabic_and_english_names_are_not(self):
        for g in geo.GOVERNORATES:
            self.assertTrue(all(ARABIC_FIRST <= c <= ARABIC_LAST or c == " " for c in g.name_ar), g.key)
            self.assertTrue(g.name_en.isascii(), g.key)

    def test_the_expected_governorates_are_present(self):
        self.assertEqual(
            geo.GOVERNORATE_KEYS,
            {"amman", "irbid", "zarqa", "balqa", "madaba", "karak",
             "tafilah", "maan", "aqaba", "mafraq", "jerash", "ajloun"},
        )

    def test_normalize_governorate(self):
        self.assertEqual(geo.normalize_governorate("balqa"), "balqa")
        self.assertEqual(geo.normalize_governorate("  Balqa "), "balqa")
        self.assertIsNone(geo.normalize_governorate("As-Salt"))
        self.assertIsNone(geo.normalize_governorate("البلقاء"))
        self.assertIsNone(geo.normalize_governorate(""))
        self.assertIsNone(geo.normalize_governorate(None))

    def test_governorate_name_ar(self):
        self.assertEqual(geo.governorate_name_ar("balqa"), "البلقاء")
        self.assertIsNone(geo.governorate_name_ar("nowhere"))
        self.assertIsNone(geo.governorate_name_ar(None))


class TestBoundingBox(unittest.TestCase):
    def test_places_in_jordan_are_inside(self):
        places = {
            "Amman": (31.95, 35.91),
            "Salt": (32.04, 35.73),
            "Irbid": (32.55, 35.85),
            "Aqaba": (29.53, 35.01),
            "Mafraq east": (32.35, 38.20),
            "Jerash": (32.28, 35.90),
        }
        for name, (lat, lng) in places.items():
            self.assertTrue(geo.in_jordan_bbox(lat, lng), name)

    def test_places_far_away_are_outside(self):
        self.assertFalse(geo.in_jordan_bbox(0.0, 0.0))
        self.assertFalse(geo.in_jordan_bbox(30.04, 31.23))   # Cairo
        self.assertFalse(geo.in_jordan_bbox(24.71, 46.67))   # Riyadh
        self.assertFalse(geo.in_jordan_bbox(48.85, 2.35))    # Paris

    def test_swapped_latitude_and_longitude_are_caught(self):
        self.assertTrue(geo.in_jordan_bbox(31.95, 35.91))
        self.assertFalse(geo.in_jordan_bbox(35.91, 31.95))

    def test_not_a_number_and_infinity_are_outside(self):
        self.assertFalse(geo.in_jordan_bbox(math.nan, 35.9))
        self.assertFalse(geo.in_jordan_bbox(31.9, math.inf))
        self.assertFalse(geo.in_jordan_bbox(-math.inf, 35.9))

    def test_the_edges_are_inside(self):
        self.assertTrue(geo.in_jordan_bbox(geo.JORDAN_MIN_LAT, geo.JORDAN_MIN_LNG))
        self.assertTrue(geo.in_jordan_bbox(geo.JORDAN_MAX_LAT, geo.JORDAN_MAX_LNG))
        self.assertFalse(geo.in_jordan_bbox(geo.JORDAN_MAX_LAT + 0.001, 35.9))
        self.assertFalse(geo.in_jordan_bbox(31.9, geo.JORDAN_MIN_LNG - 0.001))


class TestAddressText(unittest.TestCase):
    def test_clean_text_trims_and_collapses_but_keeps_the_words(self):
        self.assertEqual(geo.clean_text("  شارع   الجامعة \n"), "شارع الجامعة")
        self.assertEqual(geo.clean_text("Sport  City"), "Sport City")
        self.assertIsNone(geo.clean_text("   "))
        self.assertIsNone(geo.clean_text(""))
        self.assertIsNone(geo.clean_text(None))

    def test_compose_address_street_area_governorate_with_the_arabic_comma(self):
        self.assertEqual(
            geo.compose_address("balqa", "المدينة الرياضية", "شارع الجامعة"),
            "شارع الجامعة، المدينة الرياضية، البلقاء",
        )

    def test_compose_address_without_a_street(self):
        self.assertEqual(geo.compose_address("amman", "عبدون", None), "عبدون، عمان")
        self.assertEqual(geo.compose_address("amman", "عبدون", "  "), "عبدون، عمان")

    def test_compose_address_keeps_the_merchants_own_language(self):
        self.assertEqual(
            geo.compose_address("balqa", "Sport City", "University St"),
            "University St، Sport City، البلقاء",
        )

    def test_compose_address_ignores_an_unknown_governorate(self):
        self.assertEqual(geo.compose_address("nowhere", "عبدون", None), "عبدون")
        self.assertEqual(geo.compose_address(None, "عبدون", None), "عبدون")

    def test_landmark_is_not_part_of_the_composed_address(self):
        self.assertNotIn("مسجد", geo.compose_address("amman", "عبدون", None))

    def test_address_parts_of_returns_the_four_fields(self):
        market = SimpleNamespace(governorate="amman", area="عبدون", street=None, landmark="قرب المسجد")
        self.assertEqual(
            geo.address_parts_of(market),
            {"governorate": "amman", "area": "عبدون", "street": None, "landmark": "قرب المسجد"},
        )

    def test_address_parts_of_is_none_for_a_row_without_structure(self):
        legacy = SimpleNamespace(governorate=None, area=None, street=None, landmark=None)
        self.assertIsNone(geo.address_parts_of(legacy))
        self.assertIsNone(geo.address_parts_of(SimpleNamespace()))  # attributes missing altogether


MOBILE_ADDRESS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mobile", "utils", "jordanAddress.ts"
)


class TestMobileMirror(unittest.TestCase):
    """mobile/utils/jordanAddress.ts repeats the keys, names, box and limits; they must not drift."""

    @classmethod
    def setUpClass(cls):
        with open(MOBILE_ADDRESS, encoding="utf-8") as f:
            cls.source = f.read()

    def number(self, pattern):
        match = re.search(pattern, self.source)
        self.assertIsNotNone(match, pattern)
        return float(match.group(1))

    def test_governorates_match_key_by_key(self):
        pattern = r"key: '([a-z]+)', ar: '([^']+)', en: (?:\"([^\"]+)\"|'([^']+)')"
        mobile = [(k, ar, en_double or en_single) for k, ar, en_double, en_single in re.findall(pattern, self.source)]
        backend = [(g.key, g.name_ar, g.name_en) for g in geo.GOVERNORATES]
        self.assertEqual(mobile, backend)

    def test_bounding_box_matches(self):
        self.assertEqual(self.number(r"minLat: ([0-9.]+)"), geo.JORDAN_MIN_LAT)
        self.assertEqual(self.number(r"maxLat: ([0-9.]+)"), geo.JORDAN_MAX_LAT)
        self.assertEqual(self.number(r"minLng: ([0-9.]+)"), geo.JORDAN_MIN_LNG)
        self.assertEqual(self.number(r"maxLng: ([0-9.]+)"), geo.JORDAN_MAX_LNG)

    def test_text_limits_match(self):
        self.assertEqual(self.number(r"AREA_MAX_LENGTH = ([0-9]+)"), geo.AREA_MAX_LENGTH)
        self.assertEqual(self.number(r"STREET_MAX_LENGTH = ([0-9]+)"), geo.STREET_MAX_LENGTH)
        self.assertEqual(self.number(r"LANDMARK_MAX_LENGTH = ([0-9]+)"), geo.LANDMARK_MAX_LENGTH)

    def test_the_free_move_limit_matches_the_policy(self):
        from app.services.market_location import FREE_MOVE_LIMIT_M
        self.assertEqual(self.number(r"FREE_MOVE_LIMIT_M = ([0-9]+)"), FREE_MOVE_LIMIT_M)


if __name__ == "__main__":
    unittest.main(verbosity=2)
