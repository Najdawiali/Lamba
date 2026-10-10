"""
Query Understanding Service — intent, category, brand and attribute extraction for a search query.

Three layers, cheapest first:
  1. rules (app/services/query_attributes.py): organic / gender / temperature / dietary from the query's
     words; instant, no network; always present, and they win over the model for their keys;
  2. a Redis cache of what the model answered for this query (app/services/qu_cache.py);
  3. the model, called once, with no retry, through its own circuit breaker, asking DeepInfra to reject
     at once ("fail_fast") instead of queueing when the model is at capacity.
Any failure falls back to the rules alone. The call never raises. Every call is counted by outcome in
Redis (HGETALL lamba:stats:qu:<YYYY-MM-DD>) and logged as "[QU] outcome=...".
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.config import settings
from app.services import qu_cache
from app.services.arabic_norm import normalize_query
from app.services.cache import get_redis
from app.services.http_pool import deepinfra_query_breaker
from app.services.llm import llm_adapter
from app.services.query_attributes import extract_query_attributes, merge_attributes
from app.services.service_tier import service_tier_fields

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

# Category-level terms that need LLM processing — broad discovery queries
# like "food", "kitchen", "sweets" that must be expanded into concrete products.
_CATEGORY_TERMS = {
    # Food & grocery categories
    "اكل", "أكل", "طعام", "مأكولات", "طبخ", "مطبخ", "بقالة", "سوبرماركت",
    "فواكه", "فاكهة", "خضار", "خضروات", "لحوم", "لحمة", "دواجن",
    "ألبان", "حليب", "أجبان", "مشروبات", "عصائر",
    "حلويات", "سكاكر", "شوكولاتة", "معجنات", "مخبوزات", "خبز",
    "بهارات", "توابل", "أعشاب", "زيوت",
    "تسالي", "سناكات", "مكسرات", "مجمدات", "معلبات",
    # Cooking / recipes
    "طبخة", "طبخات", "وصفة", "وصفات", "أكلة", "اكلة",
    # Kitchen & household
    "أواني", "صحون", "أدوات", "أثاث", "منظفات", "مواعين",
    # Electronics & tech
    "إلكترونيات", "الكترونيات", "أجهزة", "اجهزة", "موبايلات", "جوالات", "شواحن", "اكسسوارات",
    # Personal care & beauty
    "تجميل", "مكياج", "عطور", "عناية", "كريمات", "شامبو",
    # Services
    "خدمات", "صيانة", "تصليح", "تنظيف", "توصيل",
    # General retail
    "هدايا", "هدية", "قرطاسية", "مدرسية", "ملابس", "أحذية", "شنط",
    # Arabizi equivalents
    "akl", "tabkh", "matbakh", "5odra", "la7meh", "7alawiyyat",
    "makaroona", "snacks", "drinks", "food", "kitchen", "grocery",
    "cleaning", "electronics", "gifts", "beauty",
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

    # Category-level terms need LLM to classify intent and detect category
    if q in _CATEGORY_TERMS or any(w in _CATEGORY_TERMS for w in word_list):
        return True

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


# A change to the prompt invalidates cached answers.
_PROMPT_VERSION = hashlib.sha256(_QU_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:8]


def _outcome_from_reasons(reasons: List[str]) -> str:
    """Name the failure of a model call from the adapter's reasons (see LLMAdapter.error_sink)."""
    reason = reasons[-1] if reasons else "error"
    if reason == "timeout":
        return "timeout"
    if reason == "http_429":
        return "overloaded"
    if reason.startswith("http_"):
        return "http_error"
    if reason in ("breaker_open", "no_api_key"):
        return reason
    return "error"


def _parse_reply(reply: str) -> Optional[dict]:
    """The model's answer as the fields that are cached and used, or None if it is not a JSON object."""
    try:
        parsed = json.loads(reply)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None

    def text(name: str) -> Optional[str]:
        value = parsed.get(name)
        return value if isinstance(value, str) and value.strip() else None

    intent = parsed.get("intent")
    raw_attrs = parsed.get("attributes", {})
    if not isinstance(raw_attrs, dict):
        raw_attrs = {}
    return {
        "intent": intent if intent in ("product", "service") else None,
        "category_name": text("category_name"),
        "brand": text("brand"),
        "search_query": text("search_query"),
        "query_clean": text("query_clean"),
        "attributes": {k: v for k, v in raw_attrs.items() if k in _ALLOWED_ATTR_KEYS and v is not None},
    }


async def _redis_or_none() -> Any:
    try:
        return await get_redis()
    except Exception:
        return None


class QueryUnderstandingService:
    """Async Query Understanding: rules, then cache, then one model call. Never raises."""

    def __init__(self) -> None:
        self._inflight = 0

    def rules_only_intent(self, query_text: str) -> QueryIntent:
        """What search knows about a query with no model at all: the rule-based attributes."""
        norm_q = normalize_query(query_text)
        return QueryIntent(
            search_query=norm_q or query_text,
            attributes=extract_query_attributes(norm_q),
        )

    async def analyze_query_async(self, query_text: str) -> QueryIntent:
        started = time.monotonic()
        fallback = self.rules_only_intent(query_text)
        redis_client = await _redis_or_none()
        try:
            intent, outcome = await self._understand(query_text, fallback, redis_client)
        except Exception as exc:  # search must never fail because of query understanding
            logger.warning("[QU] unexpected failure, using the rules only: %r", exc)
            intent, outcome = fallback, "error"
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log = logger.debug if outcome == "not_needed" else logger.info
        log("[QU] outcome=%s ms=%d query=%r attrs=%s", outcome, elapsed_ms, query_text, intent.attributes)
        await qu_cache.count(redis_client, outcome)
        return intent

    async def _understand(self, query_text: str, fallback: QueryIntent, redis_client: Any):
        if not needs_llm(query_text):
            return fallback, "not_needed"

        key = qu_cache.cache_key(normalize_query(query_text), settings.query_llm_fallback_model, _PROMPT_VERSION)
        cached = await qu_cache.get(redis_client, key)
        if cached is not None:
            return self._intent_from(cached, fallback), "cache_hit"

        if deepinfra_query_breaker.should_skip():
            return fallback, "breaker_open"
        if self._inflight >= settings.query_llm_max_inflight:
            return fallback, "busy"

        reasons: List[str] = []
        extra = {"fail_fast": True} if settings.query_llm_fail_fast else {}
        extra.update(service_tier_fields(settings.query_llm_service_tier, allow_flex=False))
        self._inflight += 1
        try:
            reply = await llm_adapter.complete_chat(
                messages=[
                    {"role": "system", "content": _QU_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Query: {query_text}"},
                ],
                model=settings.query_llm_fallback_model,
                temperature=0.0,
                max_tokens=250,
                timeout=settings.query_llm_call_timeout_seconds,
                max_retries=1,  # one attempt: a 429 or a timeout is not retried inside the search's time budget
                breaker=deepinfra_query_breaker,
                error_sink=reasons,
                chat_template_kwargs={"enable_thinking": False},
                **extra,
            )
        finally:
            self._inflight -= 1
        if reply is None:
            return fallback, _outcome_from_reasons(reasons)

        fields = _parse_reply(reply)
        if fields is None:
            return fallback, "bad_json"
        await qu_cache.put(redis_client, key, fields, settings.cache_qu_ttl)
        return self._intent_from(fields, fallback), "ok"

    @staticmethod
    def _intent_from(fields: dict, fallback: QueryIntent) -> QueryIntent:
        return QueryIntent(
            intent=fields.get("intent"),
            category_name=fields.get("category_name"),
            brand=fields.get("brand"),
            search_query=fields.get("search_query") or fallback.search_query,
            query_clean=fields.get("query_clean"),
            attributes=merge_attributes(fields.get("attributes"), fallback.attributes),
        )


query_understanding_service = QueryUnderstandingService()
