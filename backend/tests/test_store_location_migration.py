"""
Checks for migration 0005 (structured store address + location change log) and the models.

The migration is run against a recording stand-in for alembic's `op`; the column checks need
SQLAlchemy and are skipped without it. The models are read as source, since importing them needs
the whole application stack.
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
    from sqlalchemy.dialects import postgresql
    HAVE_SQLALCHEMY = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_SQLALCHEMY = False

VERSIONS = os.path.join(BACKEND, "alembic", "versions")
MIGRATION = os.path.join(VERSIONS, "0005_store_structured_address.py")
MARKET_MODEL = os.path.join(BACKEND, "app", "models", "market.py")
CHANGE_MODEL = os.path.join(BACKEND, "app", "models", "market_location_change.py")
MODELS_INIT = os.path.join(BACKEND, "app", "models", "__init__.py")


class RecordingOp:
    def __init__(self):
        self.calls = []

    def f(self, name):
        return name

    def add_column(self, table, column):
        self.calls.append(("add_column", table, column))

    def drop_column(self, table, column_name):
        self.calls.append(("drop_column", table, column_name))

    def create_table(self, name, *items):
        self.calls.append(("create_table", name, items))

    def drop_table(self, name):
        self.calls.append(("drop_table", name))

    def create_index(self, name, table, columns, unique=False):
        self.calls.append(("create_index", name, table, tuple(columns), unique))

    def drop_index(self, name, table_name=None):
        self.calls.append(("drop_index", name, table_name))


def load_migration(op):
    stub = types.ModuleType("alembic")
    stub.op = op
    saved = sys.modules.get("alembic")
    sys.modules["alembic"] = stub
    try:
        spec = importlib.util.spec_from_file_location("migration_0005_under_test", MIGRATION)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = saved
    return module


def class_columns(path, class_name):
    """{attribute: AnnAssign node} for the mapped columns of a model class, read from source."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                n.target.id: n for n in node.body
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            }
    raise AssertionError(f"{class_name} not found in {path}")


class TestChain(unittest.TestCase):
    def test_0005_continues_from_0004_and_the_chain_has_a_single_head(self):
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
        self.assertEqual(revisions["0005"], "0004")
        parents = set(revisions.values())
        heads = [rev for rev in revisions if rev not in parents]
        self.assertEqual(len(heads), 1, heads)


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestUpgradeAndDowngrade(unittest.TestCase):
    def setUp(self):
        self.op = RecordingOp()
        self.migration = load_migration(self.op)
        self.migration.upgrade()
        self.calls = list(self.op.calls)

    def test_the_four_structured_columns_are_nullable_and_have_no_default(self):
        added = [(c[1], c[2]) for c in self.calls if c[0] == "add_column"]
        self.assertEqual([c.name for _, c in added], ["governorate", "area", "street", "landmark"])
        for table, column in added:
            self.assertEqual(table, "markets")
            self.assertIsInstance(column.type, sa.String)
            self.assertTrue(column.nullable)
            self.assertIsNone(column.server_default)  # old rows stay NULL; no backfill
        self.assertEqual([c.type.length for _, c in added], [20, 120, 160, 200])

    def test_address_is_not_touched(self):
        for call in [c for c in self.calls if c[0] == "add_column"]:
            self.assertNotEqual(call[2].name, "address")

    def test_the_log_table_has_the_audit_columns(self):
        ((_, name, items),) = [c for c in self.calls if c[0] == "create_table"]
        self.assertEqual(name, "market_location_changes")
        columns = {i.name: i for i in items if isinstance(i, sa.Column)}
        self.assertEqual(
            set(columns),
            {"id", "market_id", "user_id", "old_latitude", "old_longitude", "new_latitude",
             "new_longitude", "moved_m", "old_fields", "new_fields", "created_at"},
        )
        for column in columns.values():
            self.assertFalse(column.nullable, column.name)
        for float_column in ("old_latitude", "old_longitude", "new_latitude", "new_longitude", "moved_m"):
            self.assertIsInstance(columns[float_column].type, sa.Float)
            self.assertEqual(columns[float_column].type.precision, 53)  # double precision
        self.assertIsInstance(columns["old_fields"].type, postgresql.JSONB)
        self.assertIsInstance(columns["new_fields"].type, postgresql.JSONB)

    def test_the_log_goes_with_its_store_and_its_user(self):
        ((_, _, items),) = [c for c in self.calls if c[0] == "create_table"]
        targets = {
            tuple(e.target_fullname for e in fk.elements): fk.ondelete
            for fk in items if isinstance(fk, sa.ForeignKeyConstraint)
        }
        self.assertEqual(targets, {("markets.id",): "CASCADE", ("users.id",): "CASCADE"})
        self.assertTrue(any(isinstance(i, sa.PrimaryKeyConstraint) for i in items))

    def test_the_log_is_indexed_by_store(self):
        indexes = [c for c in self.calls if c[0] == "create_index"]
        self.assertEqual(
            indexes,
            [("create_index", "ix_market_location_changes_market_id", "market_location_changes",
              ("market_id",), False)],
        )

    def test_downgrade_undoes_everything_in_reverse(self):
        self.op.calls.clear()
        self.migration.downgrade()
        self.assertEqual(
            self.op.calls,
            [
                ("drop_index", "ix_market_location_changes_market_id", "market_location_changes"),
                ("drop_table", "market_location_changes"),
                ("drop_column", "markets", "landmark"),
                ("drop_column", "markets", "street"),
                ("drop_column", "markets", "area"),
                ("drop_column", "markets", "governorate"),
            ],
        )


class TestModels(unittest.TestCase):
    def test_market_declares_the_four_nullable_columns_with_the_migration_lengths(self):
        columns = class_columns(MARKET_MODEL, "Market")
        expected = {"governorate": 20, "area": 120, "street": 160, "landmark": 200}
        for name, length in expected.items():
            self.assertIn(name, columns, f"Market.{name} is missing")
            node = columns[name]
            self.assertIn("None", ast.unparse(node.annotation))  # Mapped[str | None]
            call = node.value
            self.assertEqual(ast.unparse(call.args[0]), f"String({length})")
            self.assertEqual({k.arg: ast.literal_eval(k.value) for k in call.keywords}, {"nullable": True})

    def test_address_stays_required(self):
        node = class_columns(MARKET_MODEL, "Market")["address"]
        self.assertEqual({k.arg: ast.literal_eval(k.value) for k in node.value.keywords}, {"nullable": False})

    def test_market_no_longer_pretends_to_have_address_ar(self):
        self.assertNotIn("address_ar", class_columns(MARKET_MODEL, "Market"))

    def test_the_log_model_matches_the_migration_columns(self):
        columns = class_columns(CHANGE_MODEL, "MarketLocationChange")
        self.assertEqual(
            set(columns),
            {"id", "market_id", "user_id", "old_latitude", "old_longitude", "new_latitude",
             "new_longitude", "moved_m", "old_fields", "new_fields", "created_at"},
        )
        with open(CHANGE_MODEL, encoding="utf-8") as f:
            source = f.read()
        self.assertIn('__tablename__ = "market_location_changes"', source)
        self.assertEqual(source.count('ondelete="CASCADE"'), 2)

    def test_the_log_model_is_registered_with_the_others(self):
        with open(MODELS_INIT, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("from app.models.market_location_change import MarketLocationChange", source)
        self.assertIn('"MarketLocationChange"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
