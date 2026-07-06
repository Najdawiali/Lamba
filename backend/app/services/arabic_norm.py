"""
Arabic text normalization & Arabizi transliteration.

Single source of truth used by:
  - app.services.embedding (before encoding queries & items)
  - app.api.search_v1     (before building tsquery / lexical predicates)
  - scripts.backfill_search_terms (when populating search_terms)

Normalization breakdown:
  1. Strip tashkeel (diacritics)
  2. Unify alef forms (إ أ آ ا → ا)
  3. Alef maksura → ya (ى → ي)
  4. Unify hamza carriers (ؤ ئ → ء)
  5. Strip tatweel / kashida (ـ)
  6. Collapse whitespace

Arabizi → Arabic:
  Common digit-to-letter conversions used in informal chat (3→ع, 7→ح, etc.)
  so queries like "shay" / "3asal" can match catalog items written in Arabic.

References:
  - CAMeL Tools (pip install camel-tools) — more thorough, but heavier
  - PyArabic — alternative
  - The subset below is hand-rolled to stay dependency-free and deterministic.
"""

from __future__ import annotations

import re
import unicodedata

# ── Compiled regexes (compiled once for performance) ────────────────
_DIACRITICS_RE = re.compile(r"[\u064B-\u0652\u0670]")    # Tashkeel + dagger alef
_ALEF_RE = re.compile(r"[إأآا]")
_ALEF_MAKSURA_RE = re.compile(r"ى")
_HAMZA_CARRIERS_RE = re.compile(r"[ؤئ]")
_TATWEEL_RE = re.compile(r"\u0640+")                     # Kashida
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_arabic(text: str | None) -> str:
    """
    Normalize Arabic script text for canonical matching.

    Args:
        text: Raw input, possibly None or mixed Arabic/Latin.

    Returns:
        Lowercased, normalized string with diacritics stripped, alef forms
        unified, alef-maksura → ya, hamza-carriers → bare hamza, tatweel
        removed, and whitespace collapsed to single spaces.
    """
    if not text:
        return ""

    # NFKC normalization handles a lot of presentation forms and ligatures
    text = unicodedata.normalize("NFKC", text)

    text = _DIACRITICS_RE.sub("", text)
    text = _ALEF_RE.sub("ا", text)
    text = _ALEF_MAKSURA_RE.sub("ي", text)
    text = _HAMZA_CARRIERS_RE.sub("ء", text)
    text = _TATWEEL_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    return text.lower()


# ── Arabizi (Franco-Arabic) → Arabic ────────────────────────────────
# Mapping derived from common Latin-script Gulf/Levantine chat orthography.
# Applied as positional-aware substitutions: digits and letter clusters
# that are conventionally used to approximate Arabic letters.
_ARABIZI_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"3'"), "غ"),
    (re.compile(r"7'"), "خ"),
    (re.compile(r"6'"), "ط"),
    (re.compile(r"9'"), "ض"),
    (re.compile(r"2'"), "ء"),
    (re.compile(r"\b3"), "ع"),
    (re.compile(r"\b7"), "ح"),
    (re.compile(r"\b6"), "ط"),
    (re.compile(r"\b9"), "ض"),
    (re.compile(r"\b5"), "خ"),
    (re.compile(r"\b8"), "ق"),
    (re.compile(r"\b4"), "ش"),
    (re.compile(r"\b2"), "أ"),
    (re.compile(r"\bgh\b"), "غ"),
    (re.compile(r"\bkh\b"), "خ"),
    (re.compile(r"\bsh\b"), "ش"),
    (re.compile(r"\bch\b"), "ش"),
    (re.compile(r"\bth\b"), "ث"),
    (re.compile(r"\bah\b"), "ة"),
    (re.compile(r"\ba\b"), "ا"),
]


def arabizi_to_arabic(text: str | None) -> str:
    """
    Convert Arabizi / Franco-Arabic numerics to Arabic script approximation.

    Examples:
        "3asal"  -> "عasal"
        "shay"   -> "shay"      (only digits and a few clusters are mapped)
        "7abibi" -> "حabibi"

    This is a *light* transliteration layer intended to widen recall, not a
    full Latin→Arabic transliteration engine. Pair with normalize_arabic().
    """
    if not text:
        return ""
    out = text
    for pattern, replacement in _ARABIZI_RULES:
        out = pattern.sub(replacement, out)
    return out


def normalize_query(text: str | None) -> str:
    """
    Full query-time normalization pipeline:
      Arabizi → Arabic, then Arabic normalize, then lowercase collapse.

    Use this on every user query before embedding AND before building the
    tsvector/tsquery lexical predicate.
    """
    if not text:
        return ""
    arabicized = arabizi_to_arabic(text)
    return normalize_arabic(arabicized)