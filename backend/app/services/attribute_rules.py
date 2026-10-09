"""
Rules for the structured attributes in global_items.attributes (JSONB).

One place for what a valid attribute is, shared by search (what the query side may filter on),
merchant uploads (what a client may store) and the catalog enrichment job. Standard library only.

Why this exists: the search filter used to CAST attributes->>'organic' to a boolean, which is a
database error for any stored non-boolean string, and merchant uploads stored whatever JSON the
client sent. It also matched gender with ILIKE '%male%', which matches the stored value 'female'.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.arabic_norm import normalize_arabic

# Keys search may filter on (the same whitelist as query_understanding._ALLOWED_ATTR_KEYS).
SEARCH_ATTR_KEYS = frozenset({
    "type", "color", "flavor", "origin", "organic", "size",
    "brand", "temperature", "dietary", "material", "gender",
})
# Service listings (the merchant form and seed data) also carry these.
SERVICE_ATTR_KEYS = frozenset({"appointment_required", "home_service_available"})
# Keys a merchant client may store. stock_status is sent by the add-product form for products.
MERCHANT_ATTR_KEYS = SEARCH_ATTR_KEYS | SERVICE_ATTR_KEYS | {"stock_status"}
# Keys whose value must be a real JSON boolean.
BOOLEAN_ATTR_KEYS = frozenset({"organic", "appointment_required", "home_service_available"})

MAX_TEXT_LENGTH = 60

# Enumerated keys: the stored value is always one of these English words, whatever language
# the merchant or the query model used.
_ENUM_ALIASES: dict[str, dict[str, str]] = {
    "gender": {
        "male": "male", "m": "male", "man": "male", "men": "male",
        "رجالي": "male", "رجال": "male", "ذكر": "male", "للرجال": "male",
        "female": "female", "f": "female", "woman": "female", "women": "female",
        "نسائي": "female", "نساء": "female", "انثى": "female", "أنثى": "female",
        "للنساء": "female", "حريمي": "female",
        "unisex": "unisex", "both": "unisex", "للجنسين": "unisex",
        "any": "any",  # seeded service listings
    },
    "temperature": {
        "hot": "hot", "warm": "hot", "ساخن": "hot", "سخن": "hot", "حار": "hot",
        "cold": "cold", "بارد": "cold", "باردة": "cold",
        "iced": "iced", "ice": "iced", "مثلج": "iced", "مثلجة": "iced",
    },
}
ENUM_ATTR_KEYS = frozenset(_ENUM_ALIASES)

# Stored values that satisfy a queried enum value. Exact match only, so "male" can never match
# "female"; the one deliberate widening is that a cold query also finds iced items and back.
_ENUM_STORED_MATCHES: dict[str, dict[str, tuple[str, ...]]] = {
    "gender": {"male": ("male",), "female": ("female",), "unisex": ("unisex",), "any": ("any",)},
    "temperature": {"hot": ("hot",), "cold": ("cold", "iced"), "iced": ("iced", "cold")},
}
# Words in a product name that also satisfy the filter, for items whose attributes are not
# filled yet. Arabic and English words that cannot be substrings of each other.
_ENUM_NAME_WORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "gender": {"male": ("رجالي", "للرجال"), "female": ("نسائي", "للنساء", "حريمي")},
    "temperature": {"hot": ("hot", "ساخن"), "cold": ("cold", "بارد"), "iced": ("iced", "مثلج")},
}

_TRUE_WORDS = frozenset({"true", "yes", "y", "1", "نعم", "عضوي", "organic"})
_FALSE_WORDS = frozenset({"false", "no", "n", "0", "لا"})
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SPACE_RE = re.compile(r"\s+")


# The aliases also under their normalised spelling: the query model sees alef/hamza-normalised text,
# so it may answer "نساءي" (normalised) as readily as "نسائي".
_ENUM_LOOKUP: dict[str, dict[str, str]] = {
    key: {**aliases, **{normalize_arabic(alias): canonical for alias, canonical in aliases.items()}}
    for key, aliases in _ENUM_ALIASES.items()
}


def canonical_enum_value(key: str, value: Any) -> str | None:
    """The canonical English value of an enumerated attribute, or None if it is not one."""
    lookup = _ENUM_LOOKUP.get(key)
    if lookup is None or not isinstance(value, str):
        return None
    word = value.strip().lower()
    return lookup.get(word) or lookup.get(normalize_arabic(word))


def clean_text(value: Any, max_length: int = MAX_TEXT_LENGTH) -> str | None:
    """A trimmed single-line string, or None if it is not a string, is empty or is too long."""
    if not isinstance(value, str):
        return None
    text = _SPACE_RE.sub(" ", _CONTROL_RE.sub(" ", value)).strip()
    if not text or len(text) > max_length:
        return None
    return text


def coerce_bool(value: Any) -> bool | None:
    """True/False for a JSON boolean or an obvious yes/no word; None for anything else."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
    return None


def sanitize_merchant_attributes(raw: Any) -> dict:
    """
    What a merchant client may store in attributes: only known keys, with the right type.
    Booleans must be real booleans, gender/temperature are canonicalised, other values are
    short single-line strings. Everything else is dropped, never repaired by guessing.
    """
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in MERCHANT_ATTR_KEYS:
            continue
        if key in BOOLEAN_ATTR_KEYS:
            if isinstance(value, bool):
                clean[key] = value
        elif key in ENUM_ATTR_KEYS:
            canonical = canonical_enum_value(key, value)
            if canonical is not None:
                clean[key] = canonical
        else:
            text = clean_text(value)
            if text is not None:
                clean[key] = text
    return clean


# ── Search side: what the query model asked for, as a plan the SQL layer turns into clauses ──

@dataclass(frozen=True)
class AttrFilter:
    kind: str                      # "bool" | "enum" | "brand" | "text"
    key: str
    value: Any = None              # bool: the wanted boolean. enum: the canonical value
    stored: tuple[str, ...] = ()   # enum: stored values that satisfy it
    name_words: tuple[str, ...] = ()  # enum: words in a name that also satisfy it
    variants: tuple[str, ...] = ()    # brand/text: the value in every spelling worth trying (see match_variants)


def _with_and_without_al(value: str) -> tuple[str, ...]:
    variants = [value]
    if value.startswith("ال") and len(value) > 2:
        variants.append(value[2:])
    elif not value.startswith("ال"):
        variants.append("ال" + value)
    return tuple(variants)


# Spelling of alef and hamza. The query model is shown alef/hamza-normalised text ("شاي اخضر") but tends
# to answer in the usual spelling ("أخضر"), while product names and stored values may use either, and
# ILIKE tells them apart. So a value is tried in its raw and normalised form and with every plausible
# original letter put back, one letter at a time (a word-initial bare alef was أ or إ; a bare hamza was ئ or ؤ).
_ALEF, _ALEF_HAMZA_ABOVE, _ALEF_HAMZA_BELOW = chr(0x0627), chr(0x0623), chr(0x0625)
_HAMZA, _YEH_HAMZA, _WAW_HAMZA = chr(0x0621), chr(0x0626), chr(0x0624)
MAX_MATCH_VARIANTS = 16


def _single_letter_restorations(form: str) -> list[str]:
    out = []
    for i, ch in enumerate(form):
        if ch == _ALEF:
            starts_word = i == 0 or form[i - 1] == " "
            after_article = i >= 2 and form[i - 2:i] == "ال" and (i == 2 or form[i - 3] == " ")
            is_the_article_itself = starts_word and form[i:i + 2] == "ال"
            if (starts_word or after_article) and not is_the_article_itself:
                out.extend(form[:i] + rep + form[i + 1:] for rep in (_ALEF_HAMZA_ABOVE, _ALEF_HAMZA_BELOW))
        elif ch == _HAMZA:
            out.extend(form[:i] + rep + form[i + 1:] for rep in (_YEH_HAMZA, _WAW_HAMZA))
    return out


def spelling_variants(value: str) -> tuple[str, ...]:
    """The value as given, normalised, and with original alef/hamza letters put back (case-insensitive unique)."""
    seen: dict[str, str] = {}
    for form in (value, normalize_arabic(value)):
        seen.setdefault(form.lower(), form)
    for form in list(seen.values()):
        for restored in _single_letter_restorations(form):
            seen.setdefault(restored.lower(), restored)
    return tuple(form for form in seen.values() if form.strip())


def match_variants(value: str) -> tuple[str, ...]:
    """Every form of a query value worth matching: spelling variants, with and without "ال"."""
    variants: dict[str, str] = {}
    for base in _with_and_without_al(value):
        for form in spelling_variants(base):
            variants.setdefault(form.lower(), form)
    return tuple(variants.values())[:MAX_MATCH_VARIANTS]


def plan_attribute_filters(extracted_attrs: Any) -> list[AttrFilter]:
    """
    Turn the query model's attributes into filters. Anything unusable is skipped, which only
    widens the result set: unknown keys, null, numbers, a boolean for a text key, a text that is
    not one of the enum values.
    """
    if not isinstance(extracted_attrs, dict):
        return []
    plans: list[AttrFilter] = []
    for key, value in extracted_attrs.items():
        if key not in SEARCH_ATTR_KEYS or value is None:
            continue
        if key in BOOLEAN_ATTR_KEYS:
            wanted = coerce_bool(value)
            if wanted is not None:
                plans.append(AttrFilter("bool", key, value=wanted))
        elif key in ENUM_ATTR_KEYS:
            canonical = canonical_enum_value(key, value)
            if canonical is not None:
                plans.append(AttrFilter(
                    "enum", key, value=canonical,
                    stored=_ENUM_STORED_MATCHES[key][canonical],
                    name_words=_ENUM_NAME_WORDS[key].get(canonical, ()),
                ))
        elif isinstance(value, str):
            text = value.strip()
            if text:
                plans.append(AttrFilter(
                    "brand" if key == "brand" else "text", key, variants=match_variants(text),
                ))
    return plans
