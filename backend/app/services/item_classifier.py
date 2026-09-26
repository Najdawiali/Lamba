"""
Item classifier — decides, in one LLM call, whether a product may be listed on
Lamba (restriction policy) and which category it belongs to (app.taxonomy).

Used wherever a product enters the catalog: merchant manual add, CSV upload,
barcode-catalog import. Pure function of the text: no DB access, so it can be
evaluated offline (see backend/evals/eval_classifier.py).

Moderation outcome (see ClassificationResult.moderation_status):
    restricted + high confidence  -> "blocked"
    restricted + low confidence   -> "pending_review"   (a human decides)
    allowed    + low confidence   -> "pending_review"
    allowed    + high confidence  -> "approved"
    LLM unavailable / bad output  -> "pending_review"   (fail closed)

`confidence` refers to the restriction decision only. A wrong category is
cheap (the merchant can fix it); a wrong restriction decision is not.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from app.config import settings
from app.services.llm import llm_adapter
from app.taxonomy import CATEGORY_BY_SLUG, LEAF_CATEGORIES

logger = logging.getLogger(__name__)

RESTRICTED_CLASSES: tuple[str, ...] = ("tobacco", "alcohol", "drugs", "weapons")

_POLICY = """Lamba does NOT allow these products at all:
- tobacco: cigarettes, cigars, hookah tobacco (معسل), vapes / e-cigarettes / e-liquids, nicotine pouches, and smoking accessories (hookah devices, hookah charcoal, hookah foil, hookah hoses, cigarette holders, rolling papers).
- alcohol: beer, wine, arak, spirits, cooking wine, any drink that contains alcohol.
- drugs: narcotics, illegal substances, drug paraphernalia, and prescription-only medicines (antibiotics, opioids, sedatives, pregabalin, and similar).
- weapons: firearms, blank guns, ammunition, air guns and pellets, combat knives, swords, brass knuckles, tasers, pepper spray, explosives, fireworks.

These ARE allowed even though they can look similar: lighters, barbecue charcoal and charcoal lighters, air fresheners and odor removers, non-alcoholic beer and malt drinks, vinegar, medical/rubbing alcohol, hand sanitizer, over-the-counter painkillers and first-aid supplies, kitchen knives, tools (saws, axes, glue guns, spray guns), and toy guns.

Judge what the product IS, not which words appear in its name. Brand names can resemble restricted words."""


def _category_lines(listing_type: str | None) -> list[str]:
    lines = []
    for c in LEAF_CATEGORIES:
        if listing_type and c.listing_type != listing_type:
            continue
        section = CATEGORY_BY_SLUG[c.parent].name_ar
        lines.append(f"- {c.slug}: {c.name_ar} ({c.name_en}) [{section}]")
    return lines


def build_system_prompt(listing_type: str | None = None) -> str:
    return (
        "You classify products and services that shops in Jordan list on Lamba, a local "
        "marketplace. Names are often short cashier-style Arabic names with brand and size.\n\n"
        "Task 1 — restricted:\n"
        f"{_POLICY}\n\n"
        "Task 2 — category: choose exactly one slug from this list:\n"
        + "\n".join(_category_lines(listing_type))
        + "\n\n"
        "Task 3 — confidence about Task 1 only: \"high\" if you are certain whether the item "
        "is restricted, \"low\" if it could plausibly be restricted or you do not recognize it.\n\n"
        "Respond with ONLY this JSON object, no other text:\n"
        '{"restricted": "none|tobacco|alcohol|drugs|weapons", "category": "<slug>", "confidence": "high|low"}'
    )


@dataclass(frozen=True)
class ClassificationResult:
    restricted: str | None  # None = allowed, else one of RESTRICTED_CLASSES
    category_slug: str | None  # a leaf slug from app.taxonomy, or None
    confident: bool  # confidence about the restriction decision
    error: str | None = None  # llm_unavailable | unparseable | invalid_restricted | invalid_category
    latency_ms: int = 0
    raw: str = ""

    @property
    def moderation_status(self) -> str:
        if self.error in ("llm_unavailable", "unparseable", "invalid_restricted"):
            return "pending_review"
        if self.restricted:
            return "blocked" if self.confident else "pending_review"
        return "approved" if self.confident else "pending_review"


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_response(raw: str, allowed_slugs: set[str]) -> tuple[str | None, str | None, bool, str | None]:
    """Return (restricted, category_slug, confident, error). Pure, unit-testable."""
    match = _JSON_RE.search(raw or "")
    if not match:
        return None, None, False, "unparseable"
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, None, False, "unparseable"
    if not isinstance(data, dict):
        return None, None, False, "unparseable"

    restricted_raw = str(data.get("restricted", "")).strip().lower()
    if restricted_raw == "none":
        restricted = None
    elif restricted_raw in RESTRICTED_CLASSES:
        restricted = restricted_raw
    else:
        return None, None, False, "invalid_restricted"

    confident = str(data.get("confidence", "")).strip().lower() == "high"

    if restricted:
        return restricted, None, confident, None

    slug = str(data.get("category", "")).strip().lower()
    if slug not in allowed_slugs:
        return None, None, confident, "invalid_category"
    return None, slug, confident, None


async def classify_item(
    name: str,
    description: str | None = None,
    listing_type: str | None = None,
    *,
    model: str | None = None,
    timeout: float = 12.0,
    max_retries: int = 2,
) -> ClassificationResult:
    """Classify one product or service. Never raises; failures come back as `error`."""
    allowed = {c.slug for c in LEAF_CATEGORIES if not listing_type or c.listing_type == listing_type}
    user_msg = f"Name: {name.strip()}\nDescription: {(description or '').strip() or '-'}"

    started = time.monotonic()
    try:
        raw = await llm_adapter.complete_chat(
            messages=[
                {"role": "system", "content": build_system_prompt(listing_type)},
                {"role": "user", "content": user_msg},
            ],
            model=model or settings.classifier_model,
            temperature=0.0,
            max_tokens=80,
            timeout=timeout,
            max_retries=max_retries,
        )
    except Exception as exc:  # defensive: the adapter should not raise, but never let it escape
        logger.warning("classify_item: LLM call raised for %r: %s", name[:40], exc)
        raw = None
    latency_ms = int((time.monotonic() - started) * 1000)

    if raw is None:
        return ClassificationResult(None, None, False, "llm_unavailable", latency_ms, "")

    restricted, slug, confident, error = parse_response(raw, allowed)
    if error:
        logger.warning("classify_item: %s for %r: %r", error, name[:40], raw[:200])
    return ClassificationResult(restricted, slug, confident, error, latency_ms, raw)
