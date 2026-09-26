"""
Barcode normalization — one canonical form for storage and lookup.

GS1 barcodes (EAN-8, UPC-A, EAN-13, GTIN-14) with a valid check digit are stored
zero-padded to 14 digits (GTIN-14), the GS1-recommended database key. This makes a
UPC-A product match whether the scanner reports it as 12 digits (typical on
Android) or 13 digits with a leading zero (typical on iOS).

Anything else (a store's internal code, a typo) is kept as typed, minus spaces
and dashes, so an exact re-scan still matches it.
"""

from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s\-]+")
_GS1_LENGTHS = (8, 12, 13, 14)
_MAX_LEN = 100  # global_items.barcode is String(100)


def gs1_check_digit_ok(code: str) -> bool:
    body, check = code[:-1], int(code[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize_barcode(raw: str | None) -> str | None:
    if raw is None:
        return None
    code = _SEPARATORS.sub("", str(raw)).strip()
    if not code or len(code) > _MAX_LEN:
        return None
    if code.isdigit() and len(code) in _GS1_LENGTHS and gs1_check_digit_ok(code):
        return code.zfill(14)
    return code
