"""
Tests for app.services.attribute_filters: the SQL the attribute filters compile to.

Needs only SQLAlchemy (no database): the clauses are compiled for PostgreSQL and inspected. The
tests are skipped when SQLAlchemy is not installed. What they cannot show is how Postgres runs
the SQL; they show that no CAST can raise and that gender is matched exactly.
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from sqlalchemy import Text, column, table
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import JSONB

    from app.services.attribute_filters import build_attribute_clauses
    from app.services.attribute_rules import plan_attribute_filters
    HAVE_SQLALCHEMY = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_SQLALCHEMY = False

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def compile_filters(extracted_attrs):
    """[(sql text, bound params)] for each clause the attrs produce."""
    items = table(
        "global_items",
        column("attributes", JSONB), column("name", Text), column("name_ar", Text), column("search_terms", Text),
    )
    clauses = build_attribute_clauses(
        plan_attribute_filters(extracted_attrs),
        attributes=items.c.attributes, name=items.c.name,
        name_ar=items.c.name_ar, search_terms=items.c.search_terms,
    )
    out = []
    for clause in clauses:
        compiled = clause.compile(dialect=postgresql.dialect())
        out.append((str(compiled), compiled.params))
    return out


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestAttributeFilters(unittest.TestCase):
    def test_boolean_uses_containment_not_a_cast(self):
        ((sql, params),) = compile_filters({"organic": True})
        # Compiles to: global_items.attributes @> %(attributes_1)s::JSONB. The ::JSONB casts the
        # bound parameter (our own JSON), never the stored column, so odd stored data cannot raise.
        self.assertIn("@>", sql)
        self.assertNotIn("BOOLEAN", sql.upper())
        self.assertNotIn("CAST", sql.upper())
        self.assertNotIn("->", sql)
        self.assertNotIn("ILIKE", sql.upper())
        self.assertEqual(list(params.values()), [{"organic": True}])

    def test_boolean_false_is_containment_too(self):
        ((sql, params),) = compile_filters({"organic": False})
        self.assertIn("@>", sql)
        self.assertEqual(list(params.values()), [{"organic": False}])

    def test_gender_is_an_exact_value_and_never_a_substring_of_another(self):
        ((sql, params),) = compile_filters({"gender": "male"})
        self.assertIn("@>", sql)
        values = list(params.values())
        self.assertIn({"gender": "male"}, values)
        self.assertNotIn({"gender": "female"}, values)
        # the old filter was ILIKE '%male%', which also matches the stored value 'female'
        self.assertNotIn("%male%", values)
        self.assertNotIn("->", sql)

    def test_female_query_never_asks_for_male(self):
        ((sql, params),) = compile_filters({"gender": "female"})
        values = list(params.values())
        self.assertIn({"gender": "female"}, values)
        self.assertNotIn({"gender": "male"}, values)

    def test_gender_name_fallback_uses_whole_arabic_words(self):
        ((sql, params),) = compile_filters({"gender": "نسائي"})
        values = list(params.values())
        self.assertIn({"gender": "female"}, values)
        self.assertIn("%نسائي%", values)
        self.assertIn("ILIKE", sql.upper())

    def test_temperature_cold_also_finds_iced(self):
        ((sql, params),) = compile_filters({"temperature": "cold"})
        values = list(params.values())
        self.assertIn({"temperature": "cold"}, values)
        self.assertIn({"temperature": "iced"}, values)

    def test_text_keys_keep_the_substring_match_and_name_fallback(self):
        ((sql, params),) = compile_filters({"type": "أخضر"})
        self.assertIn("ILIKE", sql.upper())
        self.assertIn("global_items.name", sql)
        self.assertIn("global_items.name_ar", sql)
        self.assertNotIn("search_terms", sql)
        values = list(params.values())
        for pattern in ("%أخضر%", "%الأخضر%"):
            self.assertIn(pattern, values)
        self.assertIn("type", values)

    def test_brand_also_looks_in_search_terms(self):
        ((sql, params),) = compile_filters({"brand": "مرسيدس"})
        self.assertIn("search_terms", sql)
        self.assertIn("%مرسيدس%", list(params.values()))
        self.assertIn("brand", list(params.values()))

    def test_unusable_attributes_add_no_clause(self):
        self.assertEqual(compile_filters({"organic": "عادي", "size": 500, "gender": "robot"}), [])
        self.assertEqual(compile_filters(None), [])

    def test_one_clause_per_attribute(self):
        self.assertEqual(len(compile_filters({"type": "أخضر", "organic": True, "gender": "male"})), 3)


class TestSearchUsesTheSharedFilters(unittest.TestCase):
    """search_v1 cannot be imported without the whole stack; check its source instead."""

    def test_search_no_longer_casts_attributes_to_boolean(self):
        path = os.path.join(BACKEND, "app", "api", "search_v1.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)  # also proves the file still parses
        self.assertNotIn("sa.Boolean", source)
        self.assertNotIn("Boolean", source)
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("plan_attribute_filters", called)
        self.assertIn("build_attribute_clauses", called)

    def test_merchant_upload_sanitises_attributes_before_saving(self):
        path = os.path.join(BACKEND, "app", "api", "merchant_v1.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("sanitize_merchant_attributes", called)
        # the sanitised value, not the raw client JSON, is what GlobalItem(...) receives
        self.assertIn("attributes=parsed_attributes", source)
        self.assertLess(source.index("sanitize_merchant_attributes(parsed_attributes)"),
                        source.index("attributes=parsed_attributes"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
