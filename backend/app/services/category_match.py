"""
Matching the category the query model names against the taxonomy: EXACT names only.

The model's category is loose: an Arabic word ("شاي"), a section in English ("Beverages"), a slug-like
word ("dairy"), or nothing, and for the same query it can change from call to call. A substring match
turned that into unstable and sometimes wrong boosts (a plain "حليب" matched "حليب وطعام أطفال", the baby
formula category). Now only a case-insensitive match of the whole name (name, name_ar or name_en) counts;
anything else is ignored and search runs without a category for that query. The boost goes to results in the
matched category and its subcategories, by exact category name as well.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Set


def exact_name_forms(*names: Any) -> Set[str]:
    """The names as they are compared: stripped and lower-cased; non-strings and blanks are dropped."""
    return {name.strip().lower() for name in names if isinstance(name, str) and name.strip()}


def exact_category_clause(category: Any, name: str):
    """SQL for "this category's name, Arabic name or English name equals `name`", case-insensitively."""
    from sqlalchemy import func, or_

    wanted = name.strip().lower()
    return or_(
        func.lower(category.name) == wanted,
        func.lower(category.name_ar) == wanted,
        func.lower(category.name_en) == wanted,
    )


def boost_matching_category(fused: Iterable[dict], category_names: Set[str], factor: float = 1.5) -> int:
    """Multiply the rrf_score of the candidates whose category is one of `category_names`; returns how many."""
    boosted = 0
    for candidate in fused:
        item_names = exact_name_forms(
            candidate.get("category"), candidate.get("category_name_ar"), candidate.get("category_name_en")
        )
        if item_names & category_names:
            candidate["rrf_score"] *= factor
            boosted += 1
    return boosted
