"""
Checks for migration 0004 (global_items.attributes_version) and the model column.

The migration is run against a recording stand-in for alembic's `op` (alembic itself is not needed);
the column type check needs SQLAlchemy and is skipped without it. The model is read as source, since
importing it needs the whole application stack.
"""

import ast
import importlib.util
import os
import sys
import types
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

try:
    import sqlalchemy as sa
    HAVE_SQLALCHEMY = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_SQLALCHEMY = False

VERSIONS = os.path.join(BACKEND, "alembic", "versions")
MIGRATION = os.path.join(VERSIONS, "0004_attributes_version.py")
MODEL = os.path.join(BACKEND, "app", "models", "global_item.py")


class RecordingOp:
    def __init__(self):
        self.calls = []

    def add_column(self, table, column):
        self.calls.append(("add_column", table, column))

    def drop_column(self, table, column_name):
        self.calls.append(("drop_column", table, column_name))


def load_migration(op):
    stub = types.ModuleType("alembic")
    stub.op = op
    saved = sys.modules.get("alembic")
    sys.modules["alembic"] = stub
    try:
        spec = importlib.util.spec_from_file_location("migration_0004_under_test", MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = saved
    return module


class TestAttributesVersionMigration(unittest.TestCase):
    def test_chain_continues_from_0003_and_is_a_single_head(self):
        revisions = {}
        for fname in os.listdir(VERSIONS):
            if not fname.endswith(".py"):
                continue
            values = {}
            with open(os.path.join(VERSIONS, fname), encoding="utf-8") as f:
                for node in ast.parse(f.read()).body:
                    target = node.target if isinstance(node, ast.AnnAssign) else None
                    if target is not None and getattr(target, "id", None) in ("revision", "down_revision"):
                        values[target.id] = ast.literal_eval(node.value)
            if "revision" in values:
                revisions[values["revision"]] = values.get("down_revision")
        self.assertEqual(revisions["0004"], "0003")
        parents = set(revisions.values())
        heads = [rev for rev in revisions if rev not in parents]
        self.assertEqual(heads, ["0004"])

    @unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
    def test_upgrade_adds_a_nullable_smallint_and_downgrade_drops_it(self):
        op = RecordingOp()
        migration = load_migration(op)
        migration.upgrade()
        ((kind, table, column),) = op.calls
        self.assertEqual((kind, table, column.name), ("add_column", "global_items", "attributes_version"))
        self.assertIsInstance(column.type, sa.SmallInteger)
        self.assertTrue(column.nullable)
        self.assertIsNone(column.server_default)  # NULL means "never processed"; no backfill
        op.calls.clear()
        migration.downgrade()
        self.assertEqual(op.calls, [("drop_column", "global_items", "attributes_version")])

    def test_model_declares_the_same_column(self):
        with open(MODEL, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        found = None
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "attributes_version":
                found = node
        self.assertIsNotNone(found, "GlobalItem.attributes_version is missing")
        call = found.value
        self.assertEqual(ast.unparse(call.args[0]), "SmallInteger")
        self.assertEqual({k.arg: ast.literal_eval(k.value) for k in call.keywords}, {"nullable": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
