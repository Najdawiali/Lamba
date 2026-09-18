"""
LLM Query Expansion Service — multi-query retrieval with Provider Abstraction.
Supports cross-lingual translation (Arabic <-> English) and domain-specific synonyms.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List, Optional

from app.config import settings
from app.services.llm import llm_adapter
from app.services.arabic_norm import normalize_query
from app.services.cache import get_cached_expansion, cache_expansion

logger = logging.getLogger(__name__)

EXPANSION_SYSTEM_PROMPT = """You are a bilingual e-commerce search assistant for Arabic and English retail in Jordan.
Your goal is to expand user queries into concrete product search terms.

The user may type in any Arabic dialect (Jordanian, Egyptian, Gulf, Levantine).
They may also describe a NEED or USE CASE rather than naming a product.

Rules:
1. If the query names a specific product → give translations and dialect variants.
   Example: "جاج" → ["دجاج", "chicken"]
   Example: "بطيخ" → ["watermelon", "بطيخ أحمر"]

2. If the query describes a NEED, USE CASE, or CATEGORY → list the concrete products that satisfy it.
   Example: "فواكه ممكن اعصرها" → ["برتقال", "مانجا", "تفاح", "بطيخ", "عصير طبيعي"]
   Example: "شي لوجع الراس" → ["بنادول", "مسكن ألم", "أدوية صداع"]
   Example: "مستلزمات مدرسية" → ["دفاتر", "أقلام", "حقيبة مدرسية", "قرطاسية"]
   Example: "حاجات للفطور" → ["خبز", "لبنة", "زيتون", "جبنة", "بيض"]

3. Keep brand names intact (Nike, Nescafe, Almarai) — do not translate proper nouns.
4. Output 2 to 5 concrete product search terms.
5. Respond strictly with a valid JSON list of strings.

Do not include explanations or markdown fences."""


# Placeholder / example tokens to reject so prompt examples are never extracted
_PLACEHOLDER_EXPANSIONS = {
    "term1", "term2", "term3", "synonym1", "synonym2", "example1", "example2",
    "query", "variant1", "variant2", "phrase1", "phrase2",
}


class QueryExpansionService:
    """Async LLM-based query expansion with provider abstraction."""

    async def expand_async(self, query: str) -> List[str]:
        """
        Return up to `settings.expansion_max_variants` paraphrases and translations of `query`.
        Returns [] immediately when disabled or when expansion_provider is 'disabled'.
        """
        if not getattr(settings, "enable_query_expansion", True):
            return []

        provider = getattr(settings, "expansion_provider", "api").lower()
        if provider == "disabled" or not query or not query.strip():
            return []

        # Check Redis L2 cache first (saves LLM call)
        cached = await get_cached_expansion(query.strip())
        if cached is not None:
            return cached

        if provider in ("api", "deepinfra"):
            messages = [
                {"role": "system", "content": EXPANSION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Expand this search query for cross-lingual retail search: {query.strip()}"},
            ]
            try:
                full_resp = await asyncio.wait_for(
                    llm_adapter.complete_chat_full(
                        messages=messages,
                        temperature=0.1,
                        max_tokens=200,
                        timeout=7.0,
                        max_retries=1,
                        chat_template_kwargs={"enable_thinking": False},
                    ),
                    timeout=8.0,
                )
                logger.debug(
                    f"[EXPANSION RESPONSE DUMP] {json.dumps(full_resp, ensure_ascii=False, default=str)[:2000]}"
                )
                if not full_resp or not full_resp.get("choices"):
                    return []

                choice = full_resp["choices"][0]
                message = choice.get("message", {})
                content = message.get("content") or ""
                reasoning_content = message.get("reasoning_content") or ""

                # Target text: content first, fallback to reasoning_content
                target_text = content if content.strip() else reasoning_content
                logger.debug(
                    f"[EXPANSION RAW EXTRACTED] content={repr(content)} reasoning_content={repr(reasoning_content)}"
                )

                # Look for JSON array [ ... ] in target_text
                match = re.search(r"\[.*?\]", target_text, re.DOTALL)
                if not match:
                    cleaned = re.sub(r"<think>.*?</think>", "", target_text, flags=re.DOTALL | re.IGNORECASE).strip()
                    cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned, flags=re.IGNORECASE)
                    cleaned = re.sub(r"\n?```$", "", cleaned)
                    match = re.search(r"\[.*?\]", cleaned, re.DOTALL)

                if match:
                    try:
                        parsed = json.loads(match.group(0))
                    except Exception:
                        parsed = None

                    if isinstance(parsed, list):
                        max_v = getattr(settings, "expansion_max_variants", 5)
                        cleaned_variants = []
                        for item in parsed:
                            if not isinstance(item, str):
                                continue
                            val = item.strip()
                            val_lower = val.lower()
                            # Discard query duplicates, empty strings, and prompt placeholder values
                            if (
                                val
                                and val_lower != query.strip().lower()
                                and val_lower not in _PLACEHOLDER_EXPANSIONS
                            ):
                                cleaned_variants.append(val)

                        if cleaned_variants:
                            final_variants = cleaned_variants[:max_v]
                            logger.debug(
                                "[EXPANSION PARSED] query=%r  parsed_variants=%s",
                                query, final_variants,
                            )
                            await cache_expansion(query.strip(), final_variants)
                            return final_variants

                logger.warning(f"[EXPANSION PARSE FAILED] query={query!r} target_text={target_text!r}")
            except Exception as e:
                logger.warning(f"Query expansion LLM call failed: {e}")
                return []

        logger.info(f"Query expansion provider '{provider}' is not supported.")
        return []


query_expansion_service = QueryExpansionService()

