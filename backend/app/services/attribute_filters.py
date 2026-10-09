"""
SQL for the attribute filters of hybrid search: turns the plan from attribute_rules into clauses.

Booleans and enumerated values use JSONB containment (attributes @> '{"organic": true}'), which
matches only a real stored value and can never raise on odd data. The old CAST(... AS Boolean)
was a database error for any stored non-boolean string, so one bad row could break every
"organic" search. Text keys keep their substring match with the name fallback.
"""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import or_

from app.services.attribute_rules import AttrFilter


def build_attribute_clauses(
    plans: Sequence[AttrFilter],
    *,
    attributes: Any,
    name: Any,
    name_ar: Any,
    search_terms: Any,
) -> list:
    """One WHERE clause per planned filter (they are ANDed by the caller)."""
    clauses = []
    for plan in plans:
        if plan.kind == "bool":
            clauses.append(attributes.contains({plan.key: plan.value}))
        elif plan.kind == "enum":
            parts = [attributes.contains({plan.key: stored}) for stored in plan.stored]
            for word in plan.name_words:
                parts.extend([name.ilike(f"%{word}%"), name_ar.ilike(f"%{word}%")])
            clauses.append(or_(*parts))
        elif plan.kind == "brand":
            parts = []
            for variant in plan.variants:
                parts.extend([
                    attributes["brand"].as_string().ilike(f"%{variant}%"),
                    name.ilike(f"%{variant}%"),
                    name_ar.ilike(f"%{variant}%"),
                    search_terms.ilike(f"%{variant}%"),
                ])
            clauses.append(or_(*parts))
        else:  # "text"
            parts = []
            for variant in plan.variants:
                parts.extend([
                    attributes[plan.key].as_string().ilike(f"%{variant}%"),
                    name.ilike(f"%{variant}%"),
                    name_ar.ilike(f"%{variant}%"),
                ])
            clauses.append(or_(*parts))
    return clauses
