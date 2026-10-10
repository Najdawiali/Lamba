"""
DeepInfra service tiers, chosen per call path (see the *_service_tier settings in app/config.py).

Per https://docs.deepinfra.com/chat/overview a chat completion takes an optional `service_tier`:
- unset: standard scheduling and price
- "priority": served first when the model is busy, +50% per-token price
- "flex": -20% per-token price, but a request may wait up to 10 minutes or be rejected with a 429, so it
  is for batch work only and must never be configured on an interactive path

On the server (2026-10-10), around a burst of HTTP 429 "Model busy" on gemma-4-26B-A4B, priority answered
6 of 6 calls and the standard tier 5 of 6.

Standard library only.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_TIERS = ("priority", "flex")
_STANDARD_NAMES = ("", "standard", "default", "none")
_warned: set = set()


def service_tier_fields(tier: Optional[str], *, allow_flex: bool = True) -> dict:
    """
    The request fields for a configured tier: {} for the standard tier, {"service_tier": "priority"} etc.

    An unknown value is ignored (standard tier) with one warning per value: a typo in an environment
    variable must not turn every model call into an HTTP 400. Interactive paths pass allow_flex=False:
    "flex" may queue a request for up to 10 minutes, so there it is ignored the same way.
    """
    value = (tier or "").strip().lower()
    if value in _STANDARD_NAMES:
        return {}
    if value == "priority" or (value == "flex" and allow_flex):
        return {"service_tier": value}
    if value not in _warned:
        _warned.add(value)
        if value == "flex":
            logger.warning("DeepInfra service tier 'flex' ignored on an interactive path (a request may wait up to 10 minutes)")
        else:
            logger.warning("Unknown DeepInfra service tier %r ignored (use one of: %s, or leave empty)", tier, ", ".join(SUPPORTED_TIERS))
    return {}
