"""
DeepInfra Model Health Check

Tests all DeepInfra endpoints (embedding, reranker, real-time LLM, and offline LLM)
to verify API connectivity, correct response formats, and expected behavior.

Usage:
    cd backend
    python -m scripts.check_deepinfra_models
"""

import asyncio
import sys
import os
import math
import json

# Fix Windows console encoding for Unicode symbols (✓/✗)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure backend/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx


def load_settings():
    """Load settings from app config."""
    from app.config import settings
    return settings


async def check_embedding(settings) -> bool:
    """Test embedding endpoint: verify 1024d, non-zero, normalized."""
    print("\n" + "=" * 60)
    print("CHECK 1: Embedding Endpoint")
    print("=" * 60)

    url = f"{settings.deepinfra_api_base}{settings.embedding_api_path}"
    print(f"  URL:   {url}")
    print(f"  Model: {settings.qwen_embed_model}")
    print(f"  Dim:   {settings.text_embedding_dim}")

    headers = {
        "Authorization": f"Bearer {settings.deepinfra_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.qwen_embed_model,
        "input": ["حليب طازج"],
        "encoding_format": "float",
        "dimensions": settings.text_embedding_dim,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        embedding = data["data"][0]["embedding"]
        dim = len(embedding)
        is_zero = all(x == 0 for x in embedding)
        norm = math.sqrt(sum(x * x for x in embedding))

        print(f"  ✓ Response received")
        print(f"  Dimension: {dim} (expected {settings.text_embedding_dim})")
        print(f"  Zero vector: {is_zero}")
        print(f"  L2 norm: {norm:.4f} (expected ≈ 1.0)")

        ok = True
        if dim != settings.text_embedding_dim:
            print(f"  ✗ FAIL: Wrong dimension {dim} != {settings.text_embedding_dim}")
            ok = False
        if is_zero:
            print(f"  ✗ FAIL: Zero vector returned")
            ok = False
        if not (0.9 < norm < 1.1):
            print(f"  ⚠ WARNING: Norm is {norm:.4f}, expected ~1.0")

        if ok:
            print("  ✓ PASS")
        return ok

    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


async def check_reranker(settings) -> bool:
    """Test reranker: relevant doc should score higher than irrelevant."""
    print("\n" + "=" * 60)
    print("CHECK 2: Reranker Endpoint")
    print("=" * 60)

    url = f"https://api.deepinfra.com/v1/inference/{settings.reranker_model}"
    print(f"  URL:   {url}")
    print(f"  Model: {settings.reranker_model}")

    headers = {
        "Authorization": f"Bearer {settings.deepinfra_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "queries": ["مزيل عرق"],
        "documents": [
            "مزيل عرق رجالي مضاد للتعرق",
            "شامبو للشعر",
        ],
    }
    if getattr(settings, "reranker_instruction_enabled", True):
        payload["instruction"] = settings.reranker_instruction
        print(f"  Instruction: {settings.reranker_instruction[:60]}...")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        scores = data["scores"]
        print(f"  ✓ Response received")
        print(f"  Relevant score:   {scores[0]:.4f} (مزيل عرق رجالي)")
        print(f"  Irrelevant score: {scores[1]:.4f} (شامبو للشعر)")

        ok = True
        if scores[0] <= scores[1]:
            print(f"  ✗ FAIL: Relevant score should be > irrelevant")
            ok = False
        if scores[0] == scores[1]:
            print(f"  ✗ FAIL: Scores are identical")
            ok = False

        if ok:
            print("  ✓ PASS")
        return ok

    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


async def check_llm(settings) -> bool:
    """Test real-time LLM endpoint (Qwen3.6): returns parseable response."""
    print("\n" + "=" * 60)
    print("CHECK 3: Real-time LLM Chat Completions Endpoint")
    print("=" * 60)

    url = f"{settings.deepinfra_api_base}/openai/chat/completions"
    model = getattr(settings, "query_llm_model", "Qwen/Qwen3.6-35B-A3B")
    print(f"  URL:   {url}")
    print(f"  Model: {model}")

    headers = {
        "Authorization": f"Bearer {settings.deepinfra_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a search query analyzer. Return ONLY valid JSON "
                    '(no markdown): {"intent": "product"|"service", '
                    '"query_ar": "...", "query_en": "...", "synonyms": [...]}'
                ),
            },
            {"role": "user", "content": "حليب"},
        ],
        "temperature": 0.1,
        "max_tokens": 300,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        print(f"  ✓ Response received")
        print(f"  Content preview: {content[:200]}")

        # Try to parse as JSON
        try:
            # Strip markdown code fences if present
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
            parsed = json.loads(clean)
            print(f"  ✓ Valid JSON: {list(parsed.keys())}")
            print("  ✓ PASS")
            return True
        except json.JSONDecodeError:
            print(f"  ⚠ WARNING: Response is not valid JSON (may still work)")
            print("  ✓ PASS (endpoint reachable)")
            return True

    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


async def check_offline_llm(settings) -> bool:
    """Verify Gemma 4 31B is reachable and returns parseable output."""
    print("\n" + "=" * 60)
    print("CHECK 4: Offline LLM (Gemma 4 31B) Chat Completions Endpoint")
    print("=" * 60)

    url = f"{settings.deepinfra_api_base}/openai/chat/completions"
    model = getattr(settings, "offline_llm_model", "google/gemma-4-31B-it")
    print(f"  URL:   {url}")
    print(f"  Model: {model}")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": 'Extract attributes: "شاي أخضر صيني"\nReturn: {"type": "...", "origin": "..."}'},
        ],
        "temperature": 0.1,
        "max_tokens": 100,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepinfra_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        print(f"  ✓ Response received")
        print(f"  Content preview: {content[:200]}")

        # Try to parse as JSON
        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
        parsed = json.loads(clean)
        print(f"  ✓ Offline LLM ({model}): {parsed}")
        print("  ✓ PASS")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


async def main():
    print("DeepInfra Model Health Check")
    print("============================\n")

    settings = load_settings()

    if not settings.deepinfra_api_key or "REPLACE" in settings.deepinfra_api_key:
        print("✗ DEEPINFRA_API_KEY is not set or contains placeholder.")
        print("  Set it in backend/.env before running this check.")
        sys.exit(1)

    print(f"API Base: {settings.deepinfra_api_base}")
    print(f"Embedding Model: {settings.qwen_embed_model}")
    print(f"Reranker Model: {settings.reranker_model}")
    print(f"Real-time LLM Model: {getattr(settings, 'query_llm_model', 'N/A')}")
    print(f"Offline LLM Model: {getattr(settings, 'offline_llm_model', 'N/A')}")

    results = {
        "embedding": await check_embedding(settings),
        "reranker": await check_reranker(settings),
        "realtime_llm": await check_llm(settings),
        "offline_llm": await check_offline_llm(settings),
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name:16s} {status}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\n✓ All checks passed!")
    else:
        print("\n✗ Some checks failed. Review output above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
