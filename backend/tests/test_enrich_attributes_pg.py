"""
The SQL of app.jobs.enrich_attributes against a REAL PostgreSQL: which products are pending, the
repeatable random sample, the merge (existing keys win) and the guard against writing twice.

Skipped unless LAMBA_TEST_DATABASE_URL is set. Point it at any THROWAWAY PostgreSQL 13+ (no extensions,
no migrations needed): the test creates a TEMP table called global_items, which shadows any real one
for that connection only and disappears when the connection closes. Never point it at production.

    docker run -d --name lamba-test-pg -e POSTGRES_PASSWORD=throwaway -e POSTGRES_DB=t -p 127.0.0.1:55432:5432 postgres:16
    LAMBA_TEST_DATABASE_URL=postgresql+asyncpg://postgres:throwaway@127.0.0.1:55432/t python -m unittest tests.test_enrich_attributes_pg
    docker rm -f lamba-test-pg
"""

import json
import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_DB_URL = os.environ.get("LAMBA_TEST_DATABASE_URL")

if TEST_DB_URL:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.jobs import enrich_attributes as job

CREATE_TABLE = """
CREATE TEMP TABLE global_items (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    name_ar text,
    listing_type text NOT NULL DEFAULT 'product',
    created_by uuid,
    moderation_status text NOT NULL DEFAULT 'approved',
    attributes jsonb DEFAULT '{}',
    attributes_version smallint
)
"""


@unittest.skipUnless(TEST_DB_URL, "LAMBA_TEST_DATABASE_URL not set")
class TestEnrichAttributesSql(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
        self.conn = await self.engine.connect()
        await self.conn.execute(text(CREATE_TABLE))
        self.ids = {}

    async def asyncTearDown(self):
        await self.conn.rollback()
        await self.conn.close()
        await self.engine.dispose()

    async def add(self, label, name="منتج", name_ar=None, attributes="{}", version=None,
                  listing_type="product", created_by=None, status="approved"):
        """Insert one row; `attributes` is JSON text, or None for SQL NULL."""
        item_id = str(uuid.uuid4())
        self.ids[label] = item_id
        await self.conn.execute(
            text("INSERT INTO global_items (id, name, name_ar, listing_type, created_by, moderation_status, "
                 "attributes, attributes_version) VALUES (CAST(:id AS uuid), :name, :name_ar, :lt, "
                 "CAST(:cb AS uuid), :st, CAST(:attrs AS jsonb), :v)"),
            {"id": item_id, "name": name, "name_ar": name_ar, "lt": listing_type, "cb": created_by,
             "st": status, "attrs": attributes, "v": version},
        )

    async def attributes_of(self, label):
        row = (await self.conn.execute(
            text("SELECT attributes, attributes_version FROM global_items WHERE id = CAST(:id AS uuid)"),
            {"id": self.ids[label]},
        )).one()
        value = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        return value, row[1]

    async def seed_catalog(self):
        merchant = str(uuid.uuid4())
        await self.add("empty", name="شاي", name_ar="شاي أخضر")           # pending, uses name_ar
        await self.add("null", name="ماء", attributes=None)                # pending: SQL NULL
        await self.add("json_null", name="عصير", attributes="null")        # pending: JSON null literal
        await self.add("array", name="حليب", attributes="[]")              # pending: not an object
        await self.add("blank_ar", name="لبن", name_ar="  ")               # pending, falls back to name
        await self.add("stock_only", name="جبنة", attributes='{"stock_status": "available"}')  # pending
        await self.add("has_keys", name="زيت", attributes='{"brand": "x"}')   # already holds an attribute
        await self.add("done", name="سكر", version=1)                      # already processed
        await self.add("merchant", name="ملح", created_by=merchant)        # merchant-created
        await self.add("service", name="حلاقة", listing_type="service")    # not a product
        await self.add("blocked", name="كحول", status="blocked")           # never shown to customers
        await self.add("pending_review", name="تمر", status="pending_review")  # pending: may be approved later

    async def test_which_products_are_pending(self):
        await self.seed_catalog()
        rows = await job.fetch_pending(self.conn)
        by_id = {item_id: name for item_id, name in rows}
        expected = {"empty", "null", "json_null", "array", "blank_ar", "stock_only", "pending_review"}
        self.assertEqual({label for label, i in self.ids.items() if i in by_id}, expected)
        self.assertEqual(by_id[self.ids["empty"]], "شاي أخضر")   # the Arabic name wins
        self.assertEqual(by_id[self.ids["blank_ar"]], "لبن")      # blank name_ar falls back to name
        self.assertEqual([r[0] for r in rows], sorted(by_id))     # by id

    async def test_seeded_sample_is_repeatable_and_limited(self):
        await self.seed_catalog()
        first = await job.fetch_pending(self.conn, limit=4, seed=7)
        again = await job.fetch_pending(self.conn, limit=4, seed=7)
        self.assertEqual(first, again)
        self.assertEqual(len(first), 4)
        everything = await job.fetch_pending(self.conn)
        self.assertTrue(set(first) <= set(everything))

    async def test_saving_merges_with_existing_keys_winning_and_sets_the_version(self):
        await self.seed_catalog()
        rows = [
            (self.ids["stock_only"], {"type": "أخضر", "stock_status": "SHOULD NOT WIN"}),
            (self.ids["null"], {"brand": "نستله"}),
            (self.ids["json_null"], {"flavor": "ليمون"}),
            (self.ids["array"], {}),
        ]
        self.assertEqual(await job.save_results(self.conn, rows, version=1), 4)
        self.assertEqual(await self.attributes_of("stock_only"), ({"type": "أخضر", "stock_status": "available"}, 1))
        self.assertEqual(await self.attributes_of("null"), ({"brand": "نستله"}, 1))
        self.assertEqual(await self.attributes_of("json_null"), ({"flavor": "ليمون"}, 1))
        self.assertEqual(await self.attributes_of("array"), ({}, 1))  # nothing extracted, still marked done
        # a finished product is no longer pending
        pending = {item_id for item_id, _ in await job.fetch_pending(self.conn)}
        for label in ("stock_only", "null", "json_null", "array"):
            self.assertNotIn(self.ids[label], pending)

    async def test_a_second_save_changes_nothing(self):
        await self.seed_catalog()
        row = (self.ids["empty"], {"type": "أخضر"})
        self.assertEqual(await job.save_results(self.conn, [row], version=1), 1)
        self.assertEqual(await job.save_results(self.conn, [(self.ids["empty"], {"type": "أسود"})], version=2), 0)
        self.assertEqual(await self.attributes_of("empty"), ({"type": "أخضر"}, 1))

    async def test_stats_count_each_group(self):
        await self.seed_catalog()
        await job.save_results(self.conn, [(self.ids["empty"], {"type": "أخضر"})], version=1)
        stats = await job.fetch_stats(self.conn, version=1)
        self.assertEqual(stats["catalog_products"], 10)   # all but the merchant item and the service
        self.assertEqual(stats["blocked"], 1)
        self.assertEqual(stats["done_current_version"], 2)  # "done" and "empty"
        self.assertEqual(stats["done_older_version"], 0)
        self.assertEqual(stats["has_attributes_but_no_version"], 1)  # "has_keys"
        self.assertEqual(stats["pending"], 6)

    async def test_audit_sample_and_value_counts_cover_only_processed_catalog_products(self):
        await self.seed_catalog()
        await job.save_results(self.conn, [
            (self.ids["empty"], {"type": "أخضر", "brand": "ليز"}),
            (self.ids["null"], {"type": "أخضر"}),
            (self.ids["array"], {"type": "أسود"}),
            (self.ids["blank_ar"], {}),
        ], version=1)
        sample = await job.fetch_audit_sample(self.conn, limit=10, seed=3, version=1)
        ids = {item_id for item_id, _, _ in sample}
        # the four just saved plus "done" (processed earlier); never the merchant item or unprocessed rows
        self.assertEqual(ids, {self.ids[k] for k in ("empty", "null", "array", "blank_ar", "done")})
        self.assertTrue(all(isinstance(attrs, dict) for _, _, attrs in sample))
        self.assertEqual(sample, await job.fetch_audit_sample(self.conn, limit=10, seed=3, version=1))
        counts = await job.fetch_value_counts(self.conn, version=1)
        self.assertEqual(counts, {"type": [("أخضر", 2), ("أسود", 1)], "brand": [("ليز", 1)]})

    async def test_arabic_survives_the_round_trip(self):
        await self.seed_catalog()
        await job.save_results(self.conn, [(self.ids["empty"], {"type": "بكر ممتاز"})], version=1)
        value, _ = await self.attributes_of("empty")
        self.assertEqual(json.dumps(value, ensure_ascii=False), '{"type": "بكر ممتاز"}')


if __name__ == "__main__":
    unittest.main(verbosity=2)
