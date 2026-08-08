"""
Query token extractor & overlap helper.

Used by the post-rerank guard (search_v1.py) to identify candidates that
score highly at the reranker but share NO literal tokens with the query — a
strong signal of an out-of-domain false positive (e.g. query "شاشه 44 بوصه
من smi" vs candidate "بروتين المراعي شوكلاته").

Lightweight, deterministic, no LLM calls. Relies on app.services.arabic_norm
for canonical Arabic surface forms.
"""

from __future__ import annotations

import re
from typing import Dict, Set

from app.services.arabic_norm import normalize_arabic, arabizi_to_arabic


# Arabic stop-words — removed before token overlap so they don't pad the count.
# Kept tiny on purpose; a longer list would over-prune short queries.
_AR_STOPWORDS: Set[str] = {
    "من", "في", "على", "الى", "او", "و", "ف", "ال", "ب", "ل",
    "هذا", "هذه", "ذلك", "تلك", "التي", "الذي",
}
# Latin stop-words (used when query contains Arabizi / English fragments).
_LATIN_STOPWORDS: Set[str] = {
    "from", "of", "the", "a", "an", "and", "or", "for", "with", "in", "on",
    "is", "are", "to",
}

# Digits / size-pattern Recognizer — "44", "44inch", "44 بوصه", "32L"
_SIZE_RE = re.compile(r"\b\d{1,4}(?:\s*(?:inch|in|بوصه|بوصة|cm|kg|g|l|ml|cc)?)\b", re.IGNORECASE)
# Latin-script token of length>=2 (skips single letters and pure digits)
_LATIN_TOKEN_RE = re.compile(r"\b[a-z]{2,}\b", re.IGNORECASE)


def extract_query_tokens(query: str) -> Dict[str, Set[str]]:
    """
    Pull {brands, sizes, category_terms} tokens from a raw query string.

    The split is heuristic and intentionally permissive:
      - sizes  → digit-anchored tokens + unit words (44, 44 بوصه)
      - brands → Latin-script tokens length >= 2 (e.g. "smi", "sony", "lg")
      - category_terms → all remaining Arabic-script tokens (after stopword
        removal and normalization)

    Returns empty sets when the query doesn't contain that script/kind of
    token — so the guard can gracefully skip the corresponding check.
    """
    if not query:
        return {"brands": set(), "sizes": set(), "category_terms": set()}

    # First pass: normalize Arabic + convert Arabizi → Arabic
    arabicized = arabizi_to_arabic(query)
    norm = normalize_arabic(arabicized) or query.lower()

    # Sizes — operate on the original (lowercased) query to preserve digits
    sizes: Set[str] = set()
    for m in _SIZE_RE.finditer(query.lower()):
        token = re.sub(r"\s+", "", m.group(0))  # "44 بوصه" → "44بوصه"
        sizes.add(token)
        # Also add the bare digit-only form so candidate "44 inch" matches query "44"
        digits_only = re.sub(r"[^\d]", "", token)
        if digits_only:
            sizes.add(digits_only)

    # Latin tokens → brand candidates
    brands: Set[str] = {w.lower() for w in _LATIN_TOKEN_RE.findall(query)
                        if w.lower() not in _LATIN_STOPWORDS}

    # Arabic tokens → category terms
    cat_terms: Set[str] = set()
    for raw in re.split(r"[\s,،;:\-_/]+", arabicized):
        tok = normalize_arabic(raw)
        if not tok:
            continue
        if tok in _AR_STOPWORDS or tok.isdigit():
            continue
        cat_terms.add(tok)

    return {"brands": brands, "sizes": sizes, "category_terms": cat_terms}


def _doc_text_tokens(text: str) -> Set[str]:
    """Normalize a candidate's name+description into a set of surface tokens."""
    if not text:
        return set()
    arabicized = arabizi_to_arabic(text)
    norm = normalize_arabic(arabicized) or text.lower()
    tokens: Set[str] = set()
    for raw in re.split(r"[\s,،;:\-_/()]+", norm):
        tok = normalize_arabic(raw) or raw.lower().strip()
        if not tok or tok in _AR_STOPWORDS or tok in _LATIN_STOPWORDS:
            continue
        tokens.add(tok)
        # Also add the bare-digit form for size matching
        if tok.isdigit():
            tokens.add(tok)
    return tokens


def tokens_overlap(query_tokens: Dict[str, Set[str]], doc_text: str) -> int:
    """
    Count shared tokens between the query and a candidate's text.

    A hit in any of the three buckets (brand, size, category) counts. We
    intentionally return the *number* of distinct shared tokens so the
    caller can apply its own minimum threshold (settings.reranker_token_overlap_min).
    """
    if not doc_text:
        return 0
    doc_toks = _doc_text_tokens(doc_text)
    overlap = 0
    for bucket in ("brands", "sizes", "category_terms"):
        for qt in query_tokens.get(bucket, set()):
            if not qt:
                continue
            # Exact match OR substring containment (handles "smi" inside "smi-tv")
            for dt in doc_toks:
                if qt == dt or qt in dt or dt in qt:
                    overlap += 1
                    break
    return overlap