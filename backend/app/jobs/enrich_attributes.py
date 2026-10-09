"""
Fill global_items.attributes for the barcode catalog from the product NAME — resumable, chunked.

Only catalog products (created_by IS NULL, listing_type 'product', not blocked) whose
attributes_version is NULL and that hold no extracted attribute yet are touched. Every
processed product gets attributes_version set, even when nothing could be extracted, so a rerun
never pays for it again. Existing attribute keys always win over extracted ones.

    # 1. sample for grading (reads only; writes a CSV to grade, a CSV of what the validator
    #    dropped, and prints a report with token counts and an items/s rate)
    docker compose run --rm --no-deps -v /opt/lamba/eval_data:/data api \
        python -m app.jobs.enrich_attributes --dry-run --limit 100 --seed 1 --out-dir /data

    # 2. how many products are waiting (counts only, no model calls)
    docker compose run --rm --no-deps api python -m app.jobs.enrich_attributes --stats

    # 3. the full run, in the background (resumable: run it again after any stop)
    docker compose run -d --no-deps --name attr_enrich -v /opt/lamba/eval_data:/data api \
        python -m app.jobs.enrich_attributes --concurrency 8 --out-dir /data

    # 4. after the run: 100 fresh processed products to grade, and every stored value per key
    docker compose run --rm --no-deps -v /opt/lamba/eval_data:/data api \
        python -m app.jobs.enrich_attributes --audit --limit 100 --seed 2 --out-dir /data

Calls go through the catalog circuit breaker, never search's, and wait out an open breaker
instead of racing through the queue. After 30 failed products in a row the job stops (credit
used up, provider down) instead of looping for hours; the stopped products stay pending.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Sequence

from sqlalchemy import text

from app.services.attribute_extraction import (
    EXTRACT_KEYS,
    PROMPT_VERSION,
    RESPONSE_FORMATS,
    Extraction,
    extract_attributes,
)

log = logging.getLogger("enrich_attributes")

CHUNK = 100
ATTEMPTS = 3
MAX_TOKENS = 200
CALL_TIMEOUT = 60.0
MAX_CONSECUTIVE_FAILURES = 30
# DeepInfra list price for google/gemma-4-31B-it on 2026-10-09 (docs.deepinfra.com). The cost in
# the report is an estimate from the token counts the API returns, not a bill.
INPUT_USD_PER_M = 0.20
OUTPUT_USD_PER_M = 0.40
PROBE_NAME = "حليب المراعي قليل الدسم 1 لتر"

# ── SQL (plain text, so the statements are readable and testable against any Postgres) ──────────
_KEY_ARRAY = "ARRAY[" + ", ".join("'%s'" % key for key in EXTRACT_KEYS) + "]"
_CATALOG = "listing_type = 'product' AND created_by IS NULL"
_HAS_EXTRACTED_KEYS = (
    "COALESCE(CASE WHEN jsonb_typeof(attributes) = 'object' THEN attributes END, CAST('{}' AS jsonb)) ?| "
    + _KEY_ARRAY
)
PENDING_WHERE = (
    f"{_CATALOG} AND moderation_status <> 'blocked' AND attributes_version IS NULL "
    f"AND NOT ({_HAS_EXTRACTED_KEYS})"
)
UPDATE_SQL = text(
    "UPDATE global_items SET "
    "attributes = CAST(:new AS jsonb) || CASE WHEN jsonb_typeof(attributes) = 'object' "
    "THEN attributes ELSE CAST('{}' AS jsonb) END, "
    "attributes_version = :version "
    "WHERE id = CAST(:id AS uuid) AND attributes_version IS NULL"
)
STATS_SQL = text(f"""
SELECT
  count(*) FILTER (WHERE {_CATALOG}) AS catalog_products,
  count(*) FILTER (WHERE {_CATALOG} AND moderation_status = 'blocked') AS blocked,
  count(*) FILTER (WHERE {_CATALOG} AND attributes_version = :v) AS done_current_version,
  count(*) FILTER (WHERE {_CATALOG} AND attributes_version < :v) AS done_older_version,
  count(*) FILTER (WHERE {_CATALOG} AND attributes_version IS NULL AND {_HAS_EXTRACTED_KEYS})
      AS has_attributes_but_no_version,
  count(*) FILTER (WHERE {PENDING_WHERE}) AS pending
FROM global_items
""")


async def fetch_pending(db, limit: Optional[int] = None, seed: Optional[int] = None) -> list[tuple[str, str]]:
    """(id, name) of pending products: by id, or in a repeatable random order when `seed` is given."""
    order = "md5(CAST(id AS text) || :seed)" if seed is not None else "id"
    sql = (
        "SELECT CAST(id AS text), COALESCE(NULLIF(btrim(name_ar), ''), name) "
        f"FROM global_items WHERE {PENDING_WHERE} ORDER BY {order}"
    )
    params: dict = {}
    if seed is not None:
        params["seed"] = str(seed)
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit
    rows = (await db.execute(text(sql), params)).all()
    return [(row[0], row[1]) for row in rows]


async def save_results(db, rows: Sequence[tuple[str, dict]], version: int = PROMPT_VERSION) -> int:
    """Write extracted attributes (existing keys win) and the version. Returns rows changed."""
    written = 0
    for item_id, attributes in rows:
        result = await db.execute(
            UPDATE_SQL,
            {"id": item_id, "new": json.dumps(attributes, ensure_ascii=False), "version": version},
        )
        written += result.rowcount or 0
    return written


async def fetch_stats(db, version: int = PROMPT_VERSION) -> dict:
    return dict((await db.execute(STATS_SQL, {"v": version})).mappings().one())


AUDIT_SAMPLE_SQL = text(
    "SELECT CAST(id AS text), COALESCE(NULLIF(btrim(name_ar), ''), name), attributes "
    f"FROM global_items WHERE {_CATALOG} AND attributes_version = :v "
    "ORDER BY md5(CAST(id AS text) || :seed) LIMIT :limit"
)
VALUE_COUNTS_SQL = text(
    "SELECT kv.key, kv.value, count(*) AS n "
    "FROM global_items g, LATERAL jsonb_each_text(CASE WHEN jsonb_typeof(g.attributes) = 'object' "
    "THEN g.attributes ELSE CAST('{}' AS jsonb) END) AS kv "
    "WHERE g.listing_type = 'product' AND g.created_by IS NULL AND g.attributes_version = :v "
    f"AND kv.key = ANY({_KEY_ARRAY}) "
    "GROUP BY kv.key, kv.value ORDER BY kv.key, n DESC, kv.value"
)


async def fetch_audit_sample(db, limit: int, seed: int, version: int = PROMPT_VERSION) -> list[tuple[str, str, dict]]:
    """A repeatable random sample of products the job already processed, with what is stored now."""
    rows = (await db.execute(AUDIT_SAMPLE_SQL, {"v": version, "seed": str(seed), "limit": limit})).all()
    sample = []
    for item_id, name, attributes in rows:
        if isinstance(attributes, str):  # a driver without the JSON codec hands back text
            attributes = json.loads(attributes)
        sample.append((item_id, name, attributes if isinstance(attributes, dict) else {}))
    return sample


async def fetch_value_counts(db, version: int = PROMPT_VERSION) -> dict[str, list[tuple[str, int]]]:
    """For each extracted key, every stored value with how many products carry it (most common first)."""
    counts: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key, value, n in (await db.execute(VALUE_COUNTS_SQL, {"v": version})).all():
        counts[key].append((value, int(n)))
    return dict(counts)


# ── Calling the model ──────────────────────────────────────────────────────────────────────────
async def breaker_gate(breaker, sleep=asyncio.sleep) -> None:
    """
    Batch jobs must WAIT OUT an open circuit breaker, not race through their queue (the same
    rule as app.jobs.import_catalog.breaker_gate). should_skip() resets the breaker once its
    cooldown has passed, so this loop ends by itself.
    """
    while breaker.should_skip():
        await sleep(2)


def make_call_chat(timeout: float = CALL_TIMEOUT):
    """The real provider call, through the catalog breaker. Imported lazily: tests never need it."""
    from app.config import settings
    from app.services.http_pool import deepinfra_catalog_breaker
    from app.services.llm import llm_adapter

    async def call_chat(messages, response_format):
        await breaker_gate(deepinfra_catalog_breaker)
        extra = {"response_format": response_format} if response_format else {}
        return await llm_adapter.complete_chat_full(
            messages=messages,
            model=settings.offline_llm_model,
            temperature=0.0,
            max_tokens=MAX_TOKENS,
            timeout=timeout,
            max_retries=1,
            breaker=deepinfra_catalog_breaker,
            **extra,
        )

    return call_chat


async def choose_response_format(call_chat, requested: str = "auto") -> str:
    """
    Which structured-output mode the model accepts. The provider documents json_schema and
    json_object, but not per model, so "auto" tries each on one fixed name (a few tokens).
    Raises RuntimeError when none answers, before the job spends anything on the queue.
    """
    modes = ["schema", "object", "none"] if requested == "auto" else [requested]
    for mode in modes:
        probe = await extract_attributes(PROBE_NAME, call_chat, RESPONSE_FORMATS[mode])
        if probe.status == "ok":
            return mode
        log.warning("response format %r failed the probe (%s)", mode, probe.status)
    raise RuntimeError(
        "The model did not answer the probe in any mode: check DeepInfra credit (HTTP 402), "
        "the API key and the model name."
    )


async def extract_patiently(
    name: str,
    call_chat,
    response_format: Optional[dict],
    keys=EXTRACT_KEYS,
    *,
    attempts: int = ATTEMPTS,
    sleep=asyncio.sleep,
    should_stop: Callable[[], bool] = lambda: False,
) -> Extraction:
    """Retry provider failures with a growing pause; an answer, even an empty one, ends it."""
    result = Extraction("no_response")
    for attempt in range(attempts):
        if should_stop():
            return Extraction("skipped")
        result = await extract_attributes(name, call_chat, response_format, keys)
        if result.status != "no_response":
            return result
        if attempt < attempts - 1:
            await sleep(5 * (attempt + 1))
    return result


# ── The run ────────────────────────────────────────────────────────────────────────────────────
@dataclass
class RunReport:
    total: int = 0
    statuses: Counter = field(default_factory=Counter)
    written: int = 0
    with_attributes: int = 0
    key_counts: Counter = field(default_factory=Counter)
    values: dict = field(default_factory=lambda: defaultdict(Counter))
    drops: Counter = field(default_factory=Counter)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    results: list = field(default_factory=list)    # (id, name, Extraction); kept for a dry run
    failures: list = field(default_factory=list)   # (id, name, status, raw)
    aborted: bool = False
    elapsed: float = 0.0

    @property
    def estimated_cost_usd(self) -> float:
        return (self.prompt_tokens * INPUT_USD_PER_M + self.completion_tokens * OUTPUT_USD_PER_M) / 1_000_000


@dataclass
class _Control:
    consecutive_failures: int = 0
    stop: bool = False


async def process(
    items: Sequence[tuple[str, str]],
    *,
    call_chat,
    response_format: Optional[dict],
    concurrency: int,
    save: Optional[Callable[[list], Awaitable[int]]] = None,
    keep_results: bool = False,
    keys=EXTRACT_KEYS,
    chunk_size: int = CHUNK,
    attempts: int = ATTEMPTS,
    max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
    sleep=asyncio.sleep,
) -> RunReport:
    """
    Extract every (id, name), `chunk_size` at a time. After each chunk the valid answers go to
    `save` (None for a dry run). Provider failures leave a product pending; too many in a row
    stop the run.
    """
    report = RunReport(total=len(items))
    sem = asyncio.Semaphore(concurrency)
    ctl = _Control()
    started = time.monotonic()

    async def one(item):
        item_id, name = item
        async with sem:
            if ctl.stop:
                return item_id, name, Extraction("skipped")
            result = await extract_patiently(
                name, call_chat, response_format, keys,
                attempts=attempts, sleep=sleep, should_stop=lambda: ctl.stop,
            )
        if result.status == "ok":
            ctl.consecutive_failures = 0
        elif result.status != "skipped":
            ctl.consecutive_failures += 1
            if ctl.consecutive_failures >= max_consecutive_failures:
                ctl.stop = True
        return item_id, name, result

    for start in range(0, len(items), chunk_size):
        outcomes = await asyncio.gather(*(one(item) for item in items[start:start + chunk_size]))
        to_save = []
        for item_id, name, result in outcomes:
            report.statuses[result.status] += 1
            report.prompt_tokens += result.prompt_tokens
            report.completion_tokens += result.completion_tokens
            if result.status == "ok":
                to_save.append((item_id, result.attributes))
                if result.attributes:
                    report.with_attributes += 1
                for key, value in result.attributes.items():
                    report.key_counts[key] += 1
                    report.values[key][str(value)] += 1
                for reason in result.dropped:
                    report.drops[reason] += 1
            elif result.status != "skipped":
                report.failures.append((item_id, name, result.status, result.raw))
            if keep_results:
                report.results.append((item_id, name, result))
        if save is not None and to_save:
            report.written += await save(to_save)

        done = min(start + chunk_size, len(items))
        elapsed = max(time.monotonic() - started, 1e-6)
        rate = done / elapsed
        log.info(
            "%d/%d  (%.1f items/s, ETA %.0f min)  %s  ~$%.2f",
            done, len(items), rate, (len(items) - done) / rate / 60 if rate else 0,
            dict(report.statuses), report.estimated_cost_usd,
        )
        if ctl.stop:
            report.aborted = True
            break

    report.elapsed = time.monotonic() - started
    return report


# ── Reports ────────────────────────────────────────────────────────────────────────────────────
def write_sample_csv(path: str, results: Sequence[tuple]) -> None:
    """The sheet to grade: fill in `correct` with y or n (and say what was wrong in `notes`)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "extracted_attributes", "correct", "notes"])
        for item_id, name, result in results:
            if result.status == "ok":
                writer.writerow([item_id, name, json.dumps(result.attributes, ensure_ascii=False), "", ""])


def write_drops_csv(path: str, results: Sequence[tuple]) -> None:
    """What the model said and what the validator removed, for tuning the prompt."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "model_reply", "dropped_by_validator"])
        for item_id, name, result in results:
            if result.status == "ok" and result.dropped:
                writer.writerow([item_id, name, result.raw, "; ".join(result.dropped)])


def write_failures_csv(path: str, failures: Sequence[tuple]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "status", "raw"])
        writer.writerows(failures)


def format_report(report: RunReport, *, dry_run: bool) -> str:
    done = report.statuses["ok"]
    lines = [
        "DRY RUN (nothing was written)" if dry_run else "RUN FINISHED" + (" - STOPPED EARLY" if report.aborted else ""),
        f"products asked: {report.total}  answered: {done}  statuses: {dict(report.statuses)}",
        f"with at least one attribute: {report.with_attributes}"
        + (f" ({100 * report.with_attributes / done:.0f}% of answered)" if done else ""),
        f"rows written: {report.written}",
        f"tokens: {report.prompt_tokens} in / {report.completion_tokens} out"
        f"  = ~${report.estimated_cost_usd:.3f} at list price"
        + (f"  (~${report.estimated_cost_usd / done:.5f} per product)" if done else ""),
        f"time: {report.elapsed:.0f}s" + (f"  = {done / report.elapsed:.2f} items/s" if report.elapsed and done else ""),
        f"attributes per key: {dict(report.key_counts)}",
        f"removed by the validator: {dict(report.drops)}",
    ]
    for key, counter in sorted(report.values.items()):
        lines.append(f"  {key}: " + ", ".join(f"{value} x{n}" for value, n in counter.most_common(12)))
    return "\n".join(lines)


def format_value_counts(counts: dict, per_key: int = 15) -> str:
    """The distinct stored values per key: systematic junk (a placeholder, a wrong word) shows up here."""
    lines = []
    for key in EXTRACT_KEYS:
        values = counts.get(key)
        if values:
            shown = ", ".join(f"{value} x{n}" for value, n in values[:per_key])
            more = f" (+{len(values) - per_key} more values)" if len(values) > per_key else ""
            lines.append(f"  {key}: {sum(n for _, n in values)} products, {len(values)} distinct: {shown}{more}")
    return "\n".join(lines) or "  (no extracted attributes stored yet)"


def ensure_writable(directory: str) -> None:
    """Fail before any money is spent if the reports cannot be written (e.g. no -v mount)."""
    os.makedirs(directory, exist_ok=True)
    probe = os.path.join(directory, ".write_test")
    with open(probe, "w", encoding="utf-8") as f:
        f.write("ok")
    os.remove(probe)


# ── Command line ───────────────────────────────────────────────────────────────────────────────
async def run(args, async_session) -> int:
    if not args.stats:
        ensure_writable(args.out_dir)

    async with async_session() as db:
        if args.stats:
            for name, value in (await fetch_stats(db)).items():
                print(f"{name}: {value}")
            return 0
        if args.audit:
            seed = 1 if args.seed is None else args.seed
            sample = await fetch_audit_sample(db, args.limit or 100, seed)
            counts = await fetch_value_counts(db)
            path = os.path.join(args.out_dir, f"attributes_audit_seed{seed}_n{len(sample)}.csv")
            write_sample_csv(path, [(i, n, Extraction("ok", attrs)) for i, n, attrs in sample])
            print(f"audit sheet ({len(sample)} processed products as stored now): {path}")
            print("stored values per key:\n" + format_value_counts(counts))
            return 0
        seed = (1 if args.seed is None else args.seed) if args.dry_run else args.seed
        items = await fetch_pending(db, args.limit, seed)
    print(f"pending catalog products selected: {len(items)}")
    if not items:
        print("Nothing to do.")
        return 0

    keys = tuple(k.strip() for k in args.keys.split(",") if k.strip())
    call_chat = make_call_chat(args.timeout)
    try:
        mode = await choose_response_format(call_chat, args.response_format)
    except RuntimeError as exc:
        print(f"STOPPED before processing anything: {exc}")
        return 2
    print(f"structured output mode: {mode}; keys: {', '.join(keys)}; concurrency: {args.concurrency}")

    async def save(rows):
        async with async_session() as db:
            written = await save_results(db, rows)
            await db.commit()
        return written

    report = await process(
        items,
        call_chat=call_chat,
        response_format=RESPONSE_FORMATS[mode],
        concurrency=args.concurrency,
        save=None if args.dry_run else save,
        keep_results=args.dry_run,
        keys=keys,
    )

    if args.dry_run:
        sample = os.path.join(args.out_dir, f"attributes_sample_seed{seed}_n{len(items)}.csv")
        drops = sample[:-4] + ".drops.csv"
        write_sample_csv(sample, report.results)
        write_drops_csv(drops, report.results)
        print(f"grading sheet: {sample}\nvalidator drops: {drops}")
    if report.failures:
        failures = os.path.join(args.out_dir, "attributes_failures.csv")
        write_failures_csv(failures, report.failures)
        print(f"{len(report.failures)} failures listed in {failures} (they stay pending)")
    print(format_report(report, dry_run=args.dry_run))
    if report.aborted:
        print(f"Stopped after {MAX_CONSECUTIVE_FAILURES} failed products in a row: check DeepInfra "
              "credit and status, then run the same command again; finished products are kept.")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fill global_items.attributes for catalog products from their names")
    p.add_argument("--dry-run", action="store_true",
                   help="read only: write a CSV to grade (random sample, see --seed) and print a report")
    p.add_argument("--stats", action="store_true", help="print counts only; no model calls")
    p.add_argument("--audit", action="store_true",
                   help="after a run: write a sheet to grade from already-processed products (--limit, --seed) "
                        "and print every stored value per key; no model calls, nothing is written to the database")
    p.add_argument("--limit", type=int, default=None, help="process at most N products (the sample size in a dry run)")
    p.add_argument("--seed", type=int, default=None,
                   help="repeatable random order; a dry run defaults to 1, a real run to by-id order")
    p.add_argument("--out-dir", default="/data", help="where reports are written (mount a host folder here)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--timeout", type=float, default=CALL_TIMEOUT, help="seconds per model call")
    p.add_argument("--response-format", choices=["auto", "schema", "object", "none"], default="auto",
                   help="structured output mode (auto tries schema, then object, then none)")
    p.add_argument("--keys", default=",".join(EXTRACT_KEYS),
                   help="comma-separated keys to keep; the others are dropped by the validator")
    return p


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    unknown = [k for k in (s.strip() for s in args.keys.split(",")) if k and k not in EXTRACT_KEYS]
    if unknown:
        parser.error(f"unknown keys: {', '.join(unknown)} (allowed: {', '.join(EXTRACT_KEYS)})")
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.setLevel(logging.INFO)

    from app.database import async_session, engine
    try:
        code = await run(args, async_session)
    finally:
        await engine.dispose()
    raise SystemExit(code)


if __name__ == "__main__":
    asyncio.run(main())
