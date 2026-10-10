"""
Jordan geography for store addresses: the governorates, a bounding-box sanity check for pins, and the
text built from a store's structured address.

Standard library only. The governorate keys are stored in `markets.governorate`; the app shows the
name in its own language. `mobile/utils/jordanAddress.ts` mirrors the keys (a test compares them).
"""

import math
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Governorate:
    key: str
    name_ar: str
    name_en: str


# The 12 governorates (محافظات الأردن). Keys are stable ASCII slugs, never shown to users.
GOVERNORATES = (
    Governorate("amman", "عمان", "Amman"),
    Governorate("irbid", "إربد", "Irbid"),
    Governorate("zarqa", "الزرقاء", "Zarqa"),
    Governorate("balqa", "البلقاء", "Balqa"),
    Governorate("madaba", "مأدبا", "Madaba"),
    Governorate("karak", "الكرك", "Karak"),
    Governorate("tafilah", "الطفيلة", "Tafilah"),
    Governorate("maan", "معان", "Ma'an"),
    Governorate("aqaba", "العقبة", "Aqaba"),
    Governorate("mafraq", "المفرق", "Mafraq"),
    Governorate("jerash", "جرش", "Jerash"),
    Governorate("ajloun", "عجلون", "Ajloun"),
)

GOVERNORATE_BY_KEY = {g.key: g for g in GOVERNORATES}
GOVERNORATE_KEYS = frozenset(GOVERNORATE_BY_KEY)

# A generous box around Jordan. It catches swapped latitude/longitude, a pin left at (0, 0) and
# typing mistakes; it is not a border (parts of neighbouring countries fall inside it).
JORDAN_MIN_LAT = 29.0
JORDAN_MAX_LAT = 33.5
JORDAN_MIN_LNG = 34.8
JORDAN_MAX_LNG = 39.4

AREA_MAX_LENGTH = 120
STREET_MAX_LENGTH = 160
LANDMARK_MAX_LENGTH = 200

_SPACES = re.compile(r"\s+")


def in_jordan_bbox(latitude: float, longitude: float) -> bool:
    """True when the point is inside the rough box around Jordan (False for NaN and infinity)."""
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return False
    return (
        JORDAN_MIN_LAT <= latitude <= JORDAN_MAX_LAT
        and JORDAN_MIN_LNG <= longitude <= JORDAN_MAX_LNG
    )


def clean_text(value: Optional[str]) -> Optional[str]:
    """Trim and collapse whitespace as typed; empty becomes None. The words are never changed."""
    if value is None:
        return None
    cleaned = _SPACES.sub(" ", value).strip()
    return cleaned or None


def normalize_governorate(value: Optional[str]) -> Optional[str]:
    """The key when `value` names a governorate (case and surrounding spaces ignored), else None."""
    if value is None:
        return None
    key = value.strip().lower()
    return key if key in GOVERNORATE_KEYS else None


def governorate_name_ar(key: Optional[str]) -> Optional[str]:
    governorate = GOVERNORATE_BY_KEY.get(key or "")
    return governorate.name_ar if governorate else None


def compose_address(governorate: Optional[str], area: Optional[str], street: Optional[str]) -> str:
    """
    The one-line address kept in `markets.address`: street, area, governorate (Arabic name), joined
    with the Arabic comma. It is the plain-text fallback for anything that does not read the
    structured fields (the `city` search filter matches against it). The landmark is not part of it.
    """
    parts = [clean_text(street), clean_text(area), governorate_name_ar(governorate)]
    return "، ".join(p for p in parts if p)


def address_parts_of(market) -> Optional[dict]:
    """
    The structured address of a market row for API responses, or None when the store has none
    (a row created before the structured fields existed).
    """
    parts = {
        "governorate": getattr(market, "governorate", None),
        "area": getattr(market, "area", None),
        "street": getattr(market, "street", None),
        "landmark": getattr(market, "landmark", None),
    }
    if not any(parts.values()):
        return None
    return parts
