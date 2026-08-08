"""
Health check script for local Qwen3-Embedding-0.6B model.
Validates loading, vector dimension (1024), L2 normalization (norm ≈ 1.0),
non-zero vectors, and similarity properties.

Usage:
    python -m scripts.check_local_embedding
"""

import os
import sys

# Limit OpenBLAS / OMP threads before numpy/torch import on Windows
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import time
import asyncio
import numpy as np

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.config import settings
from app.services.local_embedding import local_embedding_provider


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


async def main():
    print("=" * 60)
    print("LOCAL EMBEDDING HEALTH CHECK (Qwen/Qwen3-Embedding-0.6B)")
    print("=" * 60)

    t0 = time.time()
    local_embedding_provider.load_model()
    load_time = time.time() - t0
    print(f"Model Load Time: {load_time:.3f}s")
    print(f"Model Name:       {settings.qwen_embed_model}")
    print(f"Target Dimension: {settings.text_embedding_dim}")
    print(f"Device:           {local_embedding_provider._device}")

    test_queries = [
        "مزيل عرق",
        "مدرسه تدرس اللغه الفرنسيه",
        "deodorant",
        "madrase fransi",
        "7aleeb",
    ]

    embeddings = {}
    print("\n--- INFERENCE TESTS ---")
    for q in test_queries:
        t1 = time.time()
        vec_list = await local_embedding_provider.embed_query(q)
        lat = (time.time() - t1) * 1000.0
        vec = np.asarray(vec_list, dtype=np.float32)

        norm = np.linalg.norm(vec)
        is_zero = not bool(vec.any())
        embeddings[q] = vec

        print(f"\nQuery: '{q}'")
        print(f"  Latency:    {lat:.2f}ms")
        print(f"  Dimension:  {len(vec)}")
        print(f"  Vector Norm:{norm:.6f}")
        print(f"  Is Zero:    {is_zero}")
        print(f"  First 5:    {vec[:5].round(4).tolist()}")

        # Assertions per item
        assert len(vec) == 1024, f"Expected dimension 1024, got {len(vec)}"
        assert not is_zero, f"Vector for '{q}' is all zeros!"
        assert abs(norm - 1.0) < 1e-3, f"Vector norm for '{q}' is {norm}, expected ~1.0"

    print("\n--- CONSISTENCY & SIMILARITY TESTS ---")
    # Determinism check
    vec_repeat = await local_embedding_provider.embed_query("مزيل عرق")
    sim_self = cosine_similarity(embeddings["مزيل عرق"], np.asarray(vec_repeat))
    print(f"Self-similarity ('مزيل عرق' vs repeat): {sim_self:.6f}")
    assert sim_self > 0.999, f"Determinism failure: self-similarity is {sim_self}"

    # Related pair check (Arabic vs English deodorant)
    sim_deod = cosine_similarity(embeddings["مزيل عرق"], embeddings["deodorant"])
    print(f"Related Pair ('مزيل عرق' vs 'deodorant'): {sim_deod:.4f}")
    assert sim_deod > 0.30, f"Related terms similarity too low: {sim_deod} <= 0.30"

    # Related pair check (Arabic vs Arabizi school)
    sim_school = cosine_similarity(embeddings["مدرسه تدرس اللغه الفرنسيه"], embeddings["madrase fransi"])
    print(f"Related Pair ('مدرسه...' vs 'madrase fransi'): {sim_school:.4f}")
    assert sim_school > 0.30, f"Related terms similarity too low: {sim_school} <= 0.30"

    # Unrelated pair collapse check
    sim_unrelated = cosine_similarity(embeddings["مزيل عرق"], embeddings["مدرسه تدرس اللغه الفرنسيه"])
    print(f"Unrelated Pair ('مزيل عرق' vs 'مدرسه...'): {sim_unrelated:.4f}")
    assert sim_unrelated < 0.95, f"Vector collapse detected: unrelated similarity {sim_unrelated} >= 0.95"

    print("\n" + "=" * 60)
    print("SUCCESS: LOCAL EMBEDDING HEALTH CHECK PASSED COMPLETELY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
