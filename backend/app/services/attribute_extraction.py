"""
Structured attribute extraction for catalog products, from the NAME only.

The prompt, the response schema, the parser and the validator live here; the network call is
injected (`call_chat`), so everything is testable without a provider. The batch job that fills
global_items.attributes is app/jobs/enrich_attributes.py.

What search needs from these values (see attribute_rules.plan_attribute_filters): text values
are matched as substrings of what the query model extracted, so they are short Arabic words;
organic/gender/temperature are exact values. The validator is where that is enforced: the model
is asked politely, the code decides. Values for brand, organic, gender, temperature and dietary
must also be backed by a word in the name, so the model cannot invent them from world knowledge.

PROMPT_VERSION is stored in global_items.attributes_version. Bump it when the prompt changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.services.arabic_norm import normalize_arabic
from app.services.attribute_rules import canonical_enum_value, clean_text

PROMPT_VERSION = 1

# size is left out on purpose: nobody queries "500 مل" and the formats would not match.
EXTRACT_KEYS = (
    "brand", "type", "flavor", "origin", "dietary",
    "organic", "gender", "temperature", "color", "material",
)
TEXT_KEYS = ("type", "flavor", "origin", "color", "material")  # short Arabic words
MAX_NAME_LENGTH = 200
MAX_TEXT_VALUE_LENGTH = 30
MAX_TEXT_VALUE_WORDS = 3

SYSTEM_PROMPT = (
    "You extract product attributes from one Jordanian retail product name. "
    "Reply with one JSON object and nothing else."
)

USER_PROMPT = """Product name: {name}

Output only what the NAME ITSELF states. Never infer from brand reputation or world knowledge. If unsure, omit the key. {} is a normal answer: most names have 0-3 attributes.

Keys (omit any that do not apply):
- brand: the brand exactly as written in the name (Arabic or Latin).
- type: sub-type of the product, such as أخضر, أسود, أبيض, بكر ممتاز, تركية. Arabic, masculine singular, 1-2 words.
- flavor: one flavor stated in the name, such as نعناع, ليمون, جبنة, فانيلا. Arabic.
- origin: a place of origin stated in the name, such as أردني, نابلسي, خليلي, تركي, بلدي. Arabic.
- dietary: exactly one of: قليل الدسم, كامل الدسم, خالي من الدسم, خالي من الغلوتين, بدون سكر, بدون كافيين, خالي من اللاكتوز, نباتي
- organic: true ONLY if the name says عضوي / organic / bio. Never false.
- gender: male, female or unisex, only if the name says رجالي / نسائي / للجنسين or similar.
- temperature: hot, cold or iced, only if the name states it.
- color, material: only for non-food items. Arabic, masculine singular.

Never output size, weight, quantity, price, packaging, marketing words (جديد, عرض, فاخر), the product's own name or its category.

Examples:
"حليب المراعي قليل الدسم 1 لتر" -> {"brand":"المراعي","dietary":"قليل الدسم"}
"زيت زيتون بكر ممتاز أردني 1 لتر" -> {"type":"بكر ممتاز","origin":"أردني"}
"جبنة بيضاء بلدية 500 غم" -> {"type":"أبيض","origin":"بلدي"}
"شيبس ليز بنكهة الجبنة" -> {"brand":"ليز","flavor":"جبنة"}
"مزيل عرق نسائي نيفيا 150 مل" -> {"brand":"نيفيا","gender":"female"}
"قهوة تركية بدون هيل" -> {"type":"تركية"}
"Lipton Yellow Label Tea 100 bags" -> {"brand":"Lipton"}
"كرتونة مياه 12 حبة" -> {}"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "type": {"type": "string"},
        "flavor": {"type": "string"},
        "origin": {"type": "string"},
        "dietary": {"type": "string"},
        "organic": {"type": "boolean"},
        "gender": {"type": "string", "enum": ["male", "female", "unisex"]},
        "temperature": {"type": "string", "enum": ["hot", "cold", "iced"]},
        "color": {"type": "string"},
        "material": {"type": "string"},
    },
    "additionalProperties": False,
}
# DeepInfra structured outputs: https://docs.deepinfra.com/chat/structured-outputs
RESPONSE_FORMATS: dict[str, Optional[dict]] = {
    "schema": {
        "type": "json_schema",
        "json_schema": {"name": "product_attributes", "strict": True, "schema": RESPONSE_SCHEMA},
    },
    "object": {"type": "json_object"},
    "none": None,
}

# ── Evidence: a word in the name that backs the value ───────────────────────────────────────────
_GENDER_EVIDENCE = {
    "male": ("رجالي", "رجال", "للرجال", "men", "man", "male", "gents"),
    "female": ("نسائي", "نساء", "للنساء", "حريمي", "بناتي", "women", "woman", "female", "ladies", "lady"),
    "unisex": ("للجنسين", "unisex"),
}
_TEMPERATURE_EVIDENCE = {
    "hot": ("ساخن", "سخن"),
    "cold": ("بارد", "باردة", "cold"),
    "iced": ("مثلج", "مثلجة", "iced", "ايس تي", "ice tea"),
}
_ORGANIC_EVIDENCE = ("عضوي", "عضوية", "organic", "bio")
_DIETARY_EVIDENCE = {
    "قليل الدسم": ("قليل الدسم", "low fat", "lowfat", "لو فات"),
    "كامل الدسم": ("كامل الدسم", "full fat", "full cream", "فول كريم"),
    "خالي من الدسم": ("خالي من الدسم", "خال من الدسم", "fat free", "non fat"),
    "خالي من الغلوتين": ("غلوتين", "gluten free", "gluten-free"),
    "بدون سكر": ("بدون سكر", "خالي من السكر", "خال من السكر", "sugar free", "no sugar", "دايت", "diet", "zero"),
    "بدون كافيين": ("بدون كافيين", "خالي من الكافيين", "decaf", "decaffeinated"),
    "خالي من اللاكتوز": ("لاكتوز", "lactose free"),
    "نباتي": ("نباتي", "vegan", "plant based"),
}
DIETARY_VALUES = tuple(_DIETARY_EVIDENCE)

_PLACEHOLDERS = frozenset({
    "منتج", "عادي", "غير معروف", "لا يوجد", "غير محدد", "none", "null", "n/a", "na", "unknown", "-", "--",
})
_SEPARATORS = ("/", "|", "،", ",", ";", "؛", "\\")
_DIGIT_RE = re.compile(r"[0-9\u0660-\u0669\u06f0-\u06f9]")
_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
_LATIN_RE = re.compile(r"[a-z]")
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _has_evidence(normalized_name: str, phrases) -> bool:
    """True if one of the phrases is in the name; Latin phrases must be whole words."""
    for phrase in phrases:
        p = normalize_arabic(phrase)
        if not p:
            continue
        if _LATIN_RE.search(p):
            if re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", normalized_name):
                return True
        elif p in normalized_name:
            return True
    return False


def validate_extracted(raw: Any, name: str, keys=EXTRACT_KEYS) -> tuple[dict, list[str]]:
    """
    The attributes that may be stored, and why the rest was dropped (for the report).
    Nothing is repaired by guessing: a value that breaks a rule is dropped.
    """
    if not isinstance(raw, dict):
        return {}, ["not_an_object"]
    norm_name = normalize_arabic(name)
    clean: dict[str, Any] = {}
    dropped: list[str] = []

    for key in EXTRACT_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if value is None or value == "":
            continue
        if key not in keys:
            dropped.append(f"{key}:key_disabled")
            continue

        if key == "organic":
            if value is not True:
                dropped.append("organic:not_true")
            elif not _has_evidence(norm_name, _ORGANIC_EVIDENCE):
                dropped.append("organic:no_evidence")
            else:
                clean[key] = True

        elif key in ("gender", "temperature"):
            canonical = canonical_enum_value(key, value)
            evidence = _GENDER_EVIDENCE if key == "gender" else _TEMPERATURE_EVIDENCE
            if canonical is None or canonical not in evidence:
                dropped.append(f"{key}:bad_value")
            elif not _has_evidence(norm_name, evidence[canonical]):
                dropped.append(f"{key}:no_evidence")
            else:
                clean[key] = canonical

        elif key == "dietary":
            text = clean_text(value)
            if text not in DIETARY_VALUES:
                dropped.append("dietary:not_canonical")
            elif not _has_evidence(norm_name, _DIETARY_EVIDENCE[text]):
                dropped.append("dietary:no_evidence")
            else:
                clean[key] = text

        else:  # brand and the short text keys
            text = clean_text(value, MAX_TEXT_VALUE_LENGTH)
            reason = _text_problem(key, text, norm_name)
            if reason:
                dropped.append(f"{key}:{reason}")
            else:
                clean[key] = text

    for key in raw:
        if key not in EXTRACT_KEYS:
            dropped.append(f"{key}:unknown_key")
    return clean, dropped


def _text_problem(key: str, text: Optional[str], norm_name: str) -> Optional[str]:
    if text is None:
        return "not_a_short_string"
    norm = normalize_arabic(text)
    if norm in _PLACEHOLDERS:
        return "placeholder"
    if any(sep in text for sep in _SEPARATORS):
        return "several_values"
    if norm == norm_name:
        return "equals_name"
    if key == "brand":
        bare = norm[2:] if norm.startswith("ال") and len(norm) > 3 else norm
        if norm not in norm_name and bare not in norm_name:
            return "not_in_name"
        return None
    if _DIGIT_RE.search(text):
        return "has_digit"
    if not _ARABIC_RE.search(text):
        return "not_arabic"
    if len(text.split()) > MAX_TEXT_VALUE_WORDS:
        return "too_many_words"
    return None


# ── Prompt and response handling ───────────────────────────────────────────────────────────────
def build_messages(name: str) -> list[dict]:
    name = re.sub(r"\s+", " ", name or "").strip()[:MAX_NAME_LENGTH]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT.replace("{name}", name)},
    ]


def parse_json_object(text: Optional[str]) -> Optional[dict]:
    """The JSON object in a model reply (think blocks, code fences and chatter around it removed)."""
    if not text:
        return None
    cleaned = _THINK_RE.sub("", text).strip()
    cleaned = _FENCE_RE.sub("", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start:end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


CallChat = Callable[[list, Optional[dict]], Awaitable[Optional[dict]]]


@dataclass
class Extraction:
    status: str                                   # "ok" | "no_response" | "bad_json" | "skipped"
    attributes: dict = field(default_factory=dict)
    dropped: list = field(default_factory=list)   # why the validator removed something
    raw: str = ""                                 # the model's reply (or the error), for the reports
    prompt_tokens: int = 0
    completion_tokens: int = 0


async def extract_attributes(
    name: str,
    call_chat: CallChat,
    response_format: Optional[dict] = None,
    keys=EXTRACT_KEYS,
) -> Extraction:
    """
    One model call for one name. `call_chat(messages, response_format)` returns the provider's
    chat-completion payload, or None when the call failed. "no_response" means the provider
    failed (try again later); "bad_json" means it answered but not with a JSON object.
    An empty dict with status "ok" is a real answer: nothing could be extracted.
    """
    try:
        payload = await call_chat(build_messages(name), response_format)
    except Exception as exc:  # the adapter should not raise; a job must not die on one item
        return Extraction("no_response", raw=repr(exc))
    if not payload:
        return Extraction("no_response")

    usage = payload.get("usage") or {}
    tokens = {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
    }
    try:
        message = payload["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning_content") or ""
    except (KeyError, IndexError, TypeError, AttributeError):
        return Extraction("bad_json", **tokens)

    parsed = parse_json_object(content)
    if parsed is None:
        return Extraction("bad_json", raw=str(content)[:300], **tokens)
    attributes, dropped = validate_extracted(parsed, name, keys)
    return Extraction("ok", attributes, dropped, str(content)[:300], **tokens)
