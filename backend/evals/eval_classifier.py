"""
Offline evaluation of app.services.item_classifier — no database access.

Runs the production `classify_item` over the test sets for one or more models,
writes grading sheets (CSV, opens in Excel) and prints metrics.

    docker compose run --rm --no-deps \
        -v /opt/lamba/backend/evals:/app/evals -v /opt/lamba/eval_data:/data \
        api python -m evals.eval_classifier --split dev --data /data

Splits:
  dev      enrichment_dev_sample.csv (categories) + restricted_test_cases.csv
  holdout  enrichment_holdout_sample.csv         + restricted_holdout.csv
           Run holdout ONLY once the prompt is final: it measures whether the
           prompt generalizes, so it must never be used to tune it.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import statistics
from collections import Counter

from app.services.item_classifier import classify_item
from app.taxonomy import CATEGORY_BY_SLUG

SPLITS = {
    "dev": ("enrichment_dev_sample.csv", "restricted_test_cases.csv"),
    "holdout": ("enrichment_holdout_sample.csv", "restricted_holdout.csv"),
}
DEFAULT_MODELS = ["google/gemma-4-26B-A4B-it", "google/gemma-4-31B-it"]


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


async def classify_all(names: list[str], model: str, concurrency: int, timeout: float):
    sem = asyncio.Semaphore(concurrency)

    async def one(n: str):
        async with sem:
            return await classify_item(n, model=model, timeout=timeout)

    return await asyncio.gather(*(one(n) for n in names))


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def category_cols(slug: str | None) -> dict:
    if not slug:
        return {"category_slug": "", "category_ar": "", "section_ar": ""}
    c = CATEGORY_BY_SLUG[slug]
    return {"category_slug": slug, "category_ar": c.name_ar, "section_ar": CATEGORY_BY_SLUG[c.parent].name_ar}


def load_prior_grades(path: str | None) -> dict[tuple[str, str], str]:
    """(name_ar, category_slug) -> y/n from an earlier graded sheet."""
    if not path:
        return {}
    grades = {}
    for r in read_csv(path):
        g = (r.get("grade_category") or "").strip().lower()
        if g in ("y", "n") and r.get("category_slug"):
            grades[(r["name_ar"], r["category_slug"])] = g
    return grades


async def evaluate(model: str, split: str, data_dir: str, out_dir: str, concurrency: int,
                   timeout: float, prior: dict) -> None:
    short = model.split("/")[-1]
    cat_file, res_file = SPLITS[split]
    cat_rows = read_csv(os.path.join(data_dir, cat_file))
    res_rows = read_csv(os.path.join(data_dir, res_file))

    cat_results = await classify_all([r["name_ar"] for r in cat_rows], model, concurrency, timeout)
    res_results = await classify_all([r["name_ar"] for r in res_rows], model, concurrency, timeout)
    all_results = cat_results + res_results

    # ── Grading sheet: categories (fill grade_category with y / n) ──
    # Grades carry over when the product got the same category as in the prior sheet.
    sheet, carried, to_grade = [], 0, 0
    for r, res in zip(cat_rows, cat_results):
        g = prior.get((r["name_ar"], res.category_slug or ""), "")
        carried += bool(g)
        to_grade += not g
        sheet.append({
            "name_ar": r["name_ar"],
            "stratum": r.get("stratum", ""),
            **category_cols(res.category_slug),
            "moderation": res.moderation_status,
            "restricted": res.restricted or "",
            "error": res.error or "",
            "grade_category": g,
        })
    write_csv(os.path.join(out_dir, f"{split}_categories_{short}.csv"), sheet)

    # ── Restriction results (labelled, scored automatically) ──
    outcome = Counter()
    res_sheet = []
    for r, res in zip(res_rows, res_results):
        expected = r["expected_restricted"]
        status = res.moderation_status
        if not res.restriction_known:
            kind = "held_llm_error"
        elif expected == "none":
            kind = "correct_pass" if status == "approved" else "FALSE_FLAG"
        elif status == "approved":
            kind = "MISSED"
        else:
            kind = "caught" if res.restricted == expected else "caught_wrong_class"
        outcome[(expected == "none", kind)] += 1
        res_sheet.append({
            "name_ar": r["name_ar"],
            "expected": expected,
            "predicted": res.restricted or "none",
            "moderation": status,
            "outcome": kind,
            "error": res.error or "",
            "note": r.get("note", ""),
            "raw": res.raw[:200],
        })
    write_csv(os.path.join(out_dir, f"{split}_restricted_{short}.csv"), res_sheet)

    # ── Summary ──
    n_pos = sum(1 for r in res_rows if r["expected_restricted"] != "none")
    n_neg = len(res_rows) - n_pos
    lat = sorted(x.latency_ms for x in all_results)
    errors = Counter(x.error for x in all_results if x.error)
    flagged_in_catalog = [(r["name_ar"], x.restricted or x.error) for r, x in zip(cat_rows, cat_results)
                          if x.moderation_status != "approved"]

    print(f"\n══════ {model} — {split} ══════")
    print(f"calls: {len(all_results)}  errors: {dict(errors) or 'none'}")
    print(f"latency ms  p50={statistics.median(lat):.0f}  p95={lat[int(0.95 * (len(lat) - 1))]:.0f}  max={lat[-1]}")
    print(f"\nRESTRICTED ITEMS ({n_pos} that must be held)")
    for k in ("caught", "caught_wrong_class", "held_llm_error", "MISSED"):
        print(f"  {k:<20} {pct(outcome[(False, k)], n_pos)}")
    print(f"LOOK-ALIKES ({n_neg} that must pass)")
    for k in ("correct_pass", "held_llm_error", "FALSE_FLAG"):
        print(f"  {k:<20} {pct(outcome[(True, k)], n_neg)}")
    print(f"\nCATALOG SAMPLE ({len(cat_rows)} real products)")
    print(f"  flagged for review: {len(flagged_in_catalog)} {flagged_in_catalog if flagged_in_catalog else ''}")
    print(f"  no valid category: {sum(1 for x in cat_results if not x.category_slug)}")
    graded = [row for row in sheet if row["grade_category"] in ("y", "n")]
    if graded:
        ok = sum(row["grade_category"] == "y" for row in graded)
        print(f"  category grades carried over: {carried}  (correct {ok}/{len(graded)})  -> still to grade: {to_grade}")
    print(f"  sheets: {split}_categories_{short}.csv, {split}_restricted_{short}.csv")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=list(SPLITS), default="dev")
    p.add_argument("--data", default="/data", help="folder with the test CSVs")
    p.add_argument("--out", default=None, help="output folder (default: <data>/results)")
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--timeout", type=float, default=12.0, help="per-call LLM timeout in seconds")
    p.add_argument("--carry-grades", default=None, help="earlier graded categories CSV; unchanged predictions keep their grade")
    args = p.parse_args()

    out_dir = args.out or os.path.join(args.data, "results")
    os.makedirs(out_dir, exist_ok=True)
    prior = load_prior_grades(args.carry_grades)
    for m in args.models:
        await evaluate(m, args.split, args.data, out_dir, args.concurrency, args.timeout, prior)


if __name__ == "__main__":
    asyncio.run(main())
