import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.arabic_norm import normalize_arabic
from app.api.search_v1 import needs_expansion
from app.services.cache import lookup_synonym, lookup_synonyms_multi, get_redis


def test_needs_expansion_with_synonyms():
    # 1-word query with synonym match -> should skip LLM expansion
    assert needs_expansion("عيش", "ar", has_synonym=True) is False
    assert needs_expansion("جاج", "ar", has_synonym=True) is False

    # 2-word query with synonym match -> should skip LLM expansion
    assert needs_expansion("عيش بلدي", "ar", has_synonym=True) is False
    assert needs_expansion("بدي عيش", "ar", has_synonym=True) is False

    # Intent query without synonym -> should expand
    assert needs_expansion("بدي عيش", "ar", has_synonym=False) is True
    assert needs_expansion("وين الاقي جاج", "ar", has_synonym=False) is True

    # 3+ word complex query -> should still expand even if synonym present
    assert needs_expansion("وين الاقي جاج طازج", "ar", has_synonym=True) is True
    assert needs_expansion("عيش فينو طازج سخن", "ar", has_synonym=True) is True

    # 2-word Latin query -> expands if no synonym, skips if synonym found
    assert needs_expansion("fresh bread", "latin", has_synonym=False) is True
    assert needs_expansion("fresh bread", "latin", has_synonym=True) is False



async def test_synonym_cache_lookup_async():
    r = await get_redis()
    # Populate test entries in Redis
    await r.hset("lamba:synonyms", mapping={
        normalize_arabic("عيش"): normalize_arabic("خبز"),
        normalize_arabic("جاج"): normalize_arabic("دجاج"),
        normalize_arabic("فراخ"): normalize_arabic("دجاج"),
    })

    # Single lookup
    syn = await lookup_synonym("عيش")
    assert syn == normalize_arabic("خبز")

    syn_miss = await lookup_synonym("كلمة_غير_موجودة_123")
    assert syn_miss is None

    # Multi lookup
    multi_res = await lookup_synonyms_multi(["عيش", "جاج", "كلمة_غير_موجودة"])
    assert "عيش" in multi_res
    assert multi_res["عيش"] == normalize_arabic("خبز")
    assert "جاج" in multi_res
    assert multi_res["جاج"] == normalize_arabic("دجاج")
    assert "كلمة_غير_موجودة" not in multi_res


class TestSynonymTable(unittest.TestCase):
    def test_needs_expansion(self):
        test_needs_expansion_with_synonyms()

    def test_cache_lookup(self):
        asyncio.run(test_synonym_cache_lookup_async())


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
