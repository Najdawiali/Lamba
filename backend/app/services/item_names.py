"""
The bilingual names the merchant screens show for a catalog product.

The merchant API used to send only the English category (and the product's single `name`), so
the app showed "Spices & Sauces" in the Arabic UI. Every merchant response that describes a
catalog product takes these four fields from here, so they cannot drift apart:

    name_ar, name_en                  the product's own Arabic / English names (may be null)
    category_name_ar, category_name_en  the names of its category (may be null)

A missing name is None, never "": the app falls back to `name` / `category` itself.
"""

from typing import Any, Optional


def _clean(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def item_name_fields(gi: Any) -> dict:
    """
    name_ar / name_en / category_name_ar / category_name_en for a GlobalItem, as keyword
    arguments for a response schema.

    The category comes from `category_rel`, which GlobalItem loads with the item (lazy="joined").
    It is read from the instance dict, like GlobalItem.category does, so an item whose category
    was not loaded gives None instead of a lazy load that fails inside an async request.
    """
    category = getattr(gi, "__dict__", {}).get("category_rel")
    return {
        "name_ar": _clean(getattr(gi, "name_ar", None)),
        "name_en": _clean(getattr(gi, "name_en", None)),
        "category_name_ar": _clean(getattr(category, "name_ar", None)),
        "category_name_en": _clean(getattr(category, "name_en", None)),
    }
