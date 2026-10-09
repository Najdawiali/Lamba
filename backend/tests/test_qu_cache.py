"""
Tests for app.services.qu_cache: cache keys, the cached shape and the outcome counters.
A fake Redis client is passed in: no server, no network.
"""

import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import qu_cache


class FakeRedis:
    def __init__(self):
        self.values, self.ttls, self.hashes, self.expiries = {}, {}, {}, {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.ttls[key] = ex

    async def hincrby(self, key, field, amount):
        self.hashes.setdefault(key, {})
        self.hashes[key][field] = self.hashes[key].get(field, 0) + amount

    async def expire(self, key, seconds):
        self.expiries[key] = seconds


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("down")

    set = hincrby = expire = get


def run(coro):
    return asyncio.run(coro)


ANSWER = {
    "intent": "product", "category_name": "شاي", "brand": None, "search_query": "شاي اخضر",
    "query_clean": "شاي", "attributes": {"type": "أخضر"},
}


class TestQuCache(unittest.TestCase):
    def test_the_key_depends_on_query_model_and_prompt_but_not_on_case_or_spaces(self):
        base = qu_cache.cache_key("شاي اخضر", "google/gemma-4-26B-A4B-it", "abc123")
        self.assertTrue(base.startswith(qu_cache.KEY_PREFIX))
        self.assertEqual(base, qu_cache.cache_key("  شاي اخضر ", "google/gemma-4-26B-A4B-it", "abc123"))
        self.assertEqual(qu_cache.cache_key("Iced Tea", "m", "p"), qu_cache.cache_key("iced tea", "m", "p"))
        for other in (
            qu_cache.cache_key("شاي احمر", "google/gemma-4-26B-A4B-it", "abc123"),
            qu_cache.cache_key("شاي اخضر", "google/gemma-4-E4B-it", "abc123"),
            qu_cache.cache_key("شاي اخضر", "google/gemma-4-26B-A4B-it", "def456"),
        ):
            self.assertNotEqual(base, other)

    def test_an_answer_round_trips_with_its_ttl(self):
        redis = FakeRedis()
        key = qu_cache.cache_key("شاي اخضر", "m", "p")
        self.assertTrue(run(qu_cache.put(redis, key, ANSWER, 604800)))
        self.assertEqual(redis.ttls[key], 604800)
        self.assertEqual(run(qu_cache.get(redis, key)), ANSWER)
        self.assertEqual(json.loads(redis.values[key])["attributes"], {"type": "أخضر"})  # stored as readable Arabic
        self.assertIn("أخضر", redis.values[key])

    def test_only_the_known_fields_are_kept(self):
        redis = FakeRedis()
        key = "k"
        run(qu_cache.put(redis, key, {**ANSWER, "extra": "x"}, 60))
        self.assertNotIn("extra", json.loads(redis.values[key]))

    def test_missing_fields_become_none_and_empty_attributes(self):
        redis = FakeRedis()
        run(qu_cache.put(redis, "k", {"intent": "service"}, 60))
        self.assertEqual(run(qu_cache.get(redis, "k")), {
            "intent": "service", "category_name": None, "brand": None, "search_query": None,
            "query_clean": None, "attributes": {},
        })

    def test_unusable_values_are_a_miss_never_an_error(self):
        redis = FakeRedis()
        for stored in ("not json", "[1, 2]", '"text"', '{"attributes": "x"}', '{"intent": 5}', ""):
            redis.values["k"] = stored
            self.assertIsNone(run(qu_cache.get(redis, "k")), stored)
        self.assertIsNone(run(qu_cache.get(redis, "never-stored")))
        self.assertFalse(run(qu_cache.put(redis, "k", "nonsense", 60)))
        self.assertFalse(run(qu_cache.put(redis, "k", {"attributes": "x"}, 60)))

    def test_a_broken_or_missing_redis_never_raises(self):
        broken = BrokenRedis()
        self.assertIsNone(run(qu_cache.get(broken, "k")))
        self.assertFalse(run(qu_cache.put(broken, "k", ANSWER, 60)))
        run(qu_cache.count(broken, "ok"))
        self.assertIsNone(run(qu_cache.get(None, "k")))
        self.assertFalse(run(qu_cache.put(None, "k", ANSWER, 60)))
        run(qu_cache.count(None, "ok"))

    def test_outcomes_are_counted_per_day_and_expire(self):
        redis = FakeRedis()
        for outcome in ("ok", "ok", "timeout", "cache_hit"):
            run(qu_cache.count(redis, outcome, today="2026-10-10"))
        run(qu_cache.count(redis, "ok", today="2026-10-11"))
        run(qu_cache.count(redis, "budget_late", group="search", today="2026-10-10"))
        self.assertEqual(redis.hashes["lamba:stats:qu:2026-10-10"], {"ok": 2, "timeout": 1, "cache_hit": 1})
        self.assertEqual(redis.hashes["lamba:stats:qu:2026-10-11"], {"ok": 1})
        self.assertEqual(redis.hashes["lamba:stats:search:2026-10-10"], {"budget_late": 1})
        self.assertEqual(set(redis.expiries.values()), {14 * 24 * 3600})


if __name__ == "__main__":
    unittest.main(verbosity=2)
