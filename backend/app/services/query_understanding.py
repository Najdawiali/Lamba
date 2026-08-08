"""
Query Understanding Service — LLM-based intent, category, and brand extraction with needs_llm gatekeeper.
"""

from __future__ import annotations

import logging
import json
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.services.llm import llm_adapter
from app.services.arabic_norm import normalize_query

logger = logging.getLogger(__name__)

# Known single/two word product terms that skip LLM query understanding
_SIMPLE_PRODUCT_TERMS = {
    "حليب", "شاي", "قهوة", "عصير", "ماء", "خبز", "تمر", "بيض", "لبن", "جبنة", "زيت",
    "سكر", "ملح", "عسل", "تفاح", "موز", "برتقال", "خيار", "بصل", "ثوم", "بطاطا",
    "بندورة", "شوكولاتة", "بسكويت", "بيبسي", "كولا", "شيبس", "7aleeb", "7alib", "haleeb", "halib", "shay", "shai",
    "qahwa", "zayt", "zeit", "3asal", "khobz", "bandora", "batata", "khiyar",
}

_SERVICE_TRIGGERS = {
    "حلاقة", "تجميل", "غسيل", "تلميع", "صيانة", "تصليح", "سباكة", "كهرباء", "تنظيف",
    "مساج", "علاج", "تأجير", "توصيل", "قيادة", "مدرسة", "درس", "دروس", "تعليم", "خياطة",
    "7laqa", "hlaqa", "ghaseel", "ghasil", "sayara", "tanzif", "khiyata", "sbakeh", "kahraba",
}


def needs_llm(query_text: str | None) -> bool:
    """
    Gatekeeper heuristic: returns True only if query is complex, descriptive, or
    contains service/intent indicators. Simple product terms skip the LLM.
    """
    if not query_text:
        return False
    q = query_text.strip().lower()
    words = q.split()

    # Always run LLM if query contains service triggers
    if any(t in q for t in _SERVICE_TRIGGERS):
        return True

    # Multi-word queries (> 2 words) or long descriptive queries hit LLM
    if len(words) > 2:
        return True

    # Known simple single/two-word product queries skip LLM
    if q in _SIMPLE_PRODUCT_TERMS or (len(words) <= 2 and all(w in _SIMPLE_PRODUCT_TERMS for w in words)):
        return False

    # Default to False for short queries to preserve sub-second latency
    return len(words) >= 3


class QueryIntent(BaseModel):
    intent: Optional[str] = None           # "product", "service", or None
    category_name: Optional[str] = None    # Extracted category name
    brand: Optional[str] = None            # Extracted brand name
    search_query: str                      # Processed search query string


class QueryUnderstandingService:
    """Async Query Understanding service using LLMAdapter."""

    async def analyze_query_async(self, query_text: str) -> QueryIntent:
        """
        Extract intent, category, and brand from user query.
        Returns fallback QueryIntent immediately if needs_llm is False or if LLM fails.
        """
        norm_q = normalize_query(query_text)
        default_intent = QueryIntent(search_query=norm_q or query_text)

        if not needs_llm(query_text):
            logger.info(f"Query understanding skipped via needs_llm gatekeeper for '{query_text}'")
            return default_intent

        sys_prompt = (
            "You are a search query analyzer for an e-commerce & local services app in Jordan.\n"
            "Analyze the query and return ONLY a JSON object (no markdown, no thinking tags) with keys:\n"
            '  "intent": "product" | "service" | null,\n'
            '  "category_name": string | null,\n'
            '  "brand": string | null,\n'
            '  "search_query": string'
        )

        try:
            res = await llm_adapter.complete_chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"Query: {query_text}"},
                ],
                temperature=0.0,
                max_tokens=150,
                timeout=5.0,  # Strict 5s timeout to prevent latency spikes
            )

            if res:
                parsed = json.loads(res)
                intent_val = parsed.get("intent")
                if intent_val not in ("product", "service"):
                    intent_val = None

                return QueryIntent(
                    intent=intent_val,
                    category_name=parsed.get("category_name"),
                    brand=parsed.get("brand"),
                    search_query=parsed.get("search_query") or norm_q or query_text,
                )
        except Exception as e:
            logger.warning(f"Query understanding LLM analysis failed gracefully: {e}")

        return default_intent


query_understanding_service = QueryUnderstandingService()
