"""
Lamba Search Benchmark
======================

Evaluates search quality against a golden dataset using standard IR metrics.
Run before and after any search change to measure impact objectively.

Setup (once — seeds the diverse catalog the benchmark expects):
    docker exec eagle_api python scripts/seed_diverse.py

Usage:
    docker exec eagle_api python scripts/benchmark_search.py
    docker exec eagle_api python scripts/benchmark_search.py --save baseline
    docker exec eagle_api python scripts/benchmark_search.py --compare baseline
    docker exec eagle_api python scripts/benchmark_search.py --category brand

Metrics:
    MRR       Where does the first relevant result appear? 1.0 = always first.
    NDCG@5    Quality of the top-5 ranking. Rewards best items highest.
    P@3       What fraction of the top 3 are relevant?
    Recall    Of all expected items, how many appeared anywhere?
    Noise     Fraction of results that should NOT be there. Lower is better.
"""

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import httpx

DEFAULT_LAT = 32.0385
DEFAULT_LON = 35.7275


# ══════════════════════════════════════════════════════════════════
# GOLDEN DATASET
# ══════════════════════════════════════════════════════════════════
GOLDEN_CASES = [
    # ══ SPECIFIC PRODUCT ═════════════════════════════════════════
    {"query": "بطيخ", "category": "specific",
     "must_contain": ["بطيخ"],
     "must_not": ["Hibiscus", "شاي", "لحم", "شامبو"],
     "min_results": 1, "max_results": 5},

    {"query": "مكنسة", "category": "specific",
     "must_contain": ["مكنسة"],
     "must_not": ["شاي", "لحم", "بطيخ", "دفتر"],
     "min_results": 1, "max_results": 8},

    {"query": "مجرود حديد", "category": "specific",
     "must_contain": ["مجرود", "حديد"],
     "must_not": ["شاي", "حليب", "شامبو", "بطيخ"],
     "min_results": 1, "max_results": 8},

    {"query": "طقم فناجين", "category": "specific",
     "must_contain": ["فناجين", "طقم"],
     "must_not": ["لحم", "شاي أخضر", "حديد"],
     "min_results": 1, "max_results": 8},

    {"query": "دفتر", "category": "specific",
     "must_contain": ["دفتر"],
     "must_not": ["شاي", "لحم", "حديد", "شامبو"],
     "min_results": 1, "max_results": 8},

    {"query": "بطارية سيارة", "category": "specific",
     "must_contain": ["بطارية"],
     "must_not": ["شاي", "خبز", "شامبو"],
     "min_results": 1, "max_results": 8},

    {"query": "لحم", "category": "specific",
     "must_contain": ["لحم"],
     "must_not": ["جبنة", "حليب", "شاي", "حديد"],
     "min_results": 1, "max_results": 10},

    {"query": "حليب", "category": "specific",
     "must_contain": ["حليب", "Milk"],
     "must_not": ["لحم", "حديد", "شامبو"],
     "min_results": 1, "max_results": 10},

    # ══ BRAND RECOGNITION ════════════════════════════════════════
    {"query": "شامبو هيد اند شولدرز", "category": "brand",
     "must_contain": ["هيد اند شولدرز", "Head"],
     "must_not": ["لحم", "حديد", "بطيخ"],
     "min_results": 1, "max_results": 8},

    {"query": "Head and Shoulders", "category": "brand",
     "must_contain": ["هيد اند شولدرز", "Head"],
     "must_not": ["لحم", "حديد"],
     "min_results": 1, "max_results": 8},

    {"query": "بانتين", "category": "brand",
     "must_contain": ["بانتين", "Pantene"],
     "must_not": ["لحم", "حديد", "شاي"],
     "min_results": 1, "max_results": 8},

    {"query": "تيفال", "category": "brand",
     "must_contain": ["تيفال", "Tefal"],
     "must_not": ["شاي", "لحم", "حديد"],
     "min_results": 1, "max_results": 8},

    {"query": "بنادول", "category": "brand",
     "must_contain": ["بنادول", "Panadol"],
     "must_not": ["شاي", "لحم", "حديد"],
     "min_results": 1, "max_results": 8},

    # ══ CONDITION / STATE ════════════════════════════════════════
    {"query": "تلفون مستعمل", "category": "condition",
     "must_contain": ["مستعمل", "تلفون", "آيفون", "شاومي"],
     "must_not": ["شاي", "لحم", "حديد", "شامبو"],
     "min_results": 1, "max_results": 10},

    {"query": "آيفون مستعمل", "category": "condition",
     "must_contain": ["آيفون", "iPhone"],
     "must_not": ["شاي", "لحم", "حديد"],
     "min_results": 1, "max_results": 8},

    {"query": "تلفون جديد", "category": "condition",
     "must_contain": ["جديد", "سامسونج", "Samsung"],
     "must_not": ["شاي", "لحم", "حديد"],
     "min_results": 1, "max_results": 10},

    # ══ VARIANT TOLERANCE ════════════════════════════════════════
    {"query": "بطيخ اصفر", "category": "variant",
     "must_contain": ["بطيخ"],
     "must_not": ["شاي", "لحم", "حديد"],
     "min_results": 1, "max_results": 5},

    {"query": "مجرود حديد 14 مم", "category": "variant",
     "must_contain": ["مجرود", "حديد"],
     "must_not": ["شاي", "شامبو", "بطيخ"],
     "min_results": 1, "max_results": 8},

    {"query": "شنطة ظهر", "category": "variant",
     "must_contain": ["شنطة"],
     "must_not": ["شاي", "لحم", "حديد"],
     "min_results": 1, "max_results": 8},

    # ══ SPEC / SIZE ══════════════════════════════════════════════
    {"query": "مكنسة 2000 واط", "category": "spec",
     "must_contain": ["مكنسة"],
     "must_not": ["شاي", "لحم", "بطيخ"],
     "min_results": 1, "max_results": 8},

    {"query": "زيت محرك 5W-30", "category": "spec",
     "must_contain": ["زيت محرك", "5W-30"],
     "must_not": ["شاي", "بطيخ", "شامبو"],
     "min_results": 1, "max_results": 8},

    {"query": "شامبو 400 مل", "category": "spec",
     "must_contain": ["شامبو"],
     "must_not": ["لحم", "حديد", "بطيخ"],
     "min_results": 1, "max_results": 10},

    # ══ FINE-GRAINED ═════════════════════════════════════════════
    {"query": "شاي أخضر", "category": "fine_grained",
     "must_contain": ["شاي أخضر"],
     "must_not": ["لحم", "حديد", "شامبو"],
     "min_results": 1, "max_results": 15},

    {"query": "فلتر زيت", "category": "fine_grained",
     "must_contain": ["فلتر زيت"],
     "must_not": ["شاي", "خبز", "شامبو"],
     "min_results": 1, "max_results": 8},

    {"query": "فلتر هواء", "category": "fine_grained",
     "must_contain": ["فلتر هواء"],
     "must_not": ["شاي", "خبز", "شامبو"],
     "min_results": 1, "max_results": 8},

    # ══ INTENT / USE-CASE ════════════════════════════════════════
    {"query": "حاجات للفطور", "category": "intent",
     "must_contain": ["خبز", "بيض", "جبنة", "لبنة", "زيتون"],
     "must_not": ["حديد", "شامبو", "بطارية"],
     "min_results": 2, "max_results": 20},

    {"query": "مستلزمات مدرسية", "category": "intent",
     "must_contain": ["دفتر", "أقلام", "شنطة", "ألوان", "حاسبة"],
     "must_not": ["لحم", "حديد", "بطارية سيارة"],
     "min_results": 2, "max_results": 20},

    {"query": "شي لتنظيف البيت", "category": "intent",
     "must_contain": ["مكنسة", "ممسحة", "فرشاة", "تنظيف"],
     "must_not": ["لحم", "بطيخ", "بنادول"],
     "min_results": 1, "max_results": 20},

    {"query": "شي لوجع الراس", "category": "intent",
     "must_contain": ["بنادول", "Panadol", "مسكن"],
     "must_not": ["لحم", "حديد", "شاي أخضر"],
     "min_results": 1, "max_results": 15},

    {"query": "أشياء للعناية بالشعر", "category": "intent",
     "must_contain": ["شامبو", "بلسم", "زيت شعر"],
     "must_not": ["لحم", "حديد", "دفتر"],
     "min_results": 1, "max_results": 15},

    {"query": "فواكه ممكن اعصرها", "category": "intent",
     "must_contain": ["برتقال", "تفاح", "عصير", "مانجا", "بطيخ"],
     "must_not": ["لحم", "حديد", "شامبو"],
     "min_results": 1, "max_results": 20},

    {"query": "حاجات للسيارة", "category": "intent",
     "must_contain": ["فلتر", "زيت محرك", "بطارية", "مساحات"],
     "must_not": ["خبز", "شاي أخضر", "دفتر"],
     "min_results": 1, "max_results": 20},

    # ══ COLLOQUIAL JORDANIAN ═════════════════════════════════════
    {"query": "بدي شاي", "category": "colloquial",
     "must_contain": ["شاي", "Tea"],
     "must_not": ["لحم", "حديد", "شامبو"],
     "min_results": 1, "max_results": 15},

    {"query": "عندكم خبز", "category": "colloquial",
     "must_contain": ["خبز"],
     "must_not": ["حديد", "شامبو", "بطارية"],
     "min_results": 1, "max_results": 10},

    {"query": "بدي شاحن تلفون", "category": "colloquial",
     "must_contain": ["شاحن"],
     "must_not": ["لحم", "خبز", "بطيخ"],
     "min_results": 1, "max_results": 10},

    {"query": "في عندكم مكنسة", "category": "colloquial",
     "must_contain": ["مكنسة"],
     "must_not": ["لحم", "شاي", "بطيخ"],
     "min_results": 1, "max_results": 10},

    # ══ CROSS-LANGUAGE ═══════════════════════════════════════════
    {"query": "tea", "category": "cross_lang",
     "must_contain": ["شاي", "Tea"],
     "must_not": ["لحم", "حديد"],
     "min_results": 1, "max_results": 20},

    {"query": "vacuum cleaner", "category": "cross_lang",
     "must_contain": ["مكنسة", "Vacuum"],
     "must_not": ["شاي", "لحم", "بطيخ"],
     "min_results": 1, "max_results": 10},

    {"query": "shampoo", "category": "cross_lang",
     "must_contain": ["شامبو", "Shampoo"],
     "must_not": ["لحم", "حديد", "بطيخ"],
     "min_results": 1, "max_results": 10},

    {"query": "used phone", "category": "cross_lang",
     "must_contain": ["مستعمل", "Used", "تلفون", "iPhone"],
     "must_not": ["شاي", "لحم", "خبز"],
     "min_results": 1, "max_results": 10},

    {"query": "screwdriver", "category": "cross_lang",
     "must_contain": ["مفكات", "Screwdriver"],
     "must_not": ["شاي", "لحم", "بطيخ"],
     "min_results": 1, "max_results": 8},

    # ══ ARABIZI ══════════════════════════════════════════════════
    {"query": "chai", "category": "arabizi",
     "must_contain": ["شاي", "Tea", "Chai"],
     "must_not": ["لحم", "حديد"],
     "min_results": 1, "max_results": 20},

    {"query": "7aleeb", "category": "arabizi",
     "must_contain": ["حليب", "Milk"],
     "must_not": ["لحم", "حديد"],
     "min_results": 0, "max_results": 15},

    # ══ NEGATIVE ═════════════════════════════════════════════════
    {"query": "سيارة فيراري", "category": "negative",
     "must_contain": [],
     "must_not": ["شاي", "خبز", "شامبو", "دفتر"],
     "min_results": 0, "max_results": 3},

    {"query": "طائرة هليكوبتر", "category": "negative",
     "must_contain": [],
     "must_not": ["شاي", "لحم", "حديد", "شامبو"],
     "min_results": 0, "max_results": 3},

    {"query": "تذكرة سفر", "category": "negative",
     "must_contain": [],
     "must_not": ["شاي", "لحم", "مكنسة"],
     "min_results": 0, "max_results": 3},
]


# ══════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════

def _matches_any(text: str, patterns: List[str]) -> bool:
    t = text.lower()
    return any(p.lower() in t for p in patterns)


def reciprocal_rank(results: List[str], must_contain: List[str]) -> float:
    if not must_contain:
        return 1.0 if not results else 0.0
    for i, name in enumerate(results):
        if _matches_any(name, must_contain):
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(results: List[str], must_contain: List[str], k: int = 5) -> float:
    if not must_contain:
        return 1.0 if not results else 0.0
    gains = [1.0 if _matches_any(n, must_contain) else 0.0 for n in results[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    n_rel = min(int(sum(gains)), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    return dcg / idcg if idcg > 0 else 0.0


def precision_at_k(results: List[str], must_contain: List[str], k: int = 3) -> float:
    if not must_contain:
        return 1.0 if not results else 0.0
    top = results[:k]
    if not top:
        return 0.0
    return sum(1 for n in top if _matches_any(n, must_contain)) / len(top)


def recall_coverage(results: List[str], must_contain: List[str]) -> float:
    if not must_contain:
        return 1.0
    found = sum(1 for p in must_contain
                if any(p.lower() in n.lower() for n in results))
    return found / len(must_contain)


def noise_rate(results: List[str], must_not: List[str]) -> float:
    if not results or not must_not:
        return 0.0
    return sum(1 for n in results if _matches_any(n, must_not)) / len(results)


def overall_score(s: Dict) -> float:
    return 10.0 * (
        0.40 * s["ndcg@5"]
        + 0.25 * s["mrr"]
        + 0.20 * (1.0 - s["noise"])
        + 0.15 * s["recall"]
    )


# ══════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════

def run_benchmark(base_url: str, only_category: str = None,
                  verbose: bool = True) -> Dict:
    cases = GOLDEN_CASES
    if only_category:
        cases = [c for c in cases if c["category"] == only_category]
        if not cases:
            cats = sorted({c["category"] for c in GOLDEN_CASES})
            print(f"Unknown category '{only_category}'. Available: {', '.join(cats)}")
            return {}

    client = httpx.Client(base_url=base_url, timeout=90)
    out = []

    if verbose:
        print(f"\nBenchmark → {base_url}   ({len(cases)} cases)")
        print("=" * 84)

    current_cat = None
    for case in cases:
        if verbose and case["category"] != current_cat:
            current_cat = case["category"]
            print(f"\n  [{current_cat}]")

        q = case["query"]
        try:
            resp = client.post("/api/v1/search/hybrid", json={
                "query_text": q,
                "latitude": DEFAULT_LAT,
                "longitude": DEFAULT_LON,
            })
            names = [r.get("name", "") for r in resp.json().get("results", [])]
        except Exception as e:
            if verbose:
                print(f"    ERROR {q}: {e}")
            names = []

        mrr = reciprocal_rank(names, case["must_contain"])
        ndcg = ndcg_at_k(names, case["must_contain"], 5)
        p3 = precision_at_k(names, case["must_contain"], 3)
        rec = recall_coverage(names, case["must_contain"])
        noise = noise_rate(names, case["must_not"])
        count_ok = case["min_results"] <= len(names) <= case["max_results"]

        out.append({
            "query": q, "category": case["category"],
            "result_count": len(names), "count_ok": count_ok,
            "mrr": mrr, "ndcg@5": ndcg, "p@3": p3,
            "recall": rec, "noise": noise,
            "top_results": names[:5],
        })

        if verbose:
            ok = mrr > 0 and noise == 0 and count_ok
            mark = "✓" if ok else "✗"
            print(f"    {mark} {q[:30]:32s} n={len(names):2d} "
                  f"MRR={mrr:.2f} NDCG={ndcg:.2f} P@3={p3:.2f} "
                  f"Rec={rec:.2f} Noise={noise:.2f}")

    client.close()

    n = len(out)
    summary = {
        "timestamp": datetime.now().isoformat(),
        "base_url": base_url,
        "n_cases": n,
        "mrr": sum(c["mrr"] for c in out) / n,
        "ndcg@5": sum(c["ndcg@5"] for c in out) / n,
        "p@3": sum(c["p@3"] for c in out) / n,
        "recall": sum(c["recall"] for c in out) / n,
        "noise": sum(c["noise"] for c in out) / n,
        "count_ok_rate": sum(1 for c in out if c["count_ok"]) / n,
    }

    by_cat = {}
    for c in out:
        by_cat.setdefault(c["category"], []).append(c)
    summary["by_category"] = {
        cat: {
            "n": len(v),
            "mrr": sum(x["mrr"] for x in v) / len(v),
            "ndcg@5": sum(x["ndcg@5"] for x in v) / len(v),
            "recall": sum(x["recall"] for x in v) / len(v),
            "noise": sum(x["noise"] for x in v) / len(v),
        }
        for cat, v in by_cat.items()
    }

    if verbose:
        print("\n" + "=" * 84)
        print(f"\n  SCORE: {overall_score(summary):.1f}/10\n")
        print(f"  MRR      {summary['mrr']:.3f}    first relevant result position")
        print(f"  NDCG@5   {summary['ndcg@5']:.3f}    ranking quality")
        print(f"  P@3      {summary['p@3']:.3f}    top-3 precision")
        print(f"  Recall   {summary['recall']:.3f}    expected items found")
        print(f"  Noise    {summary['noise']:.3f}    irrelevant results (lower better)")
        print(f"  CountOK  {summary['count_ok_rate']:.3f}    result count within range")
        print("\n  By category:")
        for cat, m in sorted(summary["by_category"].items(),
                             key=lambda kv: -kv[1]["ndcg@5"]):
            print(f"    {cat:14s} n={m['n']:2d}  MRR={m['mrr']:.2f}  "
                  f"NDCG={m['ndcg@5']:.2f}  Rec={m['recall']:.2f}  "
                  f"Noise={m['noise']:.2f}")
        print()

    return {"summary": summary, "cases": out}


def compare(current: Dict, baseline_path: Path):
    with open(baseline_path, encoding="utf-8") as f:
        base = json.load(f)
    bs, cs = base["summary"], current["summary"]

    print("\n" + "=" * 84)
    print(f"  COMPARE vs {baseline_path.name}   (recorded {bs['timestamp'][:19]})")
    print("=" * 84)

    def row(label, key, higher_better=True):
        b, c = bs[key], cs[key]
        d = c - b
        arrow = "→"
        if abs(d) > 0.001:
            arrow = "▲" if (d > 0) == higher_better else "▼"
        print(f"  {label:12s} {b:.3f}  {arrow}  {c:.3f}   ({d:+.3f})")

    row("MRR", "mrr")
    row("NDCG@5", "ndcg@5")
    row("P@3", "p@3")
    row("Recall", "recall")
    row("Noise", "noise", False)
    print()
    b_sc, c_sc = overall_score(bs), overall_score(cs)
    d = c_sc - b_sc
    arrow = "▲" if d > 0.05 else ("▼" if d < -0.05 else "→")
    print(f"  SCORE        {b_sc:.1f}/10  {arrow}  {c_sc:.1f}/10   ({d:+.1f})")

    print("\n  Category movement:")
    moved = False
    for cat in sorted(cs.get("by_category", {})):
        b = bs.get("by_category", {}).get(cat)
        c = cs["by_category"][cat]
        if not b:
            continue
        d = c["ndcg@5"] - b["ndcg@5"]
        if abs(d) > 0.02:
            moved = True
            arrow = "▲" if d > 0 else "▼"
            print(f"    {arrow} {cat:14s} {b['ndcg@5']:.2f} → {c['ndcg@5']:.2f}  ({d:+.2f})")
    if not moved:
        print("    (no category moved beyond threshold)")

    base_by_q = {c["query"]: c for c in base["cases"]}
    ups, downs = [], []
    for c in current["cases"]:
        b = base_by_q.get(c["query"])
        if not b:
            continue
        d = c["ndcg@5"] - b["ndcg@5"]
        if d < -0.05:
            downs.append((c["query"], b["ndcg@5"], c["ndcg@5"]))
        elif d > 0.05:
            ups.append((c["query"], b["ndcg@5"], c["ndcg@5"]))

    if ups:
        print("\n  Improved:")
        for q, b, c in ups:
            print(f"    ▲ {q[:34]:36s} {b:.2f} → {c:.2f}")
    if downs:
        print("\n  REGRESSED:")
        for q, b, c in downs:
            print(f"    ▼ {q[:34]:36s} {b:.2f} → {c:.2f}")
    if not ups and not downs:
        print("\n  No per-query changes beyond threshold.")
    print()


def main():
    ap = argparse.ArgumentParser(description="Lamba search quality benchmark")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--save", metavar="NAME")
    ap.add_argument("--compare", metavar="NAME")
    ap.add_argument("--category", metavar="CAT",
                    help="Run only one category (specific, brand, intent, ...)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = run_benchmark(args.url, args.category, verbose=not args.json)
    if not results:
        return

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    out_dir = Path(__file__).parent / "benchmarks"
    out_dir.mkdir(exist_ok=True)

    if args.compare:
        p = out_dir / f"{args.compare}.json"
        if p.exists():
            compare(results, p)
        else:
            print(f"  No baseline '{args.compare}' in {out_dir}")

    if args.save:
        p = out_dir / f"{args.save}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"  Saved → {p}")


if __name__ == "__main__":
    main()
