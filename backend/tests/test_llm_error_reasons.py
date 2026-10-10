"""
Tests for the failure reasons of app.services.llm (error_sink) and the query-understanding breaker.

The real llm.py and http_pool.py are imported against stand-ins for httpx and app.config
(tests/stub_modules.py), with a fake HTTP client: no network, nothing installed.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stub_modules import make_config, make_httpx, stubbed  # noqa: E402

FRESH = ("app.services.http_pool", "app.services.llm")


class FakeResponse:
    def __init__(self, httpx, status=200, data=None, text=""):
        self.httpx, self.status_code, self._data, self.text = httpx, status, data, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise self.httpx.HTTPStatusError("error", response=self)

    def json(self):
        return self._data


class FakeClient:
    """post() hands out the prepared outcomes in order: a response, or an exception to raise."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestErrorReasons(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.httpx = make_httpx()
        self.stack = stubbed({"httpx": self.httpx, "app.config": make_config()}, fresh=FRESH)
        self.stack.__enter__()
        from app.services import http_pool, llm
        self.llm, self.http_pool = llm, http_pool
        self.adapter = llm.LLMAdapter()
        self.breaker = http_pool.CircuitBreaker(failure_threshold=99)
        sleeper = mock.patch.object(llm.asyncio, "sleep", new=mock.AsyncMock())
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def tearDown(self):
        self.stack.__exit__(None, None, None)

    def use(self, *outcomes):
        client = FakeClient(outcomes)
        patcher = mock.patch.object(self.llm, "get_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    def ok(self, content="{}"):
        return FakeResponse(self.httpx, 200, {"choices": [{"message": {"content": content}}]})

    def status(self, code, text="busy"):
        return FakeResponse(self.httpx, code, text=text)

    async def post(self, sink, max_retries=1, **kw):
        return await self.adapter._post_with_retry(
            "https://x/chat", {"model": "m"}, timeout=3.0, max_retries=max_retries,
            breaker=self.breaker, error_sink=sink, **kw)

    async def test_a_timeout_is_reported_as_a_timeout(self):
        client = self.use(self.httpx.ReadTimeout(""))
        sink = []
        self.assertIsNone(await self.post(sink))
        self.assertEqual((sink, len(client.calls)), (["timeout"], 1))

    async def test_a_429_is_reported_and_one_attempt_means_no_retry(self):
        client = self.use(self.status(429, '{"error":{"code":"engine_overloaded"}}'), self.ok())
        sink = []
        self.assertIsNone(await self.post(sink, max_retries=1))
        self.assertEqual((sink, len(client.calls)), (["http_429"], 1))  # the second outcome was never used

    async def test_with_more_attempts_a_429_is_still_retried_for_the_other_callers(self):
        client = self.use(self.status(429), self.status(429))
        sink = []
        self.assertIsNone(await self.post(sink, max_retries=2))
        self.assertEqual((sink, len(client.calls)), (["http_429", "http_429"], 2))

    async def test_a_server_error_then_success_returns_the_payload(self):
        client = self.use(self.status(503), self.ok('{"a": 1}'))
        sink = []
        result = await self.post(sink, max_retries=2)
        self.assertEqual(result["choices"][0]["message"]["content"], '{"a": 1}')
        self.assertEqual((sink, len(client.calls)), (["http_503"], 2))

    async def test_a_client_error_is_not_retried(self):
        client = self.use(self.status(400), self.ok())
        sink = []
        self.assertIsNone(await self.post(sink, max_retries=3))
        self.assertEqual((sink, len(client.calls)), (["http_400"], 1))

    async def test_any_other_exception_is_reported_as_an_error(self):
        self.use(RuntimeError("boom"))
        sink = []
        self.assertIsNone(await self.post(sink))
        self.assertEqual(sink, ["error"])

    async def test_a_missing_key_and_an_open_breaker_are_reported_without_a_call(self):
        client = self.use(self.ok())
        sink = []
        with mock.patch.object(self.adapter, "api_key", ""):
            self.assertIsNone(await self.post(sink))
        self.assertEqual(sink, ["no_api_key"])

        breaker = self.http_pool.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        breaker.record_failure()
        sink = []
        self.assertIsNone(await self.adapter._post_with_retry("https://x", {}, breaker=breaker, error_sink=sink))
        self.assertEqual(sink, ["breaker_open"])
        self.assertEqual(client.calls, [])

    async def test_the_sink_is_optional(self):
        self.use(self.status(500))
        self.assertIsNone(await self.adapter._post_with_retry("https://x", {}, max_retries=1, breaker=self.breaker))

    async def test_failures_count_against_the_breaker_that_was_passed(self):
        self.use(self.status(429), self.status(429))
        shared = self.http_pool.deepinfra_llm_breaker
        before = shared.failure_count
        await self.post([], max_retries=2)
        self.assertEqual(self.breaker.failure_count, 2)
        self.assertEqual(shared.failure_count, before)

    async def test_a_429_listed_as_uncounted_does_not_count_against_the_breaker(self):
        # "Model busy" is capacity, not an outage: ten of them must leave the breaker closed
        breaker = self.http_pool.CircuitBreaker(failure_threshold=5, cooldown_seconds=60)
        self.use(*[self.status(429) for _ in range(10)])
        for _ in range(10):
            sink = []
            self.assertIsNone(await self.adapter._post_with_retry(
                "https://x", {}, max_retries=1, breaker=breaker, error_sink=sink, uncounted_statuses=(429,)))
            self.assertEqual(sink, ["http_429"])               # still reported as a failure
        self.assertEqual((breaker.failure_count, breaker.should_skip()), (0, False))

    async def test_the_same_429s_open_the_breaker_when_they_are_counted(self):
        breaker = self.http_pool.CircuitBreaker(failure_threshold=5, cooldown_seconds=60)
        self.use(*[self.status(429) for _ in range(10)])
        for _ in range(5):
            await self.adapter._post_with_retry("https://x", {}, max_retries=1, breaker=breaker)
        self.assertTrue(breaker.should_skip())                 # the default is unchanged

    async def test_timeouts_and_server_errors_still_count_when_429_is_uncounted(self):
        breaker = self.http_pool.CircuitBreaker(failure_threshold=99)
        self.use(self.httpx.ReadTimeout(""), self.status(503), self.status(500), RuntimeError("boom"), self.status(429))
        for _ in range(5):
            await self.adapter._post_with_retry("https://x", {}, max_retries=1, breaker=breaker, uncounted_statuses=(429,))
        self.assertEqual(breaker.failure_count, 4)             # everything except the 429

    async def test_a_listed_status_is_still_retried_when_there_are_attempts_left(self):
        breaker = self.http_pool.CircuitBreaker(failure_threshold=99)
        client = self.use(self.status(429), self.ok('{"a": 1}'))
        result = await self.adapter._post_with_retry(
            "https://x", {}, max_retries=2, breaker=breaker, uncounted_statuses=(429,))
        self.assertIsNotNone(result)
        self.assertEqual((len(client.calls), breaker.failure_count), (2, 0))

    async def test_uncounted_statuses_pass_through_the_three_chat_methods(self):
        breaker = self.http_pool.CircuitBreaker(failure_threshold=99)
        for method in ("complete_chat_full", "complete_chat_raw", "complete_chat"):
            self.use(self.status(429))
            await getattr(self.adapter, method)(messages=[], max_retries=1, breaker=breaker, uncounted_statuses=(429,))
        self.assertEqual(breaker.failure_count, 0)

    async def test_extra_request_fields_reach_the_payload_but_the_sink_does_not(self):
        client = self.use(self.ok('{"intent": "product"}'))
        sink = []
        text = await self.adapter.complete_chat(
            messages=[{"role": "user", "content": "q"}], model="google/gemma-4-26B-A4B-it", max_retries=1,
            breaker=self.breaker, error_sink=sink, fail_fast=True, chat_template_kwargs={"enable_thinking": False})
        self.assertEqual(text, '{"intent": "product"}')
        payload = client.calls[0]["json"]
        self.assertIs(payload["fail_fast"], True)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertNotIn("error_sink", payload)
        self.assertNotIn("uncounted_statuses", payload)
        self.assertEqual(sink, [])

    async def test_failures_pass_through_the_three_chat_methods(self):
        for method in ("complete_chat_full", "complete_chat_raw", "complete_chat"):
            self.use(self.status(429))
            sink = []
            result = await getattr(self.adapter, method)(
                messages=[], max_retries=1, breaker=self.breaker, error_sink=sink)
            self.assertIsNone(result, method)
            self.assertEqual(sink, ["http_429"], method)

    def test_query_understanding_has_a_breaker_of_its_own(self):
        pool = self.http_pool
        self.assertIsNot(pool.deepinfra_query_breaker, pool.deepinfra_llm_breaker)
        self.assertIsNot(pool.deepinfra_query_breaker, pool.deepinfra_catalog_breaker)
        self.assertEqual((pool.deepinfra_query_breaker.failure_threshold, pool.deepinfra_query_breaker.cooldown_seconds), (5, 20))


if __name__ == "__main__":
    unittest.main(verbosity=2)
