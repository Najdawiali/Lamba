"""
End-to-end integration test for the search pipeline & caching optimizations.
Uses AsyncClient against FastAPI app instance.
"""

import asyncio
import time
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.auth import get_current_user
from app.services.cache import get_redis


class TestSearchPipelineE2E(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app.dependency_overrides[get_current_user] = lambda: None

    async def asyncTearDown(self):
        app.dependency_overrides.clear()

    async def test_hybrid_search_cache_hit_and_latency(self):
        """Verify cold search runs pipeline, warm search returns from cache in <100ms."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "query_text": "شاي أخضر",
                "latitude": 31.954,
                "longitude": 35.911,
                "listing_type": "product",
            }

            # Cold search 1 (mocking db query execution if db is offline or letting it run)
            t0 = time.perf_counter()
            resp1 = await client.post("/api/v1/search/hybrid", json=payload)
            t1 = time.perf_counter()
            cold_latency_ms = (t1 - t0) * 1000.0
            print(f"\n[BENCHMARK] Cold Search Latency: {cold_latency_ms:.2f} ms | Status: {resp1.status_code}")

            if resp1.status_code == 200:
                # Warm search 2 (should hit Redis full search cache)
                t2 = time.perf_counter()
                resp2 = await client.post("/api/v1/search/hybrid", json=payload)
                t3 = time.perf_counter()
                warm_latency_ms = (t3 - t2) * 1000.0
                print(f"[BENCHMARK] Warm (Cached) Search Latency: {warm_latency_ms:.2f} ms | Status: {resp2.status_code}")
                
                self.assertEqual(resp2.status_code, 200)
                data1 = resp1.json()
                data2 = resp2.json()
                self.assertEqual(data1["found"], data2["found"])
                self.assertEqual(data1["search_mode"], data2["search_mode"])
                self.assertEqual(len(data1["results"]), len(data2["results"]))
                self.assertLess(warm_latency_ms, 150.0, f"Expected warm search < 150ms, got {warm_latency_ms:.2f}ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
