"""
Rule-based attributes from a search query: no network, no model, instant.

The query model gets organic / gender / temperature / dietary right every time (checked on the
server, 2026-10-09: 24 of 24 calls), and each one is a plain word in the query. Those four are
therefore taken from the words directly, so they no longer depend on a rented model that is
sometimes saturated; the model still adds what words cannot (type, flavor, origin, brand,
category, product or service). When the model answers, these values win for their keys; when it
is late or down, they are all the search has.

Words are matched as whole tokens (an optional "و" and "ال" before and a feminine "ة" after are allowed),
never as substrings: "مسخن" is a dish, not "hot", and "Spider Man" is not a gender. Words that
are ambiguous in a query are left out ("bio" and "man" can be brands or names). Contradicting
words ("رجالي ونسائي", "ساخن بارد") produce no value for that key.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.services.arabic_norm import normalize_arabic
from app.services.attribute_rules import (
    DIETARY_EVIDENCE,
    GENDER_EVIDENCE,
    ORGANIC_EVIDENCE,
    TEMPERATURE_EVIDENCE,
)

# Fine as a word in a product name, too ambiguous in a query (brands, names).
_AMBIGUOUS_IN_QUERIES = frozenset({"bio", "man", "woman", "lady", "gents"})
_NEGATIONS = ("غير", "ليس", "non", "not")

_LATIN = re.compile(r"[a-z]")


def _phrase_pattern(phrase: str) -> Optional[re.Pattern]:
    normalized = normalize_arabic(phrase)
    if not normalized or normalized in _AMBIGUOUS_IN_QUERIES:
        return None
    body = re.escape(normalized)
    if _LATIN.search(normalized):
        return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")
    # whole token(s): an optional conjunction ("ونسائي" = "and women's") and article before, an optional
    # feminine ending after
    return re.compile(r"(?<!\S)(?:و|ف)?(?:ال)?" + body + r"(?:ة)?(?!\S)")


def _patterns(phrases) -> list:
    return [p for p in (_phrase_pattern(phrase) for phrase in phrases) if p is not None]


_ORGANIC = _patterns(ORGANIC_EVIDENCE)
_NEGATED_ORGANIC = re.compile(
    r"(?<!\S)(?:" + "|".join(_NEGATIONS) + r")[- ]+(?:ال)?(?:"
    + "|".join(re.escape(normalize_arabic(p)) for p in ORGANIC_EVIDENCE if normalize_arabic(p) not in _AMBIGUOUS_IN_QUERIES)
    + r")"
)
_GENDER = {gender: _patterns(phrases) for gender, phrases in GENDER_EVIDENCE.items()}
_TEMPERATURE = {value: _patterns(phrases) for value, phrases in TEMPERATURE_EVIDENCE.items()}
_DIETARY = {value: _patterns(phrases) for value, phrases in DIETARY_EVIDENCE.items()}


def _found(query: str, patterns) -> bool:
    return any(pattern.search(query) for pattern in patterns)


def extract_query_attributes(query: Optional[str]) -> dict[str, Any]:
    """organic / gender / temperature / dietary found as words in the query (same values the filters use)."""
    if not query:
        return {}
    q = normalize_arabic(query)
    attributes: dict[str, Any] = {}

    if _found(q, _ORGANIC) and not _NEGATED_ORGANIC.search(q):
        attributes["organic"] = True

    male, female, unisex = (_found(q, _GENDER[g]) for g in ("male", "female", "unisex"))
    if male != female and not unisex:
        attributes["gender"] = "male" if male else "female"

    hot, cold, iced = (_found(q, _TEMPERATURE[t]) for t in ("hot", "cold", "iced"))
    if hot and (cold or iced):
        pass  # contradicting words: no value
    elif hot:
        attributes["temperature"] = "hot"
    elif cold:
        attributes["temperature"] = "cold"
    elif iced:
        attributes["temperature"] = "iced"

    dietary = [value for value, patterns in _DIETARY.items() if _found(q, patterns)]
    if len(dietary) == 1:
        attributes["dietary"] = dietary[0]

    return attributes


def merge_attributes(model_attributes: Optional[dict], rule_attributes: Optional[dict]) -> dict:
    """The model's attributes plus the rule-based ones; for the keys the rules know, the rules win."""
    return {**(model_attributes or {}), **(rule_attributes or {})}
