"""
Review held products and user reports from the server.

    docker compose run --rm --no-deps api python -m app.moderation_cli pending
    docker compose run --rm --no-deps api python -m app.moderation_cli reports
    docker compose run --rm --no-deps api python -m app.moderation_cli approve <item-id> [--category <slug>]
    docker compose run --rm --no-deps api python -m app.moderation_cli block <item-id>

<item-id> may be the first 8+ characters of the product id, as printed by `pending`.
"""

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import String, cast, func, select, update

from app.database import async_session, engine
from app.models.category import Category
from app.models.global_item import GlobalItem
from app.models.market_item import MarketItem
from app.models.product_report import ProductReport
from app.models.user import User
from app.taxonomy import CATEGORY_BY_SLUG


async def _find_item(db, id_prefix: str) -> GlobalItem:
    rows = (await db.execute(
        select(GlobalItem).where(cast(GlobalItem.id, String).like(f"{id_prefix.lower()}%")).limit(2)
    )).unique().scalars().all()
    if len(rows) != 1:
        raise SystemExit(f"'{id_prefix}' matches {len(rows)} products; give more characters of the id.")
    return rows[0]


async def cmd_pending(db) -> None:
    open_reports = (
        select(ProductReport.global_item_id, func.count().label("n"))
        .where(ProductReport.status == "open").group_by(ProductReport.global_item_id).subquery()
    )
    stores = (select(MarketItem.item_id, func.count().label("n")).group_by(MarketItem.item_id).subquery())
    rows = (await db.execute(
        select(GlobalItem.id, GlobalItem.name, GlobalItem.restricted_reason, Category.slug,
               User.email, User.phone_number, func.coalesce(stores.c.n, 0), func.coalesce(open_reports.c.n, 0))
        .outerjoin(Category, Category.id == GlobalItem.category_id)
        .outerjoin(User, User.id == GlobalItem.created_by)
        .outerjoin(stores, stores.c.item_id == GlobalItem.id)
        .outerjoin(open_reports, open_reports.c.global_item_id == GlobalItem.id)
        .where(GlobalItem.moderation_status == "pending_review")
        .order_by(GlobalItem.restricted_reason, GlobalItem.name)
    )).all()
    print(f"{len(rows)} product(s) under review\n")
    for gid, name, reason, slug, email, phone, n_stores, n_reports in rows:
        who = email or phone or "catalog import"
        print(f"{str(gid)[:8]}  [{reason or '-'}]  {name}\n"
              f"          category={slug}  stores={n_stores}  open_reports={n_reports}  by={who}")


async def cmd_reports(db) -> None:
    rows = (await db.execute(
        select(GlobalItem.id, GlobalItem.name, GlobalItem.moderation_status,
               ProductReport.reason, func.count())
        .join(ProductReport, ProductReport.global_item_id == GlobalItem.id)
        .where(ProductReport.status == "open")
        .group_by(GlobalItem.id, GlobalItem.name, GlobalItem.moderation_status, ProductReport.reason)
        .order_by(func.count().desc())
    )).all()
    print(f"{len(rows)} open report group(s)\n")
    for gid, name, mod, reason, n in rows:
        print(f"{str(gid)[:8]}  {n}x {reason:<16} [{mod}]  {name}")


async def _close_reports(db, item_id, new_status: str) -> int:
    res = await db.execute(
        update(ProductReport)
        .where(ProductReport.global_item_id == item_id, ProductReport.status == "open")
        .values(status=new_status, reviewed_at=datetime.now(timezone.utc))
    )
    return res.rowcount or 0


async def cmd_approve(db, id_prefix: str, category: str | None) -> None:
    gi = await _find_item(db, id_prefix)
    if category:
        if category not in CATEGORY_BY_SLUG or CATEGORY_BY_SLUG[category].parent is None:
            raise SystemExit(f"'{category}' is not a category slug (see app/taxonomy.py).")
        gi.category_id = (await db.execute(select(Category.id).where(Category.slug == category))).scalar_one()
    gi.moderation_status = "approved"
    gi.restricted_reason = None
    closed = await _close_reports(db, gi.id, "dismissed")
    await db.commit()
    print(f"APPROVED  {gi.name}" + (f"  (category -> {category})" if category else "") + f"  | {closed} report(s) dismissed")


async def cmd_block(db, id_prefix: str) -> None:
    gi = await _find_item(db, id_prefix)
    gi.moderation_status = "blocked"
    gi.restricted_reason = gi.restricted_reason or "blocked_by_review"
    closed = await _close_reports(db, gi.id, "actioned")
    await db.commit()
    print(f"BLOCKED   {gi.name}  | {closed} report(s) actioned")


async def main() -> None:
    p = argparse.ArgumentParser(description="Review held products and user reports")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pending")
    sub.add_parser("reports")
    a = sub.add_parser("approve"); a.add_argument("item_id"); a.add_argument("--category")
    b = sub.add_parser("block"); b.add_argument("item_id")
    args = p.parse_args()
    try:
        async with async_session() as db:
            if args.cmd == "pending":
                await cmd_pending(db)
            elif args.cmd == "reports":
                await cmd_reports(db)
            elif args.cmd == "approve":
                await cmd_approve(db, args.item_id, args.category)
            else:
                await cmd_block(db, args.item_id)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
