"""
Tests for app.services.attribute_rules. Pure functions: no network, no database.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.attribute_rules import (
    MAX_MATCH_VARIANTS,
    MAX_TEXT_LENGTH,
    canonical_enum_value,
    clean_text,
    coerce_bool,
    match_variants,
    plan_attribute_filters,
    sanitize_merchant_attributes,
    spelling_variants,
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
        self.assertEqual(canonical_enum_value("gender", "نساءي"), "female")  # alef/hamza-normalised spelling
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


class TestSpellingVariants(unittest.TestCase):
    def test_bare_alef_and_hamza_forms_find_each_other(self):
        self.assertEqual(set(spelling_variants("اخضر")), {"اخضر", "أخضر", "إخضر"})
        self.assertEqual(set(spelling_variants("أخضر")), {"أخضر", "اخضر", "إخضر"})
        self.assertEqual(set(spelling_variants("إيطالي")), {"إيطالي", "ايطالي", "أيطالي"})

    def test_hamza_carriers_are_put_back(self):
        self.assertEqual(set(spelling_variants("نساءي")), {"نساءي", "نسائي", "نساؤي"})
        self.assertIn("نساءي", spelling_variants("نسائي"))  # and the other way round

    def test_only_a_word_initial_alef_is_restored_and_never_the_article(self):
        self.assertEqual(spelling_variants("المراعي"), ("المراعي",))
        self.assertEqual(spelling_variants("سلطان"), ("سلطان",))  # a medial alef is a real alef
        self.assertIn("أبيض بلدي", spelling_variants("ابيض بلدي"))
        self.assertIn("الأخضر", spelling_variants("الاخضر"))      # the alef after the article is restored
        self.assertNotIn("ألخضر", spelling_variants("الاخضر"))

    def test_latin_and_case_are_not_duplicated(self):
        self.assertEqual(spelling_variants("Nestle"), ("Nestle",))
        self.assertEqual(spelling_variants("NESTLE"), ("NESTLE",))

    def test_match_variants_add_the_article_form_and_stay_bounded(self):
        variants = match_variants("اخضر")
        self.assertEqual(variants[0], "اخضر")
        for expected in ("أخضر", "الاخضر", "الأخضر"):
            self.assertIn(expected, variants)
        self.assertEqual(len(variants), len(set(v.lower() for v in variants)))
        self.assertLessEqual(len(match_variants("اب اب اب اب اب اب اب اب")), MAX_MATCH_VARIANTS)
        for blank in ("", "   "):
            self.assertNotIn("", [v.strip() for v in spelling_variants(blank)])


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

    def test_text_values_are_matched_with_and_without_the_article(self):
        (plan,) = plan_attribute_filters({"type": "أخضر"})
        self.assertEqual(plan.kind, "text")
        self.assertEqual(plan.variants[0], "أخضر")  # as given comes first
        self.assertIn("الأخضر", plan.variants)
        (plan,) = plan_attribute_filters({"type": "الأخضر"})
        self.assertEqual(plan.variants[0], "الأخضر")
        self.assertIn("أخضر", plan.variants)
        (plan,) = plan_attribute_filters({"type": "ال"})  # too short to strip
        self.assertEqual(plan.variants, ("ال",))

    def test_the_hamza_spelling_the_model_returns_matches_bare_alef_data_and_back(self):
        # A2b on the live server (2026-10-09): the query "شاي اخضر" reached the model alef-normalised and
        # it answered {'type': 'أخضر'}. Names and stored values may be spelled either way.
        (from_model,) = plan_attribute_filters({"type": "أخضر"})
        self.assertIn("اخضر", from_model.variants)      # matches a name written without the hamza
        (bare,) = plan_attribute_filters({"type": "اخضر"})
        self.assertIn("أخضر", bare.variants)            # matches a name written with the hamza
        self.assertIn("الأخضر", bare.variants)
        (brand,) = plan_attribute_filters({"brand": "اوكسجين"})
        self.assertIn("أوكسجين", brand.variants)

    def test_gender_written_the_normalised_way_is_still_understood(self):
        (plan,) = plan_attribute_filters({"gender": "نساءي"})
        self.assertEqual((plan.kind, plan.value), ("enum", "female"))

    def test_brand_is_its_own_kind(self):
        (plan,) = plan_attribute_filters({"brand": " المراعي "})
        self.assertEqual((plan.kind, plan.variants), ("brand", ("المراعي", "مراعي")))

    def test_several_filters_keep_their_order(self):
        plans = plan_attribute_filters({"type": "أخضر", "organic": True, "gender": "male"})
        self.assertEqual([p.key for p in plans], ["type", "organic", "gender"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
