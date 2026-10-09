"""
Tests for app.services.category_match: the category the query model names must equal a taxonomy name.

The pure helpers run anywhere; the SQL clause is compiled for PostgreSQL when SQLAlchemy is installed.
The taxonomy test uses the real app/taxonomy.py and the category answers the production model really gave
on the server (2026-10-09), so it shows what now resolves and what is ignored.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.category_match import boost_matching_category, exact_category_clause, exact_name_forms
from app.taxonomy import CATEGORIES

try:
    from sqlalchemy import Column, MetaData, Table, Text
    from sqlalchemy.dialects import postgresql
    HAVE_SQLALCHEMY = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_SQLALCHEMY = False


def candidate(category, ar=None, en=None, score=1.0):
    return {"category": category, "category_name_ar": ar, "category_name_en": en, "rrf_score": score}


def resolves(answer):
    """Does this model answer equal a taxonomy name? (the SQL clause is the same comparison)"""
    wanted = answer.strip().lower()
    return any(wanted in exact_name_forms(c.name_ar, c.name_en) for c in CATEGORIES)


class TestExactNames(unittest.TestCase):
    def test_names_are_compared_stripped_and_lower_cased(self):
        self.assertEqual(exact_name_forms(" Personal Care ", "العناية الشخصية", None, "", "  ", 5), {"personal care", "العناية الشخصية"})
        self.assertEqual(exact_name_forms(), set())


class TestBoost(unittest.TestCase):
    def test_only_results_in_the_matched_category_are_boosted_by_exact_name(self):
        names = exact_name_forms("قهوة وشاي", "Coffee & Tea")
        fused = [
            candidate("Coffee & Tea", "قهوة وشاي", "Coffee & Tea", 1.0),
            candidate("قهوة وشاي", None, None, 2.0),
            candidate("Formula & Baby Food", "حليب وطعام أطفال", "Formula & Baby Food", 3.0),
            candidate(None, None, None, 4.0),
        ]
        self.assertEqual(boost_matching_category(fused, names), 2)
        self.assertEqual([c["rrf_score"] for c in fused], [1.5, 3.0, 3.0, 4.0])

    def test_a_loose_word_never_boosts_a_category_that_merely_contains_it(self):
        # the old substring test: "حليب" in "حليب وطعام أطفال" boosted the baby formula category
        fused = [candidate("Formula & Baby Food", "حليب وطعام أطفال", "Formula & Baby Food", 1.0)]
        self.assertEqual(boost_matching_category(fused, exact_name_forms("حليب")), 0)
        self.assertEqual(fused[0]["rrf_score"], 1.0)

    def test_case_and_the_factor(self):
        fused = [candidate("BEVERAGES", None, None, 2.0)]
        self.assertEqual(boost_matching_category(fused, exact_name_forms("beverages"), factor=2), 1)
        self.assertEqual(fused[0]["rrf_score"], 4.0)

    def test_nothing_to_match_changes_nothing(self):
        fused = [candidate("x", score=1.0)]
        self.assertEqual(boost_matching_category(fused, set()), 0)
        self.assertEqual(boost_matching_category([], {"x"}), 0)
        self.assertEqual(fused[0]["rrf_score"], 1.0)


class TestRealTaxonomy(unittest.TestCase):
    def test_what_the_production_model_answered_for_the_checked_queries(self):
        # Exact taxonomy names resolve (and a section brings its subcategories along: see the boost test).
        for answer in ("Beverages", "Personal Care", "beverages", " personal care "):
            self.assertTrue(resolves(answer), answer)
        # Loose, wrong-language or unrelated answers are ignored: search runs without a category.
        for answer in ("شاي", "حليب", "عطور", "زيت زيتون", "dairy", "perfumes", "الألبان والأجبان", ""):
            self.assertFalse(resolves(answer), answer)


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestClause(unittest.TestCase):
    def compile(self, name):
        categories = Table("categories", MetaData(), Column("name", Text), Column("name_ar", Text), Column("name_en", Text))
        clause = exact_category_clause(categories.c, name)
        compiled = clause.compile(dialect=postgresql.dialect())
        return str(compiled), compiled.params

    def test_equality_on_all_three_names_never_a_substring(self):
        sql, params = self.compile("  Beverages ")
        self.assertEqual(sql.count("lower("), 3)
        self.assertEqual(sql.count(" OR "), 2)
        self.assertNotIn("LIKE", sql.upper())
        self.assertEqual(set(params.values()), {"beverages"})
        for column in ("name", "name_ar", "name_en"):
            self.assertIn(f"lower(categories.{column}) = ", sql)


class TestSearchUsesIt(unittest.TestCase):
    """search_v1 cannot be imported without the whole stack; check its source."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "api", "search_v1.py")
        with open(path, encoding="utf-8") as f:
            cls.source = f.read()

    def test_no_fuzzy_category_matching_is_left(self):
        self.assertNotIn("Category.name.ilike", self.source)
        self.assertNotIn("Category.name_ar.ilike", self.source)
        self.assertNotIn("Category.name_en.ilike", self.source)
        self.assertNotIn("cat in item_cat", self.source)

    def test_the_exact_helpers_are_used(self):
        for needle in ("exact_category_clause(Category,", "boost_matching_category(fused, resolved_category_names)",
                       "exact_name_forms("):
            self.assertIn(needle, self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
