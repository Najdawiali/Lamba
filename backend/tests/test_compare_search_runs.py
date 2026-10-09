"""
Tests for the golden-query comparison tooling: scripts/compare_search_runs.py, the new options of
scripts/eval_search.py and scripts/flush_search_cache.py. Everything is loaded from the real files with
stand-ins for requests and Redis: no network, no server.
"""

import asyncio
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stub_modules import make_module, stubbed  # noqa: E402


def load_script(name, stubs=None):
    path = os.path.join(BACKEND, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("under_test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    with stubbed(stubs or {}):
        spec.loader.exec_module(module)
    return module


compare = load_script("compare_search_runs")


def item(name, matched=True, item_id=""):
    return {"rank": 1, "id": item_id, "name": name, "rerank_score": 0.5, "matched_keyword": matched}


def entry(query, *items, qtype="exact_ar"):
    return {"query": query, "query_type": qtype, "returned_items": list(items)}


def diff(before, after):
    return compare.diff_query("q", before, after)


class TestCompare(unittest.TestCase):
    def test_identical_results_are_the_same(self):
        d = diff(entry("q", item("A"), item("B")), entry("q", item("A"), item("B")))
        self.assertEqual((d.status, d.overlap, d.top1_same, d.removed, d.added), ("same", 1.0, True, [], []))
        self.assertFalse(d.regression)

    def test_results_that_leave_and_enter_are_named(self):
        d = diff(entry("q", item("A"), item("B")), entry("q", item("A"), item("C")))
        self.assertEqual((d.status, d.removed, d.added, d.top1_same), ("changed", ["B"], ["C"], True))
        self.assertAlmostEqual(d.overlap, 1 / 3)
        self.assertFalse(d.regression)

    def test_a_query_that_lost_all_its_results_is_a_regression(self):
        d = diff(entry("q", item("A")), entry("q"))
        self.assertEqual((d.status, d.regression), ("lost_all", True))

    def test_fewer_keyword_relevant_results_is_a_regression_even_if_the_count_is_the_same(self):
        d = diff(entry("q", item("A", True), item("B", True)), entry("q", item("A", True), item("X", False)))
        self.assertEqual((d.status, d.regression, d.relevant_before, d.relevant_after), ("fewer_relevant", True, 2, 1))

    def test_more_relevant_results_is_not_a_regression(self):
        d = diff(entry("q", item("A", False)), entry("q", item("A", True)))
        self.assertEqual(d.status, "same")
        d = diff(entry("q", item("A", False)), entry("q", item("B", True)))
        self.assertEqual((d.status, d.regression), ("changed", False))

    def test_gaining_results_from_nothing(self):
        d = diff(entry("q"), entry("q", item("A")))
        self.assertEqual((d.status, d.regression), ("gained_all", False))
        self.assertEqual(diff(entry("q"), entry("q")).status, "same")

    def test_the_id_identifies_a_result_when_there_is_one(self):
        d = diff(entry("q", item("Milk", item_id="1")), entry("q", item("Milk (renamed)", item_id="1")))
        self.assertEqual(d.status, "same")
        d = diff(entry("q", item("Milk", item_id="1")), entry("q", item("Milk", item_id="2")))
        self.assertEqual(d.status, "changed")

    def test_a_query_present_in_only_one_run_is_reported_not_judged(self):
        diffs = compare.compare_runs({"a": entry("a", item("A"))}, {"a": entry("a", item("A")), "b": entry("b", item("B"))})
        self.assertEqual([(d.query, d.status) for d in diffs], [("a", "same"), ("b", "missing_before")])
        diffs = compare.compare_runs({"a": entry("a", item("A"))}, {})
        self.assertEqual(diffs[0].status, "missing_after")
        self.assertFalse(any(d.regression for d in diffs))

    def test_the_report_names_regressions_and_can_hide_unchanged_queries(self):
        before = {"x": entry("x", item("A")), "y": entry("y", item("B")), "z": entry("z", item("C"), item("D"))}
        after = {"x": entry("x"), "y": entry("y", item("B")), "z": entry("z", item("C"), item("E"))}
        diffs = compare.compare_runs(before, after)
        text = compare.format_report(diffs)
        self.assertIn("[REGRESSION] 'x'", text)
        self.assertIn("left:    D", text)
        self.assertIn("entered: E", text)
        self.assertIn("regressions (lost all results, or fewer keyword-relevant results): 1", text)
        self.assertIn("'y'", text)
        self.assertNotIn("'y'", compare.format_report(diffs, only_changed=True))

    def test_files_round_trip_and_the_exit_code_follows_regressions(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for label, rows in (("before", [entry("شاي", item("شاي أخضر"))]), ("after", [entry("شاي")])):
                paths[label] = os.path.join(tmp, label + ".jsonl")
                with open(paths[label], "w", encoding="utf-8") as f:
                    for row in rows:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(compare.main([paths["before"], paths["after"]]), 0)
                self.assertEqual(compare.main([paths["before"], paths["after"], "--fail-on-regression"]), 1)
                self.assertEqual(compare.main([paths["before"], paths["before"], "--fail-on-regression"]), 0)
            self.assertIn("شاي", out.getvalue())

    def test_overall_metrics_are_shown_when_both_summaries_are_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for mrr in (0.5, 0.75):
                path = os.path.join(tmp, f"s{mrr}.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"overall": {"mrr_at_10": mrr, "latency_p50_ms": 2000.0}}, f)
                paths.append(path)
            lines = compare.summary_lines(*paths)
        self.assertTrue(any("mrr_at_10" in line and "0.5000 ->" in line and "0.7500" in line for line in lines))
        self.assertEqual(compare.summary_lines(None, None), [])


class FakeRequests:
    """Stands in for the requests module that eval_search.py uses."""

    class exceptions:
        class RequestException(Exception):
            pass

    def __init__(self, items):
        self.items, self.payloads = items, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.payloads.append((url, json))
        items = self.items

        class Response:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"found": True, "results": items}

        return Response()


class TestEvalSearchOptions(unittest.TestCase):
    def run_eval(self, argv, items):
        evaluator = load_script("eval_search")
        fake = FakeRequests(items)
        evaluator.requests = fake
        with tempfile.TemporaryDirectory() as tmp:
            dataset = os.path.join(tmp, "q.jsonl")
            with open(dataset, "w", encoding="utf-8") as f:
                f.write(json.dumps({"query": "شاي أخضر", "query_type": "t", "relevant_ids": [], "relevant_keywords": [["شاي"]]}, ensure_ascii=False) + "\n")
            out, worksheet = os.path.join(tmp, "out.json"), os.path.join(tmp, "ws.jsonl")
            old_argv = sys.argv
            sys.argv = ["eval_search.py", "--dataset", dataset, "--output", out, "--worksheet", worksheet,
                        "--base-url", "http://api.test"] + argv
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    evaluator.main()
            finally:
                sys.argv = old_argv
            with open(worksheet, encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        return fake, rows

    ITEMS = [{"item_id": "11111111-1111-1111-1111-111111111111", "name": "شاي أخضر ليبتون", "description": ""}]

    def test_defaults_are_unchanged(self):
        fake, _ = self.run_eval([], self.ITEMS)
        (url, payload) = fake.payloads[0]
        self.assertEqual(url, "http://api.test/api/v1/search/hybrid")
        self.assertEqual(payload, {"query_text": "شاي أخضر", "latitude": 32.0385, "longitude": 35.7275})

    def test_position_and_radius_can_be_chosen(self):
        fake, _ = self.run_eval(["--lat", "31.95", "--lng", "35.91", "--max-distance-km", "400"], self.ITEMS)
        payload = fake.payloads[0][1]
        self.assertEqual((payload["latitude"], payload["longitude"]), (31.95, 35.91))
        self.assertEqual(payload["filters"], {"max_distance_km": 400.0})

    def test_the_worksheet_keeps_the_items_id_which_the_api_calls_item_id(self):
        _, rows = self.run_eval([], self.ITEMS)
        item_row = rows[0]["returned_items"][0]
        self.assertEqual(item_row["id"], "11111111-1111-1111-1111-111111111111")
        self.assertTrue(item_row["matched_keyword"])


class TestFlushSearchCache(unittest.TestCase):
    class FakeRedis:
        def __init__(self, keys):
            self.keys = set(keys)

        async def scan_iter(self, match=None, count=None):
            import fnmatch
            for key in sorted(self.keys):
                if fnmatch.fnmatch(key, match):
                    yield key

        async def delete(self, key):
            self.keys.discard(key)

    def test_only_cached_search_results_are_deleted(self):
        keys = ["lamba:search:a", "lamba:search:b", "lamba:qu:c", "lamba:synonyms", "lamba:exp:d", "search:old", "lamba:stats:qu:2026-10-10"]
        redis = self.FakeRedis(keys)

        async def get_redis():
            return redis

        script = load_script("flush_search_cache", {
            "app.services.cache": make_module("app.services.cache", get_redis=get_redis),
        })
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            asyncio.run(script.main())
        self.assertEqual(sorted(redis.keys), sorted(set(keys) - {"lamba:search:a", "lamba:search:b"}))
        self.assertIn("Cleared 2 cached search results", out.getvalue())

    def test_it_no_longer_touches_the_synonym_table(self):
        path = os.path.join(BACKEND, "scripts", "flush_search_cache.py")
        with open(path, encoding="utf-8") as f:
            self.assertNotIn("build_synonym_table", f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
