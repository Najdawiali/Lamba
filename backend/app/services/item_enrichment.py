"""
Search-term enrichment + document embedding for catalog items.

Single implementation used by every path that creates or renames a product
(merchant manual add, rename, CSV upload, catalog import, batch re-enrichment),
so the embedded text is always built the same way.

ENRICHMENT_PROMPT is the production prompt that powers the current search,
moved here unchanged from scripts/enrich_search_terms.py (scripts/ is not in the
Docker image, so the old import failed silently in production). A Jordan-focused
v2 is planned after launch and must be evaluated before replacing it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.services.arabic_norm import normalize_arabic
from app.services.embedding import embedding_service
from app.services.http_pool import deepinfra_catalog_breaker
from app.services.llm import llm_adapter

logger = logging.getLogger(__name__)

ENRICHMENT_PROMPT = """You are a search index builder for a retail marketplace serving ALL Arab countries.

Given this product:
Name: {name}
Description: {description}  
Category: {category}

Generate a comprehensive, comma-separated list of search terms. Include ALL of the following:

1. Formal Arabic (فصحى) name and synonyms
2. English name and common English variants
3. Arabizi/Franco-Arab spellings (e.g., 7aleeb, za3tar, knafeh, shawarma, falafel, labneh, mansaf)
4. CRITICAL — Dialectal Arabic from EVERY major dialect. Be thorough:
   Jordanian/Palestinian: e.g., دجاج→جاج, ثوم→توم, سكر→شكر, بطاطس→بطاطا, خبز→خبز كماج
   Egyptian: e.g., دجاج→فراخ, خبز→عيش, طماطم→أوطة, بصل→بصلة, ليمون→لمون, فاصوليا→فصوليا
   Gulf/Saudi: e.g., دجاج→دياي, شاي→چاي, فطور→ريوق, ملعقة→خاشوقة, لبن→روب
   Iraqi: e.g., دجاج→دجاج, خبز→صمون, طماطم→طماطة
   Levantine: e.g., بندورة→بندوره, باذنجان→بتنجان
   Maghrebi: e.g., خبز→كسرة, بطاطا→بطاطا
5. Common misspellings and taa marbouta variants (e.g., بامية→باميه, كوسة→كوسا, جبنة→جبنه)
6. Brand-associated terms if applicable (do NOT translate brand names)
7. Category and related terms
8. Occasion/use-case tags: هدية/gift, فطور/breakfast, تنظيف/cleaning, طبخ/cooking, ضيافة/hospitality, رمضان/ramadan, حفلة/party, أطفال/kids, مدرسة/school
9. Recipe/dish associations: If this product is a key ingredient in known dishes, include those dish names
   e.g., for chicken: مقلوبة, مسخن, شاورما, فتة. For rice: منسف, كبسة, مقلوبة

Generate at LEAST 20 terms. More is better. Return ONLY a comma-separated list, no explanations."""


async def enrich_product(
    name: str,
    description: Optional[str],
    category: Optional[str],
    *,
    timeout: float = 30.0,
    max_retries: int = 2,
) -> str:
    """One LLM call -> comma-separated search terms, or "" on failure. Never raises."""
    prompt = ENRICHMENT_PROMPT.format(name=name or "", description=description or "", category=category or "")
    try:
        response = await llm_adapter.generate(
            system_prompt="Return only comma-separated search terms. No explanations.",
            user_prompt=prompt,
            model=settings.offline_llm_model,
            enable_thinking=False,
            max_tokens=500,
            timeout=timeout,
            max_retries=max_retries,
            breaker=deepinfra_catalog_breaker,
        )
    except Exception as exc:  # defensive: the adapter should not raise
        logger.warning("enrich_product failed for %r: %r", (name or "")[:40], exc)
        return ""
    if not response:
        return ""
    cleaned = response.replace("\n", ", ").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1].strip()
    return cleaned


def merge_terms(base_terms: list[str], new_terms_csv: str) -> str:
    """Comma-joined, de-duplicated by normalized Arabic form, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for term in list(base_terms) + (new_terms_csv or "").split(","):
        term = term.strip()
        key = normalize_arabic(term) if term else ""
        if term and key and key not in seen:
            seen.add(key)
            out.append(term)
    return ", ".join(out)


def build_document_text(name: str, description: Optional[str], search_terms: Optional[str]) -> str:
    """The exact text embedded for search. Keep in one place."""
    return " ".join(p for p in (name, description, search_terms) if p).strip()


async def enrich_and_embed(gi, category_name: Optional[str], *, use_llm: bool = True, timeout: float = 30.0) -> bool:
    """
    Fill gi.search_terms and gi.text_embedding in place (caller commits).

    Always embeds something (at least the name) so the product is searchable.
    embedding_status: "completed"          LLM terms + embedding
                      "pending_enrichment" embedding without LLM terms (batch job fills later)
                      "failed"             no embedding (provider down)
    Returns True when LLM enrichment succeeded. Never raises.
    """
    base = [normalize_arabic(gi.name) or gi.name]
    extra = ""
    if use_llm:
        extra = await enrich_product(gi.name, gi.description, category_name, timeout=timeout, max_retries=1)
    gi.search_terms = merge_terms(base, extra)

    embedded = False
    try:
        vec = await embedding_service.encode_text_async(
            build_document_text(gi.name, gi.description, gi.search_terms), text_type="document"
        )
        if vec is not None and bool(vec.any()):
            gi.text_embedding = vec.tolist()
            gi.embedding_model = settings.qwen_embed_model
            gi.embedding_dim = int(vec.shape[0])
            gi.embedded_at = datetime.now(timezone.utc)
            embedded = True
    except Exception as exc:
        logger.warning("Embedding failed for item %s: %r", getattr(gi, "id", "?"), exc)

    gi.embedding_status = "completed" if (embedded and extra) else ("pending_enrichment" if embedded else "failed")
    return bool(extra)
