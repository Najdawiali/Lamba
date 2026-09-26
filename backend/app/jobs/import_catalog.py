"""
Import the barcode reference catalog into global_items — resumable, idempotent.

Each row goes through the same pipeline as a merchant's manual add: two-model
classification (restriction + category), search-term enrichment, embedding.
Imported products have no store link, so customers see nothing until a merchant
stocks them. created_by stays NULL, which marks catalog imports.

    # pilot: 50 products
    docker compose run --rm --no-deps -v /opt/lamba/import_data:/data api \
        python -m app.jobs.import_catalog --csv /data/lamba_barcode_catalog.csv --limit 50
    # full run (detached; follow with: docker logs -f catalog_import)
    docker compose run -d --no-deps --name catalog_import -v /opt/lamba/import_data:/data api \
        python -m app.jobs.import_catalog --csv /data/lamba_barcode_catalog.csv
    # later: re-enrich imported products whose LLM search terms failed
    docker compose run --rm --no-deps api python -m app.jobs.import_catalog --retry-enrichment

Rerunning is safe: barcodes already in the database are skipped. Products whose
classification could not be obtained (LLM unavailable) are NOT inserted, so the
next run retries them instead of filling the review queue with outages.
Rows the classifier could not place in a category go to <csv dir>/import_unresolved.csv.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import time
from collections import Counter

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import async_session, engine
from app.models.category import Category
from app.models.global_item import GlobalItem
from app.services.item_classifier import classify_item_ensemble, restricted_reason_for
from app.services.item_enrichment import enrich_and_embed
from app.utils.barcode import normalize_barcode

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("import_catalog")
log.setLevel(logging.INFO)

CHUNK = 100


def read_rows(path: str) -> list[dict]:
    rows, seen = [], set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            code = normalize_barcode(r.get("gtin14") or r.get("barcode"))
            name = (r.get("name_ar") or r.get("name") or "").strip()
            if code and name and code not in seen:
                seen.add(code)
                rows.append({"barcode": code, "name": name})
    return rows


async def build_item(row: dict, cats: dict, sem: asyncio.Semaphore, stats: Counter, unresolved: list) -> GlobalItem | None:
    async with sem:
        verdict = await classify_item_ensemble(row["name"], None, "product")
        if not verdict.restriction_known:
            stats["retry_later (classifier unavailable)"] += 1
            return None
        cat = cats.get(verdict.category_slug)
        if cat is None:
            stats["no_category"] += 1
            unresolved.append(row)
            return None
        gi = GlobalItem(
            name=row["name"],
            name_ar=row["name"],
            barcode=row["barcode"],
            listing_type="product",
            category_id=cat[0],
            created_by=None,
            moderation_status=verdict.moderation_status,
            restricted_reason=restricted_reason_for(verdict),
        )
        await enrich_and_embed(gi, cat[1], use_llm=True)
        stats[gi.moderation_status] += 1
        stats[f"embedding: {gi.embedding_status}"] += 1
        if verdict.restricted:
            stats[f"flagged: {verdict.restricted}"] += 1
        return gi


async def save_chunk(items: list[GlobalItem], stats: Counter) -> None:
    async with async_session() as db:
        db.add_all(items)
        try:
            await db.commit()
            return
        except IntegrityError:
            await db.rollback()
    # A barcode appeared meanwhile (e.g. a merchant added it): save one by one, skip duplicates
    for gi in items:
        async with async_session() as db:
            db.add(gi)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                stats["skipped: barcode appeared meanwhile"] += 1


async def run_import(csv_path: str, limit: int | None, concurrency: int) -> None:
    rows = read_rows(csv_path)
    async with async_session() as db:
        cats = {s: (cid, en or n) for s, cid, en, n in (await db.execute(
            select(Category.slug, Category.id, Category.name_en, Category.name)
            .where(Category.parent_category_id.is_not(None))
        )).all()}
        existing = set((await db.execute(
            select(GlobalItem.barcode).where(GlobalItem.barcode.is_not(None))
        )).scalars().all())

    todo = [r for r in rows if r["barcode"] not in existing]
    if limit:
        todo = todo[:limit]
    log.info("catalog rows: %d | already imported: %d | to import now: %d | categories: %d",
             len(rows), len(rows) - len([r for r in rows if r["barcode"] not in existing]), len(todo), len(cats))

    stats, unresolved = Counter(), []
    sem = asyncio.Semaphore(concurrency)
    started = time.monotonic()
    for i in range(0, len(todo), CHUNK):
        chunk = todo[i:i + CHUNK]
        built = await asyncio.gather(*(build_item(r, cats, sem, stats, unresolved) for r in chunk))
        items = [gi for gi in built if gi is not None]
        if items:
            await save_chunk(items, stats)
        done = i + len(chunk)
        rate = done / max(time.monotonic() - started, 1e-6)
        eta_min = (len(todo) - done) / rate / 60 if rate else 0
        log.info("%d/%d  (%.1f items/s, ETA %.0f min)  %s", done, len(todo), rate, eta_min, dict(stats))

    if unresolved:
        out = os.path.join(os.path.dirname(csv_path) or ".", "import_unresolved.csv")
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["barcode", "name"])
            w.writeheader()
            w.writerows(unresolved)
        log.info("unresolved rows written to %s", out)
    log.info("DONE in %.0f min: %s", (time.monotonic() - started) / 60, dict(stats))


async def run_retry_enrichment(concurrency: int) -> None:
    async with async_session() as db:
        rows = (await db.execute(
            select(GlobalItem, Category.name_en, Category.name)
            .join(Category, Category.id == GlobalItem.category_id)
            .where(GlobalItem.created_by.is_(None), GlobalItem.embedding_status != "completed")
        )).unique().all()
        log.info("imported products needing enrichment: %d", len(rows))
        sem, stats = asyncio.Semaphore(concurrency), Counter()

        async def one(gi, en, n):
            async with sem:
                await enrich_and_embed(gi, en or n, use_llm=True)
                stats[gi.embedding_status] += 1

        for i in range(0, len(rows), CHUNK):
            await asyncio.gather(*(one(*r) for r in rows[i:i + CHUNK]))
            await db.commit()
            log.info("%d/%d  %s", min(i + CHUNK, len(rows)), len(rows), dict(stats))


async def main() -> None:
    p = argparse.ArgumentParser(description="Import the barcode catalog into global_items")
    p.add_argument("--csv", help="lamba_barcode_catalog.csv (columns: gtin14, name_ar)")
    p.add_argument("--limit", type=int, default=None, help="import at most N new products (pilot)")
    p.add_argument("--concurrency", type=int, default=12)
    p.add_argument("--retry-enrichment", action="store_true")
    a = p.parse_args()
    try:
        if a.retry_enrichment:
            await run_retry_enrichment(a.concurrency)
        elif a.csv:
            await run_import(a.csv, a.limit, a.concurrency)
        else:
            p.error("--csv is required (or use --retry-enrichment)")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
