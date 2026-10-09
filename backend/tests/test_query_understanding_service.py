"""
Tests for the query-understanding service: rules, cache, one model call, fallbacks, outcome counts.

The real app/services/query_understanding.py, http_pool.py, qu_cache.py and query_attributes.py are
used; the model adapter, Redis, httpx and app.config are stand-ins (tests/stub_modules.py). Needs
pydantic (the QueryIntent model) and skips itself without it.
"""

import ast
import asyncio
import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stub_modules import make_config, make_httpx, make_module, stubbed  # noqa: E402

try:
    import pydantic  # noqa: F401
    HAVE_PYDANTIC = True
except ImportError:  # pragma: no cover - depends on the interpreter
    HAVE_PYDANTIC = False

FRESH = ("app.services.http_pool", "app.services.query_understanding")


class FakeRedis:
    def __init__(self):
        self.values, self.ttls, self.hashes = {}, {}, {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.ttls[key] = ex

    async def hincrby(self, key, field, amount):
        self.hashes.setdefault(key, {})
        self.hashes[key][field] = self.hashes[key].get(field, 0) + amount

    async def expire(self, key, seconds):
        pass

    def counts(self):
        merged = {}
        for hash_ in self.hashes.values():
            for field, n in hash_.items():
                merged[field] = merged.get(field, 0) + n
        return merged


class FakeAdapter:
    """Stands in for llm_adapter: answers with `reply`, or fails with `reasons`."""

    def __init__(self):
        self.reply, self.reasons, self.raises, self.calls = None, [], None, []

    async def complete_chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        if self.reply is None:
            kwargs["error_sink"].extend(self.reasons)
        return self.reply


def answer(**fields):
    base = {"intent": "product", "query_clean": "شاي", "category_name": None, "brand": None,
            "search_query": "شاي اخضر", "attributes": {"type": "أخضر"}}
    base.update(fields)
    return json.dumps(base, ensure_ascii=False)


@unittest.skipUnless(HAVE_PYDANTIC, "pydantic is not installed")
class TestQueryUnderstandingService(unittest.TestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.adapter = FakeAdapter()
        self.config = make_config(
            query_llm_fallback_model="google/gemma-4-26B-A4B-it", query_llm_call_timeout_seconds=6.0,
            query_llm_fail_fast=True, query_llm_max_inflight=8, cache_qu_ttl=604800,
        )

        async def get_redis():
            if isinstance(self.redis, Exception):
                raise self.redis
            return self.redis

        stubs = {
            "httpx": make_httpx(),
            "app.config": self.config,
            "app.services.llm": make_module("app.services.llm", llm_adapter=self.adapter),
            "app.services.cache": make_module("app.services.cache", get_redis=get_redis),
        }
        self.stack = stubbed(stubs, fresh=FRESH)
        self.stack.__enter__()
        from app.services import http_pool, query_understanding
        self.qu, self.pool = query_understanding, http_pool
        self.service = query_understanding.QueryUnderstandingService()
        self.pool.deepinfra_query_breaker.failure_count = 0
        self.pool.deepinfra_query_breaker.is_open = False

    def tearDown(self):
        self.stack.__exit__(None, None, None)

    def analyze(self, query):
        return asyncio.run(self.service.analyze_query_async(query))

    # ── no model needed ───────────────────────────────────────────────────────────────────────────
    def test_a_simple_query_needs_no_model_and_still_gets_the_rule_attributes(self):
        intent = self.analyze("شاي")
        self.assertEqual((intent.attributes, intent.intent, intent.query_clean), ({}, None, None))
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.redis.counts(), {"not_needed": 1})

    # ── the model call ────────────────────────────────────────────────────────────────────────────
    def test_the_call_has_one_attempt_its_own_breaker_fail_fast_and_a_sink(self):
        self.adapter.reply = answer()
        intent = self.analyze("شاي اخضر")
        (call,) = self.adapter.calls
        self.assertEqual(call["model"], "google/gemma-4-26B-A4B-it")
        self.assertEqual(call["max_retries"], 1)                     # no retry inside the search's budget
        self.assertEqual(call["timeout"], 6.0)
        self.assertIs(call["breaker"], self.pool.deepinfra_query_breaker)
        self.assertIs(call["fail_fast"], True)
        self.assertEqual(call["temperature"], 0.0)
        self.assertEqual(call["chat_template_kwargs"], {"enable_thinking": False})
        self.assertIsInstance(call["error_sink"], list)
        self.assertEqual(call["messages"][1]["content"], "Query: شاي اخضر")
        self.assertEqual((intent.intent, intent.query_clean, intent.attributes), ("product", "شاي", {"type": "أخضر"}))
        self.assertEqual(self.redis.counts(), {"ok": 1})

    def test_fail_fast_can_be_switched_off(self):
        self.config.settings.query_llm_fail_fast = False
        self.adapter.reply = answer()
        self.analyze("شاي اخضر")
        self.assertNotIn("fail_fast", self.adapter.calls[0])

    def test_the_rules_win_over_the_model_for_their_keys_and_everything_else_is_kept(self):
        # the model says male and invents organic false; the words say female
        self.adapter.reply = answer(attributes={"gender": "male", "organic": False, "type": "أخضر"}, query_clean="عطر")
        intent = self.analyze("عطر نساءي عضوي")
        self.assertEqual(intent.attributes, {"gender": "female", "organic": True, "type": "أخضر"})

    def test_the_answer_is_cleaned(self):
        self.adapter.reply = answer(
            intent="robot", category_name=["x"], brand="  ", query_clean=None,
            attributes={"type": "أخضر", "price": 5, "color": None, "size": "كبير"},
        )
        intent = self.analyze("شاي اخضر كبير")
        self.assertEqual((intent.intent, intent.category_name, intent.brand, intent.query_clean), (None, None, None, None))
        self.assertEqual(intent.attributes, {"type": "أخضر", "size": "كبير"})

    # ── the cache ─────────────────────────────────────────────────────────────────────────────────
    def test_a_second_identical_query_is_served_from_the_cache_without_a_model_call(self):
        self.adapter.reply = answer(category_name="شاي")
        first = self.analyze("شاي اخضر")
        self.assertEqual(len(self.adapter.calls), 1)
        (key,) = [k for k in self.redis.values if k.startswith("lamba:qu:")]
        self.assertEqual(self.redis.ttls[key], 604800)
        self.adapter.reply = answer(category_name="Beverages")  # what the model would say this time
        second = self.analyze("شاي اخضر")
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual((second.category_name, second.attributes), (first.category_name, first.attributes))
        self.assertEqual(self.redis.counts(), {"ok": 1, "cache_hit": 1})

    def test_the_cache_holds_the_models_answer_not_the_rule_attributes(self):
        self.adapter.reply = answer(attributes={"type": "أخضر"})
        self.analyze("شاي اخضر عضوي")
        (stored,) = self.redis.values.values()
        self.assertEqual(json.loads(stored)["attributes"], {"type": "أخضر"})
        # and a cache hit still adds the rules
        again = self.analyze("شاي اخضر عضوي")
        self.assertEqual(again.attributes, {"type": "أخضر", "organic": True})

    def test_changing_the_model_does_not_reuse_old_answers(self):
        self.adapter.reply = answer()
        self.analyze("شاي اخضر")
        self.config.settings.query_llm_fallback_model = "Qwen/Qwen3.6-35B-A3B"
        self.analyze("شاي اخضر")
        self.assertEqual(len(self.adapter.calls), 2)

    def test_a_failed_call_is_never_cached(self):
        self.adapter.reply, self.adapter.reasons = None, ["timeout"]
        self.analyze("شاي اخضر")
        self.assertEqual(self.redis.values, {})

    def test_without_redis_it_still_works(self):
        self.redis = ConnectionError("redis down")
        self.adapter.reply = answer()
        intent = self.analyze("شاي اخضر")
        self.assertEqual(intent.query_clean, "شاي")
        self.assertEqual(len(self.adapter.calls), 1)

    # ── failures fall back to the rules ───────────────────────────────────────────────────────────
    def test_every_failure_falls_back_to_the_rule_attributes_and_is_named(self):
        cases = {
            "timeout": ["timeout"], "overloaded": ["http_429"], "http_error": ["http_503"],
            "breaker_open": ["breaker_open"], "no_api_key": ["no_api_key"], "error": ["error"],
        }
        for outcome, reasons in cases.items():
            self.redis = FakeRedis()
            self.adapter.calls.clear()
            self.adapter.reply, self.adapter.reasons = None, reasons
            intent = self.analyze("عطر نساءي")
            self.assertEqual(intent.attributes, {"gender": "female"}, outcome)
            self.assertEqual((intent.intent, intent.query_clean, intent.category_name), (None, None, None), outcome)
            self.assertEqual(intent.search_query, "عطر نساءي", outcome)
            self.assertEqual(self.redis.counts(), {outcome: 1}, outcome)

    def test_an_unparseable_reply_falls_back_and_is_named(self):
        for reply in ("sorry, I cannot", "", "[1, 2]", "null", '"text"'):
            self.redis = FakeRedis()
            self.adapter.reply = reply
            intent = self.analyze("قهوة باردة")
            self.assertEqual(intent.attributes, {"temperature": "cold"}, repr(reply))
            self.assertEqual(self.redis.counts(), {"bad_json": 1}, repr(reply))
            self.assertEqual(self.redis.values.keys() & {k for k in self.redis.values if k.startswith("lamba:qu:")}, set())

    def test_an_exception_from_the_adapter_never_reaches_the_search(self):
        self.adapter.raises = RuntimeError("boom")
        intent = self.analyze("زيت زيتون عضوي")
        self.assertEqual(intent.attributes, {"organic": True})
        self.assertEqual(self.redis.counts(), {"error": 1})

    def test_an_open_breaker_means_no_call_at_all(self):
        breaker = self.pool.deepinfra_query_breaker
        for _ in range(breaker.failure_threshold):
            breaker.record_failure()
        self.adapter.reply = answer()
        intent = self.analyze("عطر نساءي")
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(intent.attributes, {"gender": "female"})
        self.assertEqual(self.redis.counts(), {"breaker_open": 1})

    def test_too_many_calls_in_flight_means_no_call(self):
        self.service._inflight = self.config.settings.query_llm_max_inflight
        self.adapter.reply = answer()
        intent = self.analyze("عطر نساءي")
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual((intent.attributes, self.redis.counts()), ({"gender": "female"}, {"busy": 1}))

    def test_the_inflight_count_is_released_after_every_call(self):
        self.adapter.raises = RuntimeError("boom")
        self.analyze("عطر نساءي")
        self.adapter.raises, self.adapter.reply = None, answer()
        self.analyze("شاي اخضر")
        self.assertEqual(self.service._inflight, 0)

    def test_rules_only_intent_is_what_search_uses_when_the_model_is_late(self):
        intent = self.service.rules_only_intent("مزيل عرق رجالي")
        self.assertEqual((intent.attributes, intent.intent, intent.query_clean), ({"gender": "male"}, None, None))
        self.assertEqual(intent.search_query, "مزيل عرق رجالي")
        self.assertEqual(self.adapter.calls, [])


class TestSettingsDefaults(unittest.TestCase):
    """The numbers the time budget rests on, read from config.py's source (it needs pydantic-settings to import)."""

    @staticmethod
    def defaults():
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "config.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        found = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                try:
                    found[node.target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
        return found

    def test_the_query_path_defaults(self):
        d = self.defaults()
        self.assertEqual(d["query_llm_fallback_model"], "google/gemma-4-26B-A4B-it")  # not the saturated E4B
        self.assertEqual(d["query_understanding_budget_seconds"], 2.5)
        self.assertEqual(d["query_llm_call_timeout_seconds"], 6.0)
        self.assertGreater(d["query_llm_call_timeout_seconds"], d["query_understanding_budget_seconds"])  # a late answer can still be cached
        self.assertIs(d["query_llm_fail_fast"], True)
        self.assertEqual(d["query_llm_max_inflight"], 8)
        self.assertEqual(d["cache_qu_ttl"], 604800)


if __name__ == "__main__":
    unittest.main(verbosity=2)
