"""
Tests for scripts/build_synonym_table.py: the synonym table is the curated CORE_SYNONYMS only.

The script is loaded from its real file with a fake Redis in place of app.services.cache, so no
Redis, database or network is involved.
"""

import ast
import asyncio
import contextlib
import importlib.util
import io
import os
import sys
import types
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from app.services.arabic_norm import normalize_arabic

SCRIPT = os.path.join(BACKEND, "scripts", "build_synonym_table.py")


class FakeRedis:
    def __init__(self, hashes=None):
        self.hashes = dict(hashes or {})
        self.deleted = []

    async def delete(self, key):
        self.deleted.append(key)
        self.hashes.pop(key, None)

    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)


def load_script(redis_client):
    """The real script module, with get_redis() returning `redis_client` (or raising it)."""
    stub = types.ModuleType("app.services.cache")

    async def get_redis():
        if isinstance(redis_client, Exception):
            raise redis_client
        return redis_client

    stub.get_redis = get_redis
    saved = sys.modules.get("app.services.cache")
    sys.modules["app.services.cache"] = stub
    try:
        spec = importlib.util.spec_from_file_location("build_synonym_table_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("app.services.cache", None)
        else:
            sys.modules["app.services.cache"] = saved
    return module


def run_build(module):
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(module.build_synonym_table())


class TestBuildSynonymTable(unittest.TestCase):
    def test_stores_exactly_the_normalised_core_synonyms(self):
        fake = FakeRedis()
        module = load_script(fake)
        returned = run_build(module)
        expected = {normalize_arabic(t): normalize_arabic(c) for t, c in module.CORE_SYNONYMS.items()}
        self.assertEqual(returned, expected)
        self.assertEqual(fake.hashes["lamba:synonyms"], expected)
        self.assertEqual(expected[normalize_arabic("جاج")], normalize_arabic("دجاج"))

    def test_replaces_whatever_was_in_the_hash(self):
        # entries mined from product search terms by the old script must disappear on the next run
        fake = FakeRedis({"lamba:synonyms": {"حلوم": "جبنة حلوم الجبل 500 غم", "جاج": "صدور دجاج مجمدة"}})
        module = load_script(fake)
        run_build(module)
        table = fake.hashes["lamba:synonyms"]
        self.assertEqual(fake.deleted, ["lamba:synonyms"])
        self.assertNotIn(normalize_arabic("حلوم"), table)
        self.assertEqual(table[normalize_arabic("جاج")], normalize_arabic("دجاج"))

    def test_nothing_is_read_from_the_database(self):
        with open(SCRIPT, encoding="utf-8") as f:
            source = f.read()
        imported, identifiers = set(), set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
        for module_name in imported:
            self.assertFalse(module_name.startswith(("app.database", "app.models", "sqlalchemy")), module_name)
        self.assertFalse(identifiers & {"GlobalItem", "async_session", "search_terms", "select"}, identifiers)

    def test_unreachable_redis_does_not_raise(self):
        module = load_script(ConnectionError("redis down"))
        returned = run_build(module)
        self.assertEqual(len(returned), len(module.CORE_SYNONYMS))

    def test_reembed_catalog_script_is_gone(self):
        # it rebuilt the table from catalog terms and embedded a different text than production
        self.assertFalse(os.path.exists(os.path.join(BACKEND, "scripts", "reembed_catalog.py")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
