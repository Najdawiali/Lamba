"""
Tests for app.services.search_budget: query understanding in parallel with the first embedding under a
time budget, with REAL asyncio timings (tens of milliseconds). No network, no database.
"""

import asyncio
import gc
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import search_budget as sb


def run(coro):
    return asyncio.run(coro)


class Probe:
    """An awaitable that finishes after `delay` seconds with `value` (or raises it), noting when."""

    def __init__(self, delay, value=None):
        self.delay, self.value, self.finished = delay, value, None

    async def __call__(self):
        await asyncio.sleep(self.delay)
        self.finished = True
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class TestUnderstandWithinBudget(unittest.TestCase):
    def test_both_fast_the_model_answer_is_used(self):
        result = run(sb.understand_within_budget(Probe(0.01, "vec")(), Probe(0.02, "intent")(), 0.5))
        self.assertEqual((result.embedding, result.intent, result.outcome), ("vec", "intent", "answered"))

    def test_the_two_run_at_the_same_time_not_one_after_the_other(self):
        started = time.monotonic()
        result = run(sb.understand_within_budget(Probe(0.15, "vec")(), Probe(0.15, "intent")(), 1.0))
        elapsed = time.monotonic() - started
        self.assertEqual(result.outcome, "answered")
        self.assertLess(elapsed, 0.27)  # 0.30 s if they ran one after the other

    def test_search_waits_for_a_slower_model_but_only_within_the_budget(self):
        started = time.monotonic()
        result = run(sb.understand_within_budget(Probe(0.02, "vec")(), Probe(0.15, "intent")(), 0.5))
        elapsed = time.monotonic() - started
        self.assertEqual(result.outcome, "answered")
        self.assertGreaterEqual(elapsed, 0.14)
        self.assertGreaterEqual(result.waited_ms, 100)   # it waited for the model after the embedding
        self.assertLess(result.embed_ms, 100)

    def test_a_late_model_never_holds_search_beyond_the_budget(self):
        qu = Probe(0.4, "intent")
        started = time.monotonic()

        async def scenario():
            result = await sb.understand_within_budget(Probe(0.02, "vec")(), qu(), 0.12)
            return result, time.monotonic() - started, qu.finished

        result, elapsed, finished_when_returned = run(scenario())
        self.assertEqual((result.embedding, result.intent, result.outcome), ("vec", None, "late"))
        self.assertLess(elapsed, 0.25)          # the model needed 0.4 s
        self.assertIsNone(finished_when_returned)

    def test_the_budget_is_counted_from_the_start_so_a_slow_embedding_leaves_no_extra_wait(self):
        started = time.monotonic()
        result = run(sb.understand_within_budget(Probe(0.2, "vec")(), Probe(0.3, "intent")(), 0.1))
        elapsed = time.monotonic() - started
        self.assertEqual(result.outcome, "late")
        self.assertLess(elapsed, 0.27)           # the embedding's own 0.2 s, no waiting on top
        self.assertLessEqual(result.waited_ms, 20)

    def test_a_zero_budget_means_never_wait_for_the_model(self):
        result = run(sb.understand_within_budget(Probe(0.02, "vec")(), Probe(0.05, "intent")(), 0))
        self.assertEqual((result.outcome, result.intent), ("late", None))

    def test_a_late_answer_still_lands_in_the_background(self):
        qu = Probe(0.2, "intent")

        async def scenario():
            result = await sb.understand_within_budget(Probe(0.01, "vec")(), qu(), 0.05)
            assert qu.finished is None and len(sb._background) == 1
            await asyncio.sleep(0.3)               # the request is over; the model call goes on
            return result, qu.finished, len(sb._background)

        result, finished, background_left = run(scenario())
        self.assertEqual(result.outcome, "late")
        self.assertTrue(finished)                   # e.g. this is when the cache gets written
        self.assertEqual(background_left, 0)

    def test_a_late_failure_is_swallowed_quietly(self):
        problems = []

        async def scenario():
            asyncio.get_running_loop().set_exception_handler(lambda loop, context: problems.append(context))
            result = await sb.understand_within_budget(Probe(0.01, "vec")(), Probe(0.15, RuntimeError("late boom"))(), 0.03)
            await asyncio.sleep(0.25)
            gc.collect()
            return result

        result = run(scenario())
        self.assertEqual(result.outcome, "late")
        self.assertEqual(problems, [])

    def test_a_failed_model_call_is_reported_not_raised(self):
        result = run(sb.understand_within_budget(Probe(0.01, "vec")(), Probe(0.02, RuntimeError("boom"))(), 0.5))
        self.assertEqual((result.embedding, result.intent, result.outcome), ("vec", None, "failed"))

    def test_a_failed_embedding_comes_back_as_the_exception_and_does_not_hide_the_model(self):
        error = RuntimeError("no embedding")
        result = run(sb.understand_within_budget(Probe(0.01, error)(), Probe(0.02, "intent")(), 0.5))
        self.assertIs(result.embedding, error)
        self.assertEqual((result.intent, result.outcome), ("intent", "answered"))

    def test_cancelling_the_request_cancels_both(self):
        embed, qu = Probe(0.3, "vec"), Probe(0.3, "intent")

        async def scenario():
            task = asyncio.ensure_future(sb.understand_within_budget(embed(), qu(), 1.0))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.4)

        run(scenario())
        self.assertIsNone(embed.finished)
        self.assertIsNone(qu.finished)


class TestAssembleEmbeddings(unittest.TestCase):
    def assemble(self, texts, known):
        calls = []

        async def embed_batch(missing):
            calls.append(list(missing))
            return [f"vec:{t}" for t in missing]

        return run(sb.assemble_embeddings(texts, known, embed_batch)), calls

    def test_the_first_embedding_is_reused_and_only_the_rest_is_embedded_in_one_batch(self):
        vectors, calls = self.assemble(["شاي", "شاي اخضر", "tea"], {"شاي اخضر": "first"})
        self.assertEqual(vectors, ["vec:شاي", "first", "vec:tea"])      # in the order of the texts
        self.assertEqual(calls, [["شاي", "tea"]])

    def test_nothing_is_embedded_when_everything_is_known(self):
        vectors, calls = self.assemble(["a"], {"a": "known"})
        self.assertEqual((vectors, calls), (["known"], []))

    def test_a_missing_first_embedding_is_simply_embedded_with_the_rest(self):
        vectors, calls = self.assemble(["a", "b"], {})
        self.assertEqual((vectors, calls), (["vec:a", "vec:b"], [["a", "b"]]))

    def test_a_text_without_a_vector_is_left_out(self):
        async def embed_batch(missing):
            return ["vec:a"]            # the provider returned fewer vectors than asked

        vectors = run(sb.assemble_embeddings(["a", "b"], {}, embed_batch))
        self.assertEqual(vectors, ["vec:a"])

    def test_no_texts(self):
        self.assertEqual(self.assemble([], {})[0], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
