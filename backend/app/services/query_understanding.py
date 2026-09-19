"""
Query Understanding Service — LLM-based intent, category, brand, and attribute
extraction with needs_llm gatekeeper.
"""

from __future__ import annotations
import asyncio

import logging
import json
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.config import settings
from app.services.llm import llm_adapter
from app.services.arabic_norm import normalize_query

logger = logging.getLogger(__name__)

# Known single/two word product terms that skip LLM query understanding
_SIMPLE_PRODUCT_TERMS = {
    "حليب", "شاي", "قهوة", "عصير", "ماء", "خبز", "تمر", "بيض", "لبن", "جبنة", "زيت", "زيتون",
    "سكر", "ملح", "عسل", "تفاح", "موز", "برتقال", "خيار", "بصل", "ثوم", "بطاطا",
    "بندورة", "شوكولاتة", "بسكويت", "بيبسي", "كولا", "شيبس", "7aleeb", "7alib", "haleeb", "halib", "shay", "shai",
    "qahwa", "zayt", "zeit", "3asal", "khobz", "bandora", "batata", "khiyar",
}

_SERVICE_TRIGGERS = {
    "حلاقة", "تجميل", "غسيل", "تلميع", "صيانة", "تصليح", "سباكة", "كهرباء", "تنظيف",
    "مساج", "علاج", "تأجير", "توصيل", "قيادة", "مدرسة", "درس", "دروس", "تعليم", "خياطة",
    "7laqa", "hlaqa", "ghaseel", "ghasil", "sayara", "tanzif", "khiyata", "sbakeh", "kahraba",
}

# Attribute indicators — queries containing these words MUST go through
# LLM extraction even if short (e.g., "شاي أخضر" is only 2 words but
# carries an attribute that needs structured extraction).
_ATTRIBUTE_INDICATORS = {
    "أخضر", "أحمر", "أبيض", "أسمر", "أسود",  # colors
    "عضوي", "طبيعي", "بلدي",                  # organic/natural/local
    "قليل", "خالي", "بدون",                    # dietary (low/free/without)
    "بارد", "ساخن", "مثلج",                    # temperature
    "نسائي", "رجالي",                          # gender
    "كبير", "صغير", "وسط",                     # size
    "iced", "organic", "fresh", "low", "free",  # English attributes
}


def needs_llm(query_text: str | None) -> bool:
    """
    Gatekeeper heuristic: returns True only if query is complex, descriptive,
    contains service/intent indicators, or contains attribute modifiers that
    need structured extraction. Simple product terms skip the LLM.
    """
    if not query_text:
        return False
    q = query_text.strip().lower()
    words = set(q.split())

    # Query contains attribute indicators — MUST extract via LLM
    if words & _ATTRIBUTE_INDICATORS:
        return True

    # Always run LLM if query contains service triggers
    if any(t in q for t in _SERVICE_TRIGGERS):
        return True

    # Multi-word queries (> 2 words) or long descriptive queries hit LLM
    word_list = q.split()
    if len(word_list) > 2:
        return True

    # Known simple single/two-word product queries skip LLM
    if q in _SIMPLE_PRODUCT_TERMS or (len(word_list) <= 2 and all(w in _SIMPLE_PRODUCT_TERMS for w in word_list)):
        return False

    # 2-word queries with a non-simple modifier (e.g., "جبنة حلوم", "جنط مرسيدس")
    # likely carry type/brand info that needs structured extraction.
    return len(word_list) >= 2


_QU_SYSTEM_PROMPT = """You are a search query analyzer for a local marketplace in Jordan.
Analyze this search query and return ONLY a JSON object (no markdown, no thinking tags) with keys:

{
    "intent": "product" | "service" | null,
    "query_clean": "the core product/service term WITHOUT attribute modifiers",
    "category_name": string | null,
    "brand": string | null,
    "search_query": "the full normalized search string",
    "attributes": {
        "type": "sub-type if specified, else null",
        "color": "color if specified, else null",
        "flavor": "flavor if specified, else null",
        "origin": "origin if specified, else null",
        "organic": true | false | null,
        "temperature": "hot" | "cold" | "iced" | null,
        "dietary": "dietary restriction if specified, else null",
        "gender": "male" | "female" | null,
        "brand": "brand name if specified, else null"
    }
}

IMPORTANT:
- query_clean removes attribute words so semantic search focuses on the product type
- attributes become hard filters in the database
- If no attributes are present, return empty attributes {}
- Only include non-null attribute values in the output
- Do NOT guess attributes that aren't in the query

IMPORTANT — Do NOT extract these as attributes. They are search contexts, not product properties:
- Meal times: فطور, غداء, عشاء, سحور (breakfast, lunch, dinner, suhoor)
- Occasions: هدية, حفلة, ضيوف, رمضان, عيد (gift, party, guests, ramadan, eid)
- Activities: تنظيف, طبخ, سفر, رحلة, مدرسة (cleaning, cooking, travel, school)
- People: أطفال, بيبي, عائلة (kids, baby, family)

These should be part of query_clean for semantic search, NOT in attributes.

Correct examples:
- "بدي شي للفطور" → {"intent": "product", "query_clean": "فطور", "attributes": {}}
- "هدية لصاحبي" → {"intent": "product", "query_clean": "هدية", "attributes": {}}
- "شي حلو للضيوف" → {"intent": "product", "query_clean": "حلويات ضيوف", "attributes": {}}
- "أرخص شاي أخضر" → {"intent": "product", "query_clean": "شاي", "attributes": {"type": "أخضر"}}
- "شاي أخضر" → {"intent": "product", "query_clean": "شاي", "attributes": {"type": "أخضر"}}
- "حليب قليل الدسم" → {"intent": "product", "query_clean": "حليب", "attributes": {"dietary": "قليل الدسم"}}

ONLY extract attributes that are physical/measurable properties of the product itself:
type, color, flavor, origin, organic, temperature, dietary, gender, brand, size, material

Examples:
- "شاي أخضر" → {"intent": "product", "query_clean": "شاي", "category_name": null, "brand": null, "search_query": "شاي أخضر", "attributes": {"type": "أخضر"}}
- "شاي أحمر" → {"intent": "product", "query_clean": "شاي", "category_name": null, "brand": null, "search_query": "شاي أحمر", "attributes": {"type": "أحمر"}}
- "iced tea" → {"intent": "product", "query_clean": "tea", "category_name": null, "brand": null, "search_query": "iced tea", "attributes": {"temperature": "cold"}}
- "زيت زيتون عضوي" → {"intent": "product", "query_clean": "زيت زيتون", "category_name": null, "brand": null, "search_query": "زيت زيتون عضوي", "attributes": {"organic": true}}
- "حليب قليل الدسم" → {"intent": "product", "query_clean": "حليب", "category_name": null, "brand": null, "search_query": "حليب قليل الدسم", "attributes": {"dietary": "قليل الدسم"}}
- "صالون نسائي" → {"intent": "service", "query_clean": "صالون", "category_name": null, "brand": null, "search_query": "صالون نسائي", "attributes": {"gender": "female"}}
- "جنط سيارة مرسيدس" → {"intent": "product", "query_clean": "جنط سيارة", "category_name": null, "brand": "مرسيدس", "search_query": "جنط سيارة مرسيدس", "attributes": {"brand": "مرسيدس"}}
- "حليب" → {"intent": "product", "query_clean": "حليب", "category_name": null, "brand": null, "search_query": "حليب", "attributes": {}}"""


class QueryIntent(BaseModel):
    intent: Optional[str] = None           # "product", "service", or None
    category_name: Optional[str] = None    # Extracted category name
    brand: Optional[str] = None            # Extracted brand name
    search_query: str                      # Processed search query string
    query_clean: Optional[str] = None      # Core product term without attribute modifiers
    attributes: Dict[str, Any] = {}        # Extracted structured attributes for JSONB filtering


# Allowed attribute keys — anything else from LLM is discarded
_ALLOWED_ATTR_KEYS = {
    "type", "color", "flavor", "origin", "organic", "size",
    "brand", "temperature", "dietary", "material", "gender",
}


class QueryUnderstandingService:
    """Async Query Understanding service using LLMAdapter."""

    async def analyze_query_async(self, query_text: str) -> QueryIntent:
        """
        Extract intent, category, brand, and structured attributes from user query.
        Returns fallback QueryIntent immediately if needs_llm is False or if LLM fails.
        """
        norm_q = normalize_query(query_text)
        default_intent = QueryIntent(search_query=norm_q or query_text)

        if not needs_llm(query_text):
            logger.info(f"Query understanding skipped via needs_llm gatekeeper for '{query_text}'")
            return default_intent

        try:
            # Hard 6s deadline — if the LLM+retries exceed this, bail out
            # rather than letting the user wait 17s for 3 failed retries.
            res = await asyncio.wait_for(
                llm_adapter.complete_chat(
                    messages=[
                        {"role": "system", "content": _QU_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Query: {query_text}"},
                    ],
                    model=settings.query_llm_fallback_model,
                    temperature=0.0,
                    max_tokens=250,
                    timeout=3.0,
                    max_retries=2,
                    chat_template_kwargs={"enable_thinking": False},
                ),
                timeout=4.0,
            )

            if res:
                parsed = json.loads(res)
                intent_val = parsed.get("intent")
                if intent_val not in ("product", "service"):
                    intent_val = None

                # Extract and whitelist attributes
                raw_attrs = parsed.get("attributes", {})
                if not isinstance(raw_attrs, dict):
                    raw_attrs = {}
                filtered_attrs = {
                    k: v for k, v in raw_attrs.items()
                    if k in _ALLOWED_ATTR_KEYS and v is not None
                }

                return QueryIntent(
                    intent=intent_val,
                    category_name=parsed.get("category_name"),
                    brand=parsed.get("brand"),
                    search_query=parsed.get("search_query") or norm_q or query_text,
                    query_clean=parsed.get("query_clean"),
                    attributes=filtered_attrs,
                )
        except Exception as e:
            logger.warning(f"Query understanding LLM analysis failed gracefully: {e}")

        return default_intent


query_understanding_service = QueryUnderstandingService()
