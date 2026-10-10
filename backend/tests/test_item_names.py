"""
The bilingual product and category names of the merchant responses (app/services/item_names.py):
the helper itself, the three response schemas that carry its fields, and that every place in
merchant_v1.py that builds one of them uses the helper.

The helper needs nothing; the schema tests need pydantic (skipped without it). The schema modules
are loaded under a stand-in `app.schemas` package, so the package's __init__ (user schemas, which
need email-validator) is not executed.
"""

import ast
import importlib
import os
import sys
import types
import unittest
import uuid
from types import SimpleNamespace

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stub_modules import stubbed
from app.services.item_names import item_name_fields

try:
    import pydantic  # noqa: F401
    HAVE_PYDANTIC = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_PYDANTIC = False

FIELDS = ("name_ar", "name_en", "category_name_ar", "category_name_en")


def load_merchant_schemas():
    package = types.ModuleType("app.schemas")
    package.__path__ = [os.path.join(BACKEND, "app", "schemas")]
    modules = ("address", "merchant_v1")
    fresh = tuple(f"app.schemas.{name}" for name in modules)
    with stubbed({"app.schemas": package}, fresh=fresh):
        return importlib.import_module("app.schemas.merchant_v1")


def item(category=..., **own):
    """A GlobalItem stand-in. category=... means 'category_rel was not loaded'."""
    gi = SimpleNamespace(**own)
    if category is not ...:
        gi.category_rel = category
    return gi


class ItemNameFieldsTests(unittest.TestCase):
    def test_all_four_names(self):
        gi = item(
            name_ar="عسل سدر", name_en="Sidr Honey",
            category=SimpleNamespace(name="Spices & Sauces", name_ar="بهارات وصلصات", name_en="Spices & Sauces"),
        )
        self.assertEqual(item_name_fields(gi), {
            "name_ar": "عسل سدر", "name_en": "Sidr Honey",
            "category_name_ar": "بهارات وصلصات", "category_name_en": "Spices & Sauces",
        })

    def test_keys_are_exactly_the_four_schema_fields(self):
        self.assertEqual(tuple(item_name_fields(item(category=None))), FIELDS)

    def test_missing_and_blank_names_are_none_not_empty_strings(self):
        gi = item(name_ar="   ", name_en=None, category=SimpleNamespace(name_ar="", name_en=None))
        self.assertEqual(item_name_fields(gi), {f: None for f in FIELDS})

    def test_names_are_stripped(self):
        gi = item(name_ar=" شاي ", name_en="Tea\n", category=SimpleNamespace(name_ar=" مشروبات ", name_en=" Beverages"))
        fields = item_name_fields(gi)
        self.assertEqual((fields["name_ar"], fields["name_en"]), ("شاي", "Tea"))
        self.assertEqual((fields["category_name_ar"], fields["category_name_en"]), ("مشروبات", "Beverages"))

    def test_category_that_was_not_loaded_gives_none_and_never_loads_it(self):
        # Like GlobalItem.category: only what is already in the instance dict is read. A property that
        # would lazy-load (and fail in an async request) must not be touched.
        class Unloaded:
            name_ar = "عسل"
            name_en = None

            @property
            def category_rel(self):  # pragma: no cover - must not be called
                raise AssertionError("category_rel was accessed through the attribute, not the instance dict")

        fields = item_name_fields(Unloaded())
        self.assertEqual(fields["name_ar"], "عسل")
        self.assertIsNone(fields["category_name_ar"])
        self.assertIsNone(fields["category_name_en"])

    def test_item_without_a_category(self):
        gi = item(category=None, name_ar="a", name_en="b")
        self.assertEqual(item_name_fields(gi)["category_name_ar"], None)

    def test_non_string_values_are_ignored(self):
        gi = item(name_ar=5, name_en=b"x", category=SimpleNamespace(name_ar=["x"], name_en={}))
        self.assertEqual(item_name_fields(gi), {f: None for f in FIELDS})


@unittest.skipUnless(HAVE_PYDANTIC, "pydantic is not installed")
class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = load_merchant_schemas()

    def names(self):
        return item_name_fields(item(
            name_ar="عسل", name_en="Honey",
            category=SimpleNamespace(name_ar="بهارات وصلصات", name_en="Spices & Sauces"),
        ))

    def assert_names(self, dumped):
        self.assertEqual(dumped["name_ar"], "عسل")
        self.assertEqual(dumped["name_en"], "Honey")
        self.assertEqual(dumped["category_name_ar"], "بهارات وصلصات")
        self.assertEqual(dumped["category_name_en"], "Spices & Sauces")

    def test_barcode_lookup_response_carries_the_names(self):
        resp = self.schemas.BarcodeLookupResponse(
            exists_in_branch=False, global_item_id=uuid.uuid4(), name="Honey",
            category="Spices & Sauces", barcode="6281000000001", **self.names(),
        )
        self.assert_names(resp.model_dump())

    def test_catalog_item_match_carries_the_names(self):
        resp = self.schemas.CatalogItemMatch(id=uuid.uuid4(), name="Honey", **self.names())
        self.assert_names(resp.model_dump())

    def test_dashboard_response_carries_the_names(self):
        resp = self.schemas.MarketItemDashboardResponse(
            id=uuid.uuid4(), item_id=uuid.uuid4(), name="Honey", stock_count=3, in_stock=True, **self.names(),
        )
        self.assert_names(resp.model_dump())

    def test_names_are_optional_so_other_builders_keep_working(self):
        resp = self.schemas.CatalogItemMatch(id=uuid.uuid4(), name="Honey")
        self.assertEqual({f: resp.model_dump()[f] for f in FIELDS}, {f: None for f in FIELDS})


class BuildersUseTheHelperTests(unittest.TestCase):
    def test_every_builder_of_the_three_responses_passes_item_name_fields(self):
        # _dashboard_row (every dashboard row), POST /items/check and the barcode lookup. A builder that
        # forgets the helper would silently send no Arabic names again.
        with open(os.path.join(BACKEND, "app", "api", "merchant_v1.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        wanted = {"MarketItemDashboardResponse", "CatalogItemMatch", "BarcodeLookupResponse"}
        seen = {name: 0 for name in wanted}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in wanted):
                continue
            seen[node.func.id] += 1
            splatted = [
                kw.value for kw in node.keywords
                if kw.arg is None and isinstance(kw.value, ast.Call)
                and isinstance(kw.value.func, ast.Name) and kw.value.func.id == "item_name_fields"
            ]
            self.assertTrue(splatted, f"a {node.func.id}(...) call at line {node.lineno} lacks **item_name_fields(gi)")
        for name, count in seen.items():
            self.assertEqual(count, 1, f"expected one {name}(...) call in merchant_v1.py, found {count}")


if __name__ == "__main__":
    unittest.main()
