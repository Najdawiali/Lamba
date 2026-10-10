"""
Changing where an existing store is: the lock policy and what is recorded.

Allowed without support: moving the pin up to FREE_MOVE_LIMIT_M metres, and any edit of the area,
street and landmark text. Refused (the merchant contacts support): a bigger move, or a different
governorate once one is set. Setting the governorate on a store that has none is allowed.

Standard library only, no database: the endpoint reads the current pin, calls
`apply_location_update`, then writes the new point and the audit row from the returned
`LocationChange`.
"""

import math
from dataclasses import dataclass
from typing import Optional

from app.jordan_geo import compose_address

FREE_MOVE_LIMIT_M = 200.0

REASON_PIN_TOO_FAR = "pin_too_far"
REASON_GOVERNORATE_LOCKED = "governorate_locked"

SUPPORT_EMAIL = "support@lambajo.com"

# Server messages are bilingual: Arabic line, then English line (the app shows one of them).
MSG_PIN_TOO_FAR = (
    f"لا يمكن نقل موقع المتجر أكثر من {int(FREE_MOVE_LIMIT_M)} متر من التطبيق. "
    f"للتغيير تواصل مع الدعم: {SUPPORT_EMAIL}\n"
    f"The store pin can only be moved up to {int(FREE_MOVE_LIMIT_M)} m in the app. "
    f"To change it, contact support: {SUPPORT_EMAIL}"
)
MSG_GOVERNORATE_LOCKED = (
    f"لا يمكن تغيير المحافظة من التطبيق. تواصل مع الدعم: {SUPPORT_EMAIL}\n"
    f"The governorate can't be changed in the app. Contact support: {SUPPORT_EMAIL}"
)

_EARTH_RADIUS_M = 6371008.8
# Two pins closer than this are the same pin (float noise from the database round trip).
_SAME_PIN_M = 0.01

FIELDS = ("governorate", "area", "street", "landmark")


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres (haversine). Within 0.5% of PostGIS' geography distance."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


class LocationChangeRefused(Exception):
    """The lock policy says no. `reason` is one of the REASON_* values, `message` is bilingual."""

    def __init__(self, reason: str, message: str, moved_m: float = 0.0):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.moved_m = moved_m


@dataclass(frozen=True)
class LocationChange:
    changed: bool
    old_latitude: float
    old_longitude: float
    new_latitude: float
    new_longitude: float
    moved_m: float
    old_fields: dict
    new_fields: dict


def apply_location_update(market, old_latitude: float, old_longitude: float, update) -> LocationChange:
    """
    Check `update` (latitude, longitude, governorate, area, street, landmark) against the policy and,
    when it passes and changes something, write the structured fields and the composed `address`
    onto `market`. The point itself is written by the caller. Raises LocationChangeRefused.
    """
    old_fields = {name: getattr(market, name, None) for name in FIELDS}
    new_fields = {name: getattr(update, name, None) for name in FIELDS}
    moved = distance_m(old_latitude, old_longitude, update.latitude, update.longitude)

    old_governorate: Optional[str] = old_fields["governorate"]
    if old_governorate and new_fields["governorate"] != old_governorate:
        raise LocationChangeRefused(REASON_GOVERNORATE_LOCKED, MSG_GOVERNORATE_LOCKED, moved)
    if moved > FREE_MOVE_LIMIT_M:
        raise LocationChangeRefused(REASON_PIN_TOO_FAR, MSG_PIN_TOO_FAR, moved)

    changed = moved >= _SAME_PIN_M or old_fields != new_fields
    if changed:
        for name in FIELDS:
            setattr(market, name, new_fields[name])
        market.address = compose_address(
            new_fields["governorate"], new_fields["area"], new_fields["street"]
        )

    return LocationChange(
        changed=changed,
        old_latitude=old_latitude,
        old_longitude=old_longitude,
        new_latitude=update.latitude,
        new_longitude=update.longitude,
        moved_m=moved,
        old_fields=old_fields,
        new_fields=new_fields,
    )
