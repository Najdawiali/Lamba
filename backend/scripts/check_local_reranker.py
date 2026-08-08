"""
Health check script for local Qwen3-Reranker-0.6B model.
Validates loading, score computation, normalization, and score separation
(relevant > irrelevant) for products and services.

Usage:
    python -m scripts.check_local_reranker
"""

import sys
import os
import time
import asyncio

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.config import settings
from app.services.local_reranker import local_reranker_provider


async def main():
    print("=" * 60)
    print("LOCAL RERANKER HEALTH CHECK (Qwen/Qwen3-Reranker-0.6B)")
    print("=" * 60)

    t0 = time.time()
    local_reranker_provider.load_model()
    load_time = time.time() - t0
    print(f"Model Load Time:    {load_time:.3f}s")
    print(f"Model Name:          {settings.reranker_model}")
    print(f"Device:              {local_reranker_provider._device}")
    print(f"Max Length:          {settings.local_rerank_max_length}")
    print(f"Batch Size:          {settings.local_rerank_batch_size}")
    print(f"Score Normalization: {settings.reranker_score_normalization}")

    # Test pairs
    product_query = "مزيل عرق"
    product_candidates = [
        {"id": "p1", "text": "مزيل عرق رجالي مضاد للتعرق", "prior_score": 0.50},
        {"id": "p2", "text": "شامبو للشعر مغذي ومطهر", "prior_score": 0.50},
    ]

    service_query = "مدرسه تدرس اللغه الفرنسيه"
    service_candidates = [
        {"id": "s1", "text": "مدرسة لتعليم اللغة الفرنسية للأطفال والكبار", "prior_score": 0.50},
        {"id": "s2", "text": "محل بيع أدوات مطبخ وأواني منزلية", "prior_score": 0.50},
    ]

    print("\n--- RERANKING PRODUCT TEST PAIRS ---")
    t1 = time.time()
    res_product = await local_reranker_provider.rerank(product_query, product_candidates, top_k=2)
    lat_product = (time.time() - t1) * 1000.0
    print(f"Latency: {lat_product:.2f}ms")

    p_scores = {}
    for item in res_product:
        p_scores[item["id"]] = item["rerank_score"]
        print(f"  [{item['id']}] '{item['text']}' -> rerank_score: {item['rerank_score']:.4f}, final_score: {item['final_score']:.4f}")

    print("\n--- RERANKING SERVICE TEST PAIRS ---")
    t2 = time.time()
    res_service = await local_reranker_provider.rerank(service_query, service_candidates, top_k=2)
    lat_service = (time.time() - t2) * 1000.0
    print(f"Latency: {lat_service:.2f}ms")

    s_scores = {}
    for item in res_service:
        s_scores[item["id"]] = item["rerank_score"]
        print(f"  [{item['id']}] '{item['text']}' -> rerank_score: {item['rerank_score']:.4f}, final_score: {item['final_score']:.4f}")

    print("\n--- ASSERTION VERIFICATION ---")
    # Product separation check
    assert p_scores["p1"] > p_scores["p2"], (
        f"Product score separation failed: relevant ({p_scores['p1']}) <= irrelevant ({p_scores['p2']})"
    )
    print(f"✔ Product Score Separation Passed ({p_scores['p1']:.4f} > {p_scores['p2']:.4f})")

    # Service separation check
    assert s_scores["s1"] > s_scores["s2"], (
        f"Service score separation failed: relevant ({s_scores['s1']}) <= irrelevant ({s_scores['s2']})"
    )
    print(f"✔ Service Score Separation Passed ({s_scores['s1']:.4f} > {s_scores['s2']:.4f})")

    # Range and non-zero checks
    all_scores = list(p_scores.values()) + list(s_scores.values())
    assert any(s > 0 for s in all_scores), "All reranker scores are zero!"
    assert len(set(all_scores)) > 1, "Reranker scores are all identical (degenerate)!"
    for s in all_scores:
        assert 0.0 <= s <= 1.0, f"Score {s} out of expected normalized range [0, 1]"

    print("\n" + "=" * 60)
    print("SUCCESS: LOCAL RERANKER HEALTH CHECK PASSED COMPLETELY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
