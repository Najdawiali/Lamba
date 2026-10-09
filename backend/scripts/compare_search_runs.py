"""
Compare two runs of scripts/eval_search.py (the --worksheet files) query by query: what the top results were
before and after a change, which results left or entered, and whether any query lost all its results or lost
keyword-relevant ones. Standard library only.

    python backend/scripts/compare_search_runs.py before.jsonl after.jsonl
    python backend/scripts/compare_search_runs.py before.jsonl after.jsonl --only-changed --fail-on-regression

A "regression" is a query that went from some results to none, or whose keyword-matched results (the golden
set's notion of relevant) became fewer. A change in WHICH results appear is reported, not judged: after a
change to attribute filters, results should leave only when they do not have the queried attribute.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def load_worksheet(path: str) -> Dict[str, dict]:
    runs: Dict[str, dict] = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                entry = json.loads(line)
                runs[entry["query"]] = entry
    return runs


def _key(item: dict) -> str:
    return item.get("id") or item.get("name") or ""


@dataclass
class QueryDiff:
    query: str
    query_type: str
    status: str                       # same | changed | lost_all | gained_all | fewer_relevant | missing_before | missing_after
    before_count: int = 0
    after_count: int = 0
    overlap: float = 1.0
    top1_same: bool = True
    relevant_before: int = 0
    relevant_after: int = 0
    removed: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)

    @property
    def regression(self) -> bool:
        return self.status in ("lost_all", "fewer_relevant")


def diff_query(query: str, before: Optional[dict], after: Optional[dict]) -> QueryDiff:
    if before is None or after is None:
        entry = before or after
        return QueryDiff(query, entry.get("query_type", "") if entry else "",
                         "missing_before" if before is None else "missing_after")
    b_items, a_items = before.get("returned_items", []), after.get("returned_items", [])
    b_keys, a_keys = [_key(i) for i in b_items], [_key(i) for i in a_items]
    union = set(b_keys) | set(a_keys)
    overlap = len(set(b_keys) & set(a_keys)) / len(union) if union else 1.0
    relevant_before = sum(1 for i in b_items if i.get("matched_keyword"))
    relevant_after = sum(1 for i in a_items if i.get("matched_keyword"))
    removed = [i.get("name", "") for i in b_items if _key(i) not in set(a_keys)]
    added = [i.get("name", "") for i in a_items if _key(i) not in set(b_keys)]

    if b_items and not a_items:
        status = "lost_all"
    elif a_items and not b_items:
        status = "gained_all"
    elif relevant_after < relevant_before:
        status = "fewer_relevant"
    elif b_keys != a_keys:
        status = "changed"
    else:
        status = "same"
    return QueryDiff(
        query, before.get("query_type", ""), status, len(b_items), len(a_items), overlap,
        bool(b_keys and a_keys and b_keys[0] == a_keys[0]) or (not b_keys and not a_keys),
        relevant_before, relevant_after, removed, added,
    )


def compare_runs(before: Dict[str, dict], after: Dict[str, dict]) -> List[QueryDiff]:
    queries = list(before) + [q for q in after if q not in before]
    return [diff_query(q, before.get(q), after.get(q)) for q in queries]


def format_report(diffs: List[QueryDiff], *, only_changed: bool = False, max_names: int = 4) -> str:
    lines: List[str] = []
    for d in diffs:
        if only_changed and d.status == "same":
            continue
        mark = "REGRESSION" if d.regression else d.status
        lines.append(
            f"[{mark}] {d.query!r} ({d.query_type}): {d.before_count} -> {d.after_count} results, "
            f"relevant {d.relevant_before} -> {d.relevant_after}, overlap {d.overlap:.0%}, "
            f"top-1 {'same' if d.top1_same else 'different'}"
        )
        if d.removed:
            lines.append("    left:    " + " | ".join(d.removed[:max_names]) + (" ..." if len(d.removed) > max_names else ""))
        if d.added:
            lines.append("    entered: " + " | ".join(d.added[:max_names]) + (" ..." if len(d.added) > max_names else ""))
    total = len(diffs)
    by_status: Dict[str, int] = {}
    for d in diffs:
        by_status[d.status] = by_status.get(d.status, 0) + 1
    compared = [d for d in diffs if not d.status.startswith("missing")]
    mean_overlap = sum(d.overlap for d in compared) / len(compared) if compared else 1.0
    regressions = [d for d in diffs if d.regression]
    lines.append("")
    lines.append(f"{total} queries: " + ", ".join(f"{n} {s}" for s, n in sorted(by_status.items())))
    lines.append(f"mean overlap of the result lists: {mean_overlap:.0%}")
    lines.append(f"regressions (lost all results, or fewer keyword-relevant results): {len(regressions)}")
    for d in regressions:
        lines.append(f"    {d.query!r}: {d.status}")
    return "\n".join(lines)


def summary_lines(before_path: Optional[str], after_path: Optional[str]) -> List[str]:
    """Overall metrics from the two summary JSON files that eval_search.py writes (--output)."""
    if not (before_path and after_path):
        return []
    with open(before_path, encoding="utf-8") as f:
        before = json.load(f)["overall"]
    with open(after_path, encoding="utf-8") as f:
        after = json.load(f)["overall"]
    out = ["", "overall metrics (before -> after):"]
    for name in ("mrr_at_10", "recall_at_10", "ndcg_at_10", "fallback_rate", "latency_p50_ms", "latency_p90_ms", "latency_p95_ms"):
        if name in before and name in after:
            out.append(f"    {name:16} {before[name]:10.4f} -> {after[name]:10.4f}")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two eval_search.py worksheet runs")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--only-changed", action="store_true", help="leave out queries whose results did not change")
    parser.add_argument("--max-names", type=int, default=4, help="result names shown per query for what left or entered")
    parser.add_argument("--before-summary", help="the --output JSON of the first run (adds overall metrics)")
    parser.add_argument("--after-summary", help="the --output JSON of the second run")
    parser.add_argument("--fail-on-regression", action="store_true", help="exit with status 1 if any query regressed")
    args = parser.parse_args(argv)

    if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):  # Arabic names on the Windows console
        sys.stdout.reconfigure(encoding="utf-8")
    diffs = compare_runs(load_worksheet(args.before), load_worksheet(args.after))
    print(format_report(diffs, only_changed=args.only_changed, max_names=args.max_names))
    for line in summary_lines(args.before_summary, args.after_summary):
        print(line)
    return 1 if args.fail_on_regression and any(d.regression for d in diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
