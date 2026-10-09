"""
Tests for app.services.query_attributes: rule-based attributes from a search query.
Pure functions: no network, no database.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.arabic_norm import normalize_arabic, normalize_query
from app.services.attribute_rules import plan_attribute_filters
from app.services.query_attributes import extract_query_attributes, merge_attributes


def attrs(query):
    return extract_query_attributes(query)


class TestQueryAttributes(unittest.TestCase):
    def test_the_queries_checked_on_the_production_model(self):
        # What the model returned on the server on 2026-10-09 for these queries (all four reliable keys).
        expected = {
            "شاي أخضر": {},                                     # type is the model's job, not a rule's
            "حليب قليل الدسم": {"dietary": "قليل الدسم"},
            "زيت زيتون عضوي": {"organic": True},
            "عطر نسائي": {"gender": "female"},
            "قهوة باردة": {"temperature": "cold"},
            "جبنة بيضاء بلدية": {},
            "iced tea": {"temperature": "iced"},
            "مزيل عرق رجالي": {"gender": "male"},
        }
        for query, want in expected.items():
            self.assertEqual(attrs(query), want, query)
            # search passes the alef/hamza-normalised query
            self.assertEqual(attrs(normalize_query(query)), want, normalize_query(query))

    def test_articles_and_feminine_endings_are_understood(self):
        self.assertEqual(attrs("القهوة الباردة"), {"temperature": "cold"})
        self.assertEqual(attrs("شوكولاتة عضوية"), {"organic": True})
        self.assertEqual(attrs("حقيبة نسائية"), {"gender": "female"})
        self.assertEqual(attrs("ملابس للرجال"), {"gender": "male"})
        self.assertEqual(attrs("ساعة للنساء"), {"gender": "female"})
        self.assertEqual(attrs("شاي مثلج"), {"temperature": "iced"})
        self.assertEqual(attrs("قهوة ساخنة"), {"temperature": "hot"})
        self.assertEqual(attrs("حلاقة رجالة"), {"gender": "male"})   # colloquial "men"
        self.assertEqual(attrs("شاي وقهوة باردة"), {"temperature": "cold"})

    def test_english_words(self):
        self.assertEqual(attrs("Men's watch"), {"gender": "male"})
        self.assertEqual(attrs("women perfume"), {"gender": "female"})   # "men" inside "women" is not male
        self.assertEqual(attrs("organic honey"), {"organic": True})
        self.assertEqual(attrs("sugar free cola"), {"dietary": "بدون سكر"})
        self.assertEqual(attrs("Coca-Cola Zero"), {"dietary": "بدون سكر"})
        self.assertEqual(attrs("gluten free pasta"), {"dietary": "خالي من الغلوتين"})
        self.assertEqual(attrs("cold brew"), {"temperature": "cold"})

    def test_several_keys_at_once(self):
        self.assertEqual(
            attrs("عصير برتقال عضوي بدون سكر بارد"),
            {"organic": True, "dietary": "بدون سكر", "temperature": "cold"},
        )

    def test_words_are_matched_as_whole_tokens_never_as_substrings(self):
        self.assertEqual(attrs("مسخن دجاج"), {})        # the dish, not "hot" (سخن)
        self.assertEqual(attrs("سخان مياه"), {})        # a water heater
        self.assertEqual(attrs("Spider Man"), {})
        self.assertEqual(attrs("biscuit"), {})
        self.assertEqual(attrs("Bio Oil"), {})          # "bio" can be a brand
        self.assertEqual(attrs("ice cream"), {})
        self.assertEqual(attrs("hot sauce"), {})        # hot = spicy in English
        self.assertEqual(attrs("صلصة حارة"), {})        # حار is spicy, not a temperature

    def test_contradicting_words_produce_no_value_for_that_key(self):
        self.assertEqual(attrs("ملابس رجالي ونسائي"), {})
        self.assertEqual(attrs("ملابس للرجال والنساء"), {})   # "and the women": conjunction + article
        self.assertEqual(attrs("ملابس رجالي ونسائي"), {})
        self.assertEqual(attrs("مكيف ساخن بارد"), {})
        self.assertEqual(attrs("عطر للجنسين"), {})
        self.assertEqual(attrs("حليب قليل الدسم كامل الدسم"), {})
        # a conflict in one key does not hide the others
        self.assertEqual(attrs("عضوي رجالي ونسائي"), {"organic": True})

    def test_negated_organic_is_not_organic(self):
        self.assertEqual(attrs("غير عضوي"), {})
        self.assertEqual(attrs("non organic"), {})
        self.assertEqual(attrs("ليس عضوي"), {})

    def test_cold_and_iced_together_mean_cold(self):
        self.assertEqual(attrs("قهوة باردة مثلجة"), {"temperature": "cold"})

    def test_empty_input(self):
        for query in (None, "", "   "):
            self.assertEqual(attrs(query), {})

    def test_every_value_the_rules_produce_is_a_valid_search_filter(self):
        queries = ["زيت عضوي", "عطر نسائي", "عطر رجالي", "قهوة باردة", "شاي مثلج", "قهوة ساخنة", "حليب قليل الدسم"]
        for query in queries:
            found = attrs(query)
            plans = plan_attribute_filters(found)
            self.assertEqual(len(plans), len(found), (query, found))

    def test_the_rules_win_over_the_model_for_their_keys_and_keep_everything_else(self):
        merged = merge_attributes({"gender": "male", "type": "أخضر", "organic": False}, {"gender": "female", "organic": True})
        self.assertEqual(merged, {"gender": "female", "type": "أخضر", "organic": True})
        self.assertEqual(merge_attributes(None, {"organic": True}), {"organic": True})
        self.assertEqual(merge_attributes({"type": "أخضر"}, None), {"type": "أخضر"})
        self.assertEqual(merge_attributes(None, None), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
