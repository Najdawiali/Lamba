"""
Tests for app.services.attribute_rules. Pure functions: no network, no database.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.attribute_rules import (
    MAX_TEXT_LENGTH,
    canonical_enum_value,
    clean_text,
    coerce_bool,
    plan_attribute_filters,
    sanitize_merchant_attributes,
)


class TestSanitizeMerchantAttributes(unittest.TestCase):
    def test_what_the_add_product_form_sends_passes_unchanged(self):
        self.assertEqual(
            sanitize_merchant_attributes({"stock_status": "available"}),
            {"stock_status": "available"},
        )
        service = {"gender": "female", "appointment_required": True, "home_service_available": False}
        self.assertEqual(sanitize_merchant_attributes(service), service)

    def test_booleans_must_be_real_booleans(self):
        # The old search filter cast these to a boolean in SQL: "x" was a database error.
        for bad in ("x", "true", "yes", 1, 0, None, [], {}):
            self.assertEqual(sanitize_merchant_attributes({"organic": bad}), {}, repr(bad))
            self.assertEqual(sanitize_merchant_attributes({"appointment_required": bad}), {}, repr(bad))
        self.assertEqual(sanitize_merchant_attributes({"organic": False}), {"organic": False})

    def test_unknown_and_internal_keys_are_dropped(self):
        raw = {"gender": "male", "is_admin": True, "_attr_v": 1, "attributes_version": 1, "price": 5}
        self.assertEqual(sanitize_merchant_attributes(raw), {"gender": "male"})

    def test_enums_are_canonicalised_or_dropped(self):
        self.assertEqual(sanitize_merchant_attributes({"gender": " Female "}), {"gender": "female"})
        self.assertEqual(sanitize_merchant_attributes({"gender": "نسائي"}), {"gender": "female"})
        self.assertEqual(sanitize_merchant_attributes({"temperature": "بارد"}), {"temperature": "cold"})
        for bad in ("robot", "", 3, True, None):
            self.assertEqual(sanitize_merchant_attributes({"gender": bad}), {}, repr(bad))

    def test_text_values_are_short_single_line_strings(self):
        self.assertEqual(sanitize_merchant_attributes({"brand": "  المراعي \n"}), {"brand": "المراعي"})
        self.assertEqual(sanitize_merchant_attributes({"brand": "a\nb\tc"}), {"brand": "a b c"})
        for bad in ("", "   ", "x" * (MAX_TEXT_LENGTH + 1), 5, True, ["a"], {"a": 1}):
            self.assertEqual(sanitize_merchant_attributes({"brand": bad}), {}, repr(bad))
        self.assertEqual(sanitize_merchant_attributes({"brand": "x" * MAX_TEXT_LENGTH}), {"brand": "x" * MAX_TEXT_LENGTH})

    def test_anything_that_is_not_an_object_becomes_empty(self):
        for raw in (None, [], "text", 5, True, [{"gender": "male"}]):
            self.assertEqual(sanitize_merchant_attributes(raw), {}, repr(raw))
        self.assertEqual(sanitize_merchant_attributes({}), {})


class TestAttributeRuleHelpers(unittest.TestCase):
    def test_canonical_enum_value(self):
        self.assertEqual(canonical_enum_value("gender", "MALE"), "male")
        self.assertEqual(canonical_enum_value("gender", "رجالي"), "male")
        self.assertEqual(canonical_enum_value("gender", "any"), "any")
        self.assertEqual(canonical_enum_value("temperature", "ساخن"), "hot")
        self.assertEqual(canonical_enum_value("temperature", "iced"), "iced")
        self.assertIsNone(canonical_enum_value("gender", "hot"))
        self.assertIsNone(canonical_enum_value("brand", "male"))     # not an enum key
        self.assertIsNone(canonical_enum_value("gender", None))
        self.assertIsNone(canonical_enum_value("gender", 1))

    def test_coerce_bool(self):
        for value in (True, "true", " Yes ", "1", "نعم", "عضوي"):
            self.assertIs(coerce_bool(value), True, repr(value))
        for value in (False, "false", "NO", "0", "لا"):
            self.assertIs(coerce_bool(value), False, repr(value))
        for value in (1, 0, None, "maybe", "", [], {}):
            self.assertIsNone(coerce_bool(value), repr(value))

    def test_clean_text(self):
        self.assertEqual(clean_text("  أخضر  "), "أخضر")
        self.assertIsNone(clean_text(""))
        self.assertIsNone(clean_text(None))


class TestPlanAttributeFilters(unittest.TestCase):
    def test_a_boolean_becomes_a_boolean_filter(self):
        (plan,) = plan_attribute_filters({"organic": True})
        self.assertEqual((plan.kind, plan.key, plan.value), ("bool", "organic", True))

    def test_a_yes_word_for_a_boolean_key_is_understood(self):
        (plan,) = plan_attribute_filters({"organic": "true"})
        self.assertEqual((plan.kind, plan.value), ("bool", True))
        (plan,) = plan_attribute_filters({"organic": "لا"})
        self.assertEqual((plan.kind, plan.value), ("bool", False))

    def test_junk_is_skipped_so_the_search_only_gets_wider(self):
        junk = {
            "organic": "عادي",          # not a yes/no word
            "dietary": True,            # a boolean for a text key
            "size": 500,                # a number
            "color": ["أحمر"],          # a list
            "type": "   ",              # empty
            "flavor": None,
            "price": "5",               # not a search key
            "gender": "robot",          # not an enum value
        }
        self.assertEqual(plan_attribute_filters(junk), [])
        self.assertEqual(plan_attribute_filters(None), [])
        self.assertEqual(plan_attribute_filters("organic"), [])

    def test_male_never_matches_female(self):
        male, = plan_attribute_filters({"gender": "male"})
        female, = plan_attribute_filters({"gender": "female"})
        self.assertEqual(male.stored, ("male",))
        self.assertEqual(female.stored, ("female",))
        # no name word of one gender is a substring of a word of the other
        for m in male.name_words:
            for f in female.name_words:
                self.assertNotIn(m, f)
                self.assertNotIn(f, m)

    def test_arabic_gender_from_the_query_model_is_canonicalised(self):
        (plan,) = plan_attribute_filters({"gender": "نسائي"})
        self.assertEqual((plan.kind, plan.value, plan.stored), ("enum", "female", ("female",)))
        self.assertIn("نسائي", plan.name_words)

    def test_cold_and_iced_find_each_other(self):
        cold, = plan_attribute_filters({"temperature": "cold"})
        iced, = plan_attribute_filters({"temperature": "iced"})
        hot, = plan_attribute_filters({"temperature": "hot"})
        self.assertEqual(set(cold.stored), {"cold", "iced"})
        self.assertEqual(set(iced.stored), {"cold", "iced"})
        self.assertEqual(hot.stored, ("hot",))

    def test_text_values_get_the_al_variant_both_ways(self):
        (plan,) = plan_attribute_filters({"type": "أخضر"})
        self.assertEqual((plan.kind, plan.variants), ("text", ("أخضر", "الأخضر")))
        (plan,) = plan_attribute_filters({"type": "الأخضر"})
        self.assertEqual(plan.variants, ("الأخضر", "أخضر"))
        (plan,) = plan_attribute_filters({"type": "ال"})  # too short to strip
        self.assertEqual(plan.variants, ("ال",))

    def test_brand_is_its_own_kind(self):
        (plan,) = plan_attribute_filters({"brand": " المراعي "})
        self.assertEqual((plan.kind, plan.variants), ("brand", ("المراعي", "مراعي")))

    def test_several_filters_keep_their_order(self):
        plans = plan_attribute_filters({"type": "أخضر", "organic": True, "gender": "male"})
        self.assertEqual([p.key for p in plans], ["type", "organic", "gender"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
