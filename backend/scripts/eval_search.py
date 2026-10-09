import argparse
import json
import math
import time
import sys
import os
from collections import defaultdict
import random

try:
    import requests
except ImportError:
    requests = None

def get_item_text(item):
    name = item.get("name", "")
    desc = item.get("description", "")
    terms = item.get("search_terms", [])
    if isinstance(terms, list):
        terms = " ".join(terms)
    return f"{name} {desc} {terms}".lower()

def check_keyword_match(item, relevant_keywords):
    if not relevant_keywords:
        return False
    
    text = get_item_text(item)
    for group in relevant_keywords:
        # Check if ALL keywords in THIS group appear in text
        if all(kw.lower() in text for kw in group):
            return True
    return False

def calculate_dcg(scores, k):
    return sum((2**score - 1) / math.log2(i + 2) for i, score in enumerate(scores[:k]))

def calculate_ndcg(actual_scores, ideal_scores, k=10):
    dcg = calculate_dcg(actual_scores, k)
    idcg = calculate_dcg(ideal_scores, k)
    return dcg / idcg if idcg > 0 else 0.0

def mock_search_api(query):
    # Simulates a search API response for offline testing
    return {
        "results": [
            {
                "id": f"mock_{i}", 
                "name": f"Mock result {i} for {query}", 
                "description": "Mock description", 
                "rerank_score": max(0, 0.9 - i*0.05)
            }
            for i in range(10)
        ],
        "meta": {
            "reranker_fallback": random.choice([True, False]),
            "reranker_available": True,
            "latency_ms": random.uniform(20.0, 150.0)
        }
    }

def calculate_percentile(data, p):
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1

def print_metrics_table(metrics_dict, title):
    count = metrics_dict["count"]
    if count == 0:
        print(f"\n=== {title} (0 queries) ===")
        return

    avg_mrr = sum(metrics_dict["mrr"]) / count
    avg_recall = sum(metrics_dict["recall"]) / count
    avg_ndcg = sum(metrics_dict["ndcg"]) / count
    fallback_rate = (sum(metrics_dict["fallback"]) / count) * 100.0
    
    p50 = calculate_percentile(metrics_dict["latency"], 50)
    p90 = calculate_percentile(metrics_dict["latency"], 90)
    p95 = calculate_percentile(metrics_dict["latency"], 95)

    print(f"\n{'=' * 65}")
    print(f"  {title} (Total Queries: {count})")
    print(f"{'=' * 65}")
    print(f"  MRR@10:        {avg_mrr:.4f}")
    print(f"  Recall@10:     {avg_recall:.4f}")
    print(f"  NDCG@10:       {avg_ndcg:.4f}")
    print(f"  Fallback Rate: {fallback_rate:.1f}%")
    print(f"  Latency (p50): {p50:.1f} ms")
    print(f"  Latency (p90): {p90:.1f} ms")
    print(f"  Latency (p95): {p95:.1f} ms")
    print(f"{'=' * 65}")

def create_metrics_dict():
    return {
        "count": 0,
        "mrr": [],
        "recall": [],
        "ndcg": [],
        "latency": [],
        "fallback": []
    }

def main():
    parser = argparse.ArgumentParser(description="Evaluate search endpoints")
    parser.add_argument("--dataset", default="data/golden_search.jsonl")
    parser.add_argument("--output", default="data/baseline_eval_results.json")
    parser.add_argument("--worksheet", default="data/labeling_worksheet.jsonl")
    parser.add_argument("--endpoint", default="/api/v1/search/hybrid")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default="")
    parser.add_argument("--lat", type=float, default=32.0385, help="latitude of the simulated user")
    parser.add_argument("--lng", type=float, default=35.7275, help="longitude of the simulated user")
    parser.add_argument("--max-distance-km", type=float, default=None,
                        help="search radius sent as filters.max_distance_km (the API default is used if omitted)")
    parser.add_argument("--mock", action="store_true", help="Run with mock data (no server needed)")
    
    args = parser.parse_args()

    if not args.mock and requests is None:
        print("Error: The 'requests' library is required but not installed.")
        print("Install it with 'pip install requests' or run with '--mock' flag.")
        sys.exit(1)

    # Read dataset
    dataset_path = args.dataset
    if not os.path.exists(dataset_path) and os.path.exists(os.path.join("backend", dataset_path)):
        dataset_path = os.path.join("backend", dataset_path)
    elif not os.path.exists(dataset_path) and os.path.exists(os.path.join("backend", "data", "golden_search.jsonl")):
        dataset_path = os.path.join("backend", "data", "golden_search.jsonl")

    dataset = []
    if os.path.exists(dataset_path):
        with open(dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    dataset.append(json.loads(line))
    else:
        print(f"Warning: Dataset not found at {dataset_path}.")
        print("Using dummy dataset for demonstration.")
        dataset = [
            {"query": "green tea", "query_type": "exact_en", "relevant_ids": [], "relevant_keywords": [["green", "tea"]], "graded_relevance": {}},
            {"query": "شاي أخضر", "query_type": "exact_ar", "relevant_ids": [], "relevant_keywords": [["شاي", "أخضر"]], "graded_relevance": {}}
        ]

    overall_metrics = create_metrics_dict()
    per_type_metrics = defaultdict(create_metrics_dict)
    worksheet_entries = []

    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    for entry in dataset:
        query = entry.get("query", "")
        qtype = entry.get("query_type", "unknown")
        rel_ids = entry.get("relevant_ids", [])
        graded_rel = entry.get("graded_relevance", {})
        rel_keywords = entry.get("relevant_keywords", [])

        start_time = time.time()

        if args.mock:
            response_data = mock_search_api(query)
            latency = response_data.get("meta", {}).get("latency_ms", 15.0)
        else:
            url = f"{args.base_url.rstrip('/')}{args.endpoint}"
            payload = {"query_text": query, "latitude": args.lat, "longitude": args.lng}
            if args.max_distance_km is not None:
                payload["filters"] = {"max_distance_km": args.max_distance_km}
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 405: # Fallback to GET if POST not allowed
                    resp = requests.get(url, params={"query_text": query, "q": query}, headers=headers, timeout=30)
                resp.raise_for_status()
                response_data = resp.json()
                latency = (time.time() - start_time) * 1000.0
            except requests.exceptions.RequestException as e:
                print(f"Error querying backend for '{query}': {e}")
                print(f"Make sure backend is running at {args.base_url}, or pass --mock to test offline.")
                sys.exit(1)

        results = response_data.get("results", [])[:10]
        if not results and "items" in response_data:
            results = response_data.get("items", [])[:10]
        meta = response_data.get("meta", {})

        actual_scores = []
        first_rel_rank = -1
        rel_count = 0
        worksheet_items = []

        for rank, item in enumerate(results):
            item_id = str(item.get("id") or item.get("item_id") or "")  # the search API names it item_id
            score = 0
            is_matched_kw = False

            if item_id in graded_rel:
                score = graded_rel[item_id]
            elif item_id in rel_ids:
                score = 1
            elif not rel_ids and check_keyword_match(item, rel_keywords):
                score = 1
                is_matched_kw = True

            actual_scores.append(score)
            if score > 0:
                rel_count += 1
                if first_rel_rank == -1:
                    first_rel_rank = rank + 1

            worksheet_items.append({
                "rank": rank + 1,
                "id": item_id,
                "name": item.get("name", ""),
                "rerank_score": item.get("rerank_score", item.get("score", 0.0)),
                "matched_keyword": is_matched_kw,
            })

        worksheet_entries.append({
            "query": query,
            "query_type": qtype,
            "returned_items": worksheet_items,
        })

        if graded_rel:
            ideal_scores = sorted(graded_rel.values(), reverse=True)[:10]
        else:
            ideal_scores = [1] * max(len(rel_ids), rel_count)
            if not ideal_scores and rel_keywords:
                ideal_scores = [1]
            ideal_scores = ideal_scores[:10]

        mrr = 1.0 / first_rel_rank if first_rel_rank > 0 else 0.0
        recall = 0.0
        if graded_rel or rel_ids:
            total_rel = len(graded_rel) if graded_rel else len(rel_ids)
            recall = min(1.0, rel_count / total_rel) if total_rel > 0 else 0.0
        elif rel_keywords:
            recall = 1.0 if rel_count > 0 else 0.0

        ndcg = calculate_ndcg(actual_scores, ideal_scores, k=10)
        fallback = meta.get("reranker_fallback", False) or not meta.get("reranker_available", True)

        for mets in (overall_metrics, per_type_metrics[qtype]):
            mets["count"] += 1
            mets["mrr"].append(mrr)
            mets["recall"].append(recall)
            mets["ndcg"].append(ndcg)
            mets["latency"].append(latency)
            mets["fallback"].append(1 if fallback else 0)

    # Save outputs
    out_file = args.output
    if os.path.dirname(out_file):
        os.makedirs(os.path.dirname(out_file), exist_ok=True)

    ws_file = args.worksheet
    if os.path.dirname(ws_file):
        os.makedirs(os.path.dirname(ws_file), exist_ok=True)

    results_out = {
        "overall": {
            "count": overall_metrics["count"],
            "mrr_at_10": sum(overall_metrics["mrr"]) / overall_metrics["count"] if overall_metrics["count"] else 0,
            "recall_at_10": sum(overall_metrics["recall"]) / overall_metrics["count"] if overall_metrics["count"] else 0,
            "ndcg_at_10": sum(overall_metrics["ndcg"]) / overall_metrics["count"] if overall_metrics["count"] else 0,
            "fallback_rate": sum(overall_metrics["fallback"]) / overall_metrics["count"] if overall_metrics["count"] else 0,
            "latency_p50_ms": calculate_percentile(overall_metrics["latency"], 50),
            "latency_p90_ms": calculate_percentile(overall_metrics["latency"], 90),
            "latency_p95_ms": calculate_percentile(overall_metrics["latency"], 95),
        },
        "per_type": {},
    }
    for qt, metrics in per_type_metrics.items():
        results_out["per_type"][qt] = {
            "count": metrics["count"],
            "mrr_at_10": sum(metrics["mrr"]) / metrics["count"] if metrics["count"] else 0,
            "recall_at_10": sum(metrics["recall"]) / metrics["count"] if metrics["count"] else 0,
            "ndcg_at_10": sum(metrics["ndcg"]) / metrics["count"] if metrics["count"] else 0,
            "fallback_rate": sum(metrics["fallback"]) / metrics["count"] if metrics["count"] else 0,
            "latency_p50_ms": calculate_percentile(metrics["latency"], 50),
            "latency_p90_ms": calculate_percentile(metrics["latency"], 90),
            "latency_p95_ms": calculate_percentile(metrics["latency"], 95),
        }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results_out, f, indent=2, ensure_ascii=False)

    with open(ws_file, "w", encoding="utf-8") as f:
        for entry in worksheet_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Print Summary
    print_metrics_table(overall_metrics, "Overall Metrics")
    for qt, metrics in per_type_metrics.items():
        print_metrics_table(metrics, f"Metrics for Category: {qt}")

    print(f"\n✓ Metrics saved to {out_file}")
    print(f"✓ Labeling worksheet saved to {ws_file}")

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
