"""
Tests for app.jobs.enrich_attributes: the run loop, failure handling, reports and command-line glue,
with a fake model call and a fake database session. No network, no database.

The SQL itself is checked against a real PostgreSQL in test_enrich_attributes_pg.py.
Needs SQLAlchemy only to import the job (it builds its statements with text()); skipped without it.
"""

import asyncio
import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.jobs import enrich_attributes as job
    from app.services.attribute_extraction import EXTRACT_KEYS, RESPONSE_FORMATS, Extraction
    HAVE_SQLALCHEMY = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_SQLALCHEMY = False


def reply(content, prompt_tokens=900, completion_tokens=25):
    return {"choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}}


class FakeModel:
    """call_chat(messages, response_format): answers by product name, records every call."""

    def __init__(self, answers=None, default=None):
        self.answers = answers or {}
        self.default = default
        self.calls = []

    async def __call__(self, messages, response_format):
        name = messages[1]["content"].split("\n", 1)[0].removeprefix("Product name: ")
        self.calls.append((name, response_format))
        answer = self.answers.get(name, self.default)
        if callable(answer):
            answer = answer(len([c for c in self.calls if c[0] == name]))
        return answer


class FakeSleep:
    def __init__(self):
        self.pauses = []

    async def __call__(self, seconds):
        self.pauses.append(seconds)


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestEnrichProcess(unittest.TestCase):
    def go(self, items, model, **kw):
        saved = []

        async def save(rows):
            saved.append(list(rows))
            return len(rows)

        kw.setdefault("concurrency", 2)
        kw.setdefault("sleep", FakeSleep())
        if kw.pop("dry", False):
            save = None
        report = asyncio.run(job.process(items, call_chat=model, response_format=None, save=save, **kw))
        return report, saved

    def test_valid_answers_are_saved_per_chunk_and_counted(self):
        model = FakeModel({
            "حليب المراعي قليل الدسم": reply('{"brand": "المراعي", "dietary": "قليل الدسم"}'),
            "شيبس ليز": reply('{"brand": "ليز"}'),
            "مياه": reply("{}"),
        })
        items = [("1", "حليب المراعي قليل الدسم"), ("2", "شيبس ليز"), ("3", "مياه")]
        report, saved = self.go(items, model, chunk_size=2)
        self.assertEqual([[row[0] for row in chunk] for chunk in saved], [["1", "2"], ["3"]])
        self.assertEqual(saved[1], [("3", {})])  # nothing extracted is still saved, so it is not billed again
        self.assertEqual((report.total, report.written, report.with_attributes), (3, 3, 2))
        self.assertEqual(report.statuses, {"ok": 3})
        self.assertEqual(dict(report.key_counts), {"brand": 2, "dietary": 1})
        self.assertEqual((report.prompt_tokens, report.completion_tokens), (2700, 75))
        self.assertAlmostEqual(report.estimated_cost_usd, (2700 * 0.20 + 75 * 0.40) / 1e6)
        self.assertEqual(report.results, [])  # only a dry run keeps them
        self.assertFalse(report.aborted)

    def test_provider_failures_are_retried_with_a_growing_pause(self):
        model = FakeModel({"ماء": lambda n: None if n < 3 else reply("{}")})
        sleep = FakeSleep()
        report, saved = self.go([("1", "ماء")], model, sleep=sleep, attempts=3)
        self.assertEqual(report.statuses, {"ok": 1})
        self.assertEqual(sleep.pauses, [5, 10])
        self.assertEqual(saved, [[("1", {})]])

    def test_a_product_that_keeps_failing_stays_pending(self):
        model = FakeModel({"ماء": None, "عصير": reply("{}")})
        report, saved = self.go([("1", "ماء"), ("2", "عصير")], model, attempts=2)
        self.assertEqual(saved, [[("2", {})]])  # the failed one is not written, so it is picked up next run
        self.assertEqual(report.failures, [("1", "ماء", "no_response", "")])
        self.assertEqual(report.statuses, {"no_response": 1, "ok": 1})

    def test_unparseable_answers_are_not_retried_and_not_saved(self):
        model = FakeModel({"ماء": reply("sorry, no")})
        report, saved = self.go([("1", "ماء")], model, attempts=3)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(saved, [])
        self.assertEqual(report.failures, [("1", "ماء", "bad_json", "sorry, no")])

    def test_it_stops_after_too_many_failures_in_a_row(self):
        model = FakeModel(default=None)
        items = [(str(i), f"منتج {i}") for i in range(100)]
        report, saved = self.go(items, model, attempts=2, max_consecutive_failures=5, chunk_size=10, concurrency=2)
        self.assertTrue(report.aborted)
        self.assertEqual(saved, [])
        self.assertLess(len(model.calls), 30)  # it did not grind through the queue
        self.assertEqual(report.statuses["no_response"] + report.statuses["skipped"], 10)  # only the first chunk
        self.assertEqual(len(report.failures), report.statuses["no_response"])  # skipped ones are not failures
        self.assertTrue(all(name in {f"منتج {i}" for i in range(10)} for name, _ in model.calls))

    def test_a_success_resets_the_failure_streak(self):
        answers = {}
        items = []
        for i in range(12):
            name = f"منتج {i}"
            items.append((str(i), name))
            answers[name] = reply("{}") if i % 3 == 2 else None  # fail, fail, ok, fail, fail, ok ...
        report, saved = self.go(items, FakeModel(answers), attempts=1, max_consecutive_failures=3, concurrency=1)
        self.assertFalse(report.aborted)
        self.assertEqual(report.statuses, {"ok": 4, "no_response": 8})

    def test_a_dry_run_saves_nothing_and_keeps_every_result(self):
        model = FakeModel({"ماء": reply('{"brand": "نستله"}')})  # brand is not in the name: dropped
        report, saved = self.go([("1", "ماء")], model, dry=True, keep_results=True)
        self.assertEqual((saved, report.written), ([], 0))
        ((item_id, name, result),) = report.results
        self.assertEqual((item_id, name, result.attributes, result.dropped), ("1", "ماء", {}, ["brand:not_in_name"]))
        self.assertEqual(dict(report.drops), {"brand:not_in_name": 1})

    def test_the_key_filter_reaches_the_validator(self):
        model = FakeModel({"حليب المراعي كامل": reply('{"brand": "المراعي", "type": "كامل"}')})
        report, saved = self.go([("1", "حليب المراعي كامل")], model, keys=("brand",))
        self.assertEqual(saved, [[("1", {"brand": "المراعي"})]])
        self.assertEqual(dict(report.drops), {"type:key_disabled": 1})


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestEnrichProbeAndGate(unittest.TestCase):
    def test_auto_picks_the_first_mode_the_model_accepts(self):
        def only(*accepted):
            async def call_chat(messages, response_format):
                key = next(k for k, v in RESPONSE_FORMATS.items() if v == response_format)
                return reply("{}") if key in accepted else None
            return call_chat

        self.assertEqual(asyncio.run(job.choose_response_format(only("schema", "object", "none"))), "schema")
        self.assertEqual(asyncio.run(job.choose_response_format(only("object", "none"))), "object")
        self.assertEqual(asyncio.run(job.choose_response_format(only("none"))), "none")
        with self.assertRaises(RuntimeError):
            asyncio.run(job.choose_response_format(only()))

    def test_an_explicit_mode_is_the_only_one_tried(self):
        tried = []

        async def call_chat(messages, response_format):
            tried.append(response_format)
            return None

        with self.assertRaises(RuntimeError):
            asyncio.run(job.choose_response_format(call_chat, "object"))
        self.assertEqual(tried, [RESPONSE_FORMATS["object"]])

    def test_the_breaker_gate_waits_until_the_breaker_closes(self):
        class Breaker:
            def __init__(self):
                self.answers = [True, True, False]

            def should_skip(self):
                return self.answers.pop(0)

        sleep = FakeSleep()
        asyncio.run(job.breaker_gate(Breaker(), sleep))
        self.assertEqual(sleep.pauses, [2, 2])


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestEnrichReports(unittest.TestCase):
    def read(self, path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))

    def test_the_grading_sheet_has_the_columns_and_only_answered_rows(self):
        results = [
            ("a1", "شاي أخضر", Extraction("ok", {"type": "أخضر"})),
            ("a2", "كرتونة مياه", Extraction("ok", {})),
            ("a3", "ماء", Extraction("no_response")),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sample.csv")
            job.write_sample_csv(path, results)
            with open(path, "rb") as f:
                self.assertTrue(f.read(3) == b"\xef\xbb\xbf")  # BOM, so Excel shows Arabic correctly
            rows = self.read(path)
        self.assertEqual(rows[0], ["id", "name", "extracted_attributes", "correct", "notes"])
        self.assertEqual(rows[1:], [["a1", "شاي أخضر", '{"type": "أخضر"}', "", ""],
                                    ["a2", "كرتونة مياه", "{}", "", ""]])
        self.assertEqual(json.loads(rows[1][2]), {"type": "أخضر"})

    def test_drops_and_failures_files(self):
        results = [
            ("a1", "شاي", Extraction("ok", {}, ["brand:not_in_name", "type:has_digit"], '{"brand": "x"}')),
            ("a2", "ماء", Extraction("ok", {"type": "عذب"})),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            drops, failures = os.path.join(tmp, "d.csv"), os.path.join(tmp, "f.csv")
            job.write_drops_csv(drops, results)
            job.write_failures_csv(failures, [("a3", "ماء", "bad_json", "oops")])
            self.assertEqual(self.read(drops)[1:], [["a1", "شاي", '{"brand": "x"}', "brand:not_in_name; type:has_digit"]])
            self.assertEqual(self.read(failures)[1:], [["a3", "ماء", "bad_json", "oops"]])

    def test_the_summary_mentions_cost_rate_and_values(self):
        report = job.RunReport(total=2, elapsed=4.0, prompt_tokens=2000, completion_tokens=50)
        report.statuses["ok"] = 2
        report.with_attributes = 1
        report.key_counts["brand"] = 1
        report.values["brand"]["ليز"] = 1
        text = job.format_report(report, dry_run=True)
        self.assertIn("DRY RUN (nothing was written)", text)
        self.assertIn("0.50 items/s", text)
        self.assertIn("ليز x1", text)
        self.assertIn("$0.000", text)

    def test_the_output_folder_is_checked_before_money_is_spent(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "a", "b")
            job.ensure_writable(nested)
            self.assertEqual(os.listdir(nested), [])  # the probe file is removed
            blocker = os.path.join(tmp, "file")
            open(blocker, "w").close()
            with self.assertRaises(OSError):
                job.ensure_writable(blocker)


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestEnrichSqlText(unittest.TestCase):
    def test_only_catalog_products_that_are_not_done_are_pending(self):
        where = job.PENDING_WHERE
        for needle in ("listing_type = 'product'", "created_by IS NULL", "moderation_status <> 'blocked'",
                       "attributes_version IS NULL", "?|"):
            self.assertIn(needle, where)
        for key in EXTRACT_KEYS:
            self.assertIn(f"'{key}'", where)

    def test_the_update_keeps_existing_keys_and_only_touches_unversioned_rows(self):
        sql = " ".join(str(job.UPDATE_SQL).split())
        # new || existing: on a key clash the right-hand (existing) value wins
        self.assertIn("CAST(:new AS jsonb) || CASE WHEN jsonb_typeof(attributes) = 'object' THEN attributes", sql)
        self.assertTrue(sql.endswith("AND attributes_version IS NULL"))
        self.assertEqual(set(job.UPDATE_SQL.compile().params), {"new", "version", "id"})
        self.assertEqual(set(job.STATS_SQL.compile().params), {"v"})


class FakeResult:
    def __init__(self, rows=None, rowcount=1, mapping=None):
        self._rows, self.rowcount, self._mapping = rows or [], rowcount, mapping

    def all(self):
        return self._rows

    def mappings(self):
        return self

    def one(self):
        return self._mapping


class FakeDb:
    def __init__(self, pending=(), audit_rows=(), value_rows=()):
        self.pending = list(pending)
        self.audit_rows = list(audit_rows)
        self.value_rows = list(value_rows)
        self.executed = []
        self.commits = 0

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.executed.append((sql, params))
        if sql.startswith("SELECT CAST(id AS text), COALESCE(NULLIF(btrim(name_ar), ''), name), attributes"):
            return FakeResult(rows=self.audit_rows)
        if sql.startswith("SELECT CAST(id AS text)"):
            return FakeResult(rows=[tuple(p) for p in self.pending])
        if sql.startswith("SELECT kv.key"):
            return FakeResult(rows=self.value_rows)
        if sql.startswith("UPDATE"):
            return FakeResult(rowcount=1)
        return FakeResult(mapping={"catalog_products": 7, "pending": 3})

    async def commit(self):
        self.commits += 1

    def updates(self):
        return [params for sql, params in self.executed if sql.startswith("UPDATE")]


class FakeSessions:
    """async_session(): every `async with` hands out the same FakeDb."""

    def __init__(self, db):
        self.db = db

    def __call__(self):
        db = self.db

        @contextlib.asynccontextmanager
        async def manager():
            yield db

        return manager()


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestEnrichDatabaseHelpers(unittest.TestCase):
    def test_pending_products_are_selected_by_id_or_in_a_seeded_random_order(self):
        db = FakeDb(pending=[("id-1", "شاي"), ("id-2", "ماء")])
        self.assertEqual(asyncio.run(job.fetch_pending(db)), [("id-1", "شاي"), ("id-2", "ماء")])
        sql, params = db.executed[-1]
        self.assertTrue(sql.endswith("ORDER BY id"))
        self.assertEqual(params, {})

        asyncio.run(job.fetch_pending(db, limit=100, seed=7))
        sql, params = db.executed[-1]
        self.assertIn("ORDER BY md5(CAST(id AS text) || :seed) LIMIT :limit", sql)
        self.assertEqual(params, {"seed": "7", "limit": 100})

    def test_save_sends_json_text_and_counts_rows_changed(self):
        db = FakeDb()
        rows = [("id-1", {"type": "أخضر"}), ("id-2", {})]
        self.assertEqual(asyncio.run(job.save_results(db, rows, version=1)), 2)
        self.assertEqual(db.updates(), [
            {"id": "id-1", "new": '{"type": "أخضر"}', "version": 1},
            {"id": "id-2", "new": "{}", "version": 1},
        ])


@unittest.skipUnless(HAVE_SQLALCHEMY, "SQLAlchemy is not installed")
class TestEnrichRun(unittest.TestCase):
    def run_job(self, argv, db, model):
        args = job.build_parser().parse_args(argv)
        out = io.StringIO()
        with mock.patch.object(job, "make_call_chat", return_value=model), contextlib.redirect_stdout(out):
            code = asyncio.run(job.run(args, FakeSessions(db)))
        return code, out.getvalue()

    def test_defaults(self):
        args = job.build_parser().parse_args([])
        self.assertEqual((args.dry_run, args.stats, args.limit, args.seed, args.concurrency, args.out_dir),
                         (False, False, None, None, 8, "/data"))
        self.assertEqual(args.keys, ",".join(EXTRACT_KEYS))
        self.assertEqual(args.response_format, "auto")

    def test_a_dry_run_writes_the_sheets_and_never_updates_the_database(self):
        db = FakeDb(pending=[("id-1", "شاي أخضر"), ("id-2", "كرتونة مياه 12 حبة")])
        model = FakeModel({"شاي أخضر": reply('{"type": "أخضر"}'), "كرتونة مياه 12 حبة": reply("{}"),
                           job.PROBE_NAME: reply("{}")})
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.run_job(["--dry-run", "--limit", "100", "--out-dir", tmp], db, model)
            names = sorted(os.listdir(tmp))
            with open(os.path.join(tmp, "attributes_sample_seed1_n2.csv"), encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
        self.assertEqual(code, 0)
        self.assertEqual(names, ["attributes_sample_seed1_n2.csv", "attributes_sample_seed1_n2.drops.csv"])
        self.assertEqual(db.updates(), [])
        self.assertEqual(db.commits, 0)
        self.assertEqual(len(rows), 3)
        self.assertIn("DRY RUN (nothing was written)", out)
        self.assertIn("structured output mode: schema", out)
        # the dry run defaults to seed 1: a repeatable random sample, 100 products at most
        select_sql, select_params = db.executed[0]
        self.assertEqual(select_params, {"seed": "1", "limit": 100})

    def test_a_real_run_updates_and_commits_each_chunk(self):
        db = FakeDb(pending=[("id-1", "شاي أخضر"), ("id-2", "ماء")])
        model = FakeModel({"شاي أخضر": reply('{"type": "أخضر"}'), "ماء": reply("{}"), job.PROBE_NAME: reply("{}")})
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.run_job(["--out-dir", tmp], db, model)
            leftover = os.listdir(tmp)
        self.assertEqual(code, 0)
        self.assertEqual(db.updates(), [
            {"id": "id-1", "new": '{"type": "أخضر"}', "version": 1},
            {"id": "id-2", "new": "{}", "version": 1},
        ])
        self.assertGreaterEqual(db.commits, 1)
        self.assertEqual(leftover, [])  # no failures, and a real run writes no sheets
        self.assertIn("rows written: 2", out)
        select_params = db.executed[0][1]
        self.assertEqual(select_params, {})  # by id, no limit

    def test_nothing_is_spent_when_the_model_does_not_answer_the_probe(self):
        db = FakeDb(pending=[("id-1", "شاي")])
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.run_job(["--out-dir", tmp], db, FakeModel(default=None))
        self.assertEqual(code, 2)
        self.assertEqual(db.updates(), [])
        self.assertIn("STOPPED before processing anything", out)

    def test_stats_makes_no_model_calls_and_writes_no_files(self):
        db = FakeDb()
        model = FakeModel()
        with tempfile.TemporaryDirectory() as tmp:
            blocked = os.path.join(tmp, "not-created")
            code, out = self.run_job(["--stats", "--out-dir", blocked], db, model)
            self.assertFalse(os.path.exists(blocked))
        self.assertEqual((code, model.calls), (0, []))
        self.assertIn("pending: 3", out)

    def test_audit_writes_a_sheet_from_stored_values_and_lists_every_value(self):
        db = FakeDb(
            audit_rows=[("id-1", "شاي أخضر", {"type": "أخضر"}), ("id-2", "حليب", '{"stock_status": "available"}')],
            value_rows=[("type", "أخضر", 40), ("type", "أسود", 25), ("brand", "ليز", 3)],
        )
        model = FakeModel()
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.run_job(["--audit", "--limit", "50", "--seed", "2", "--out-dir", tmp], db, model)
            sheet = os.path.join(tmp, "attributes_audit_seed2_n2.csv")
            with open(sheet, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
        self.assertEqual((code, model.calls, db.updates(), db.commits), (0, [], [], 0))
        self.assertEqual(rows[0], ["id", "name", "extracted_attributes", "correct", "notes"])
        self.assertEqual(json.loads(rows[1][2]), {"type": "أخضر"})
        self.assertEqual(json.loads(rows[2][2]), {"stock_status": "available"})  # JSON text from the driver
        self.assertEqual(db.executed[0][1], {"v": 1, "seed": "2", "limit": 50})
        self.assertIn("type: 65 products, 2 distinct: أخضر x40, أسود x25", out)
        self.assertIn("brand: 3 products, 1 distinct: ليز x3", out)

    def test_value_counts_text_shows_junk_at_a_glance(self):
        text = job.format_value_counts({"type": [("v%d" % i, 20 - i) for i in range(20)], "gender": [("female", 4)]})
        self.assertIn("+5 more values", text)
        self.assertIn("gender: 4 products, 1 distinct: female x4", text)
        self.assertEqual(job.format_value_counts({}), "  (no extracted attributes stored yet)")

    def test_nothing_pending_is_not_an_error(self):
        code, out = self.run_job(["--out-dir", tempfile.gettempdir()], FakeDb(), FakeModel())
        self.assertEqual(code, 0)
        self.assertIn("Nothing to do.", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
