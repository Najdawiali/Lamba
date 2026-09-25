"""
Sync app/taxonomy.py into the `categories` table.

    python -m app.taxonomy_sync            # add/update by slug, report extras
    python -m app.taxonomy_sync --prune    # also delete extras that are unused

Idempotent: safe to run on every deploy. Categories are matched by `slug`, so
renaming one in taxonomy.py updates its names in place (same id, products keep
their category).

--prune never deletes a category that still has products or subcategories:
categories -> global_items is ON DELETE CASCADE, so deleting a used category
would silently delete its products.
"""

import argparse
import asyncio
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.database import engine
from app.models import Category, GlobalItem
from app.taxonomy import CATEGORIES, CATEGORY_BY_SLUG

cat = Category.__table__
item = GlobalItem.__table__


async def sync(prune: bool) -> None:
    async with engine.begin() as conn:
        # Sections first, so children can resolve their parent id
        ordered = [c for c in CATEGORIES if c.parent is None] + [c for c in CATEGORIES if c.parent is not None]
        created = updated = 0

        for c in ordered:
            parent_id = None
            if c.parent is not None:
                parent_id = (
                    await conn.execute(select(cat.c.id).where(cat.c.slug == c.parent))
                ).scalar_one()

            values = {
                "name": c.name_en,  # legacy column still read by older code paths
                "name_en": c.name_en,
                "name_ar": c.name_ar,
                "listing_type": c.listing_type,
                "icon": c.icon,
                "sort_order": c.sort_order,
                "parent_category_id": parent_id,
            }
            existed = (
                await conn.execute(select(cat.c.id).where(cat.c.slug == c.slug))
            ).scalar_one_or_none() is not None

            stmt = insert(cat).values(id=uuid.uuid4(), slug=c.slug, **values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[cat.c.slug],
                set_={k: stmt.excluded[k] for k in values},
            )
            await conn.execute(stmt)
            if existed:
                updated += 1
            else:
                created += 1

        # Categories in the DB that are not in taxonomy.py
        rows = (await conn.execute(select(cat.c.id, cat.c.slug, cat.c.name))).all()
        extras = [r for r in rows if r.slug not in CATEGORY_BY_SLUG]
        pruned, kept = [], []
        for r in extras:
            n_items = (
                await conn.execute(select(func.count()).select_from(item).where(item.c.category_id == r.id))
            ).scalar_one()
            n_children = (
                await conn.execute(select(func.count()).select_from(cat).where(cat.c.parent_category_id == r.id))
            ).scalar_one()
            if prune and n_items == 0 and n_children == 0:
                await conn.execute(cat.delete().where(cat.c.id == r.id))
                pruned.append(r.slug)
            else:
                kept.append(f"{r.slug} ({r.name}): {n_items} products, {n_children} subcategories")

        total = (await conn.execute(select(func.count()).select_from(cat))).scalar_one()

    print(f"created: {created}  updated: {updated}  total in DB: {total}")
    if pruned:
        print(f"pruned (unused, not in taxonomy): {', '.join(pruned)}")
    if kept:
        print("NOT in taxonomy but kept:")
        for line in kept:
            print(f"  - {line}")


async def _run(prune: bool) -> None:
    try:
        await sync(prune)
    finally:
        await engine.dispose()  # same event loop as the connections


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync app/taxonomy.py into the categories table")
    parser.add_argument("--prune", action="store_true", help="delete unused categories that are not in taxonomy.py")
    args = parser.parse_args()
    asyncio.run(_run(prune=args.prune))


if __name__ == "__main__":
    main()
