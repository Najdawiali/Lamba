import time
import requests
import json
import os
import sys

# Define 100 test queries with expected target matches
# Each query has a list of alternative clauses. A result is a match if it satisfies ALL keywords in ANY of the clauses.
TEST_CASES = [
    # ── 1. Exact Matches (Arabic) ─────────────────────────────────
    {
        "query": "شاي أخضر صيني",
        "category": "exact_ar",
        "expected": [["شاي", "أخضر", "صيني"]]
    },
    {
        "query": "قهوة تركية فاخرة",
        "category": "exact_ar",
        "expected": [["قهوة", "تركية"]]
    },
    {
        "query": "هيل أخضر",
        "category": "exact_ar",
        "expected": [["هيل", "أخضر"]]
    },
    {
        "query": "فستق حلبي محمص",
        "category": "exact_ar",
        "expected": [["فستق", "حلبي", "محمص"]]
    },
    {
        "query": "زيت حبة البركة",
        "category": "exact_ar",
        "expected": [["زيت", "البركة"]]
    },
    {
        "query": "قرفة سيلانية",
        "category": "exact_ar",
        "expected": [["قرفة", "سيلانية"]]
    },
    {
        "query": "سماق مطحون",
        "category": "exact_ar",
        "expected": [["سماق", "مطحون"]]
    },
    {
        "query": "طحينة فاخرة",
        "category": "exact_ar",
        "expected": [["طحينة"]]
    },
    {
        "query": "شاي بابونج عضوي",
        "category": "exact_ar",
        "expected": [["بابونج"]]
    },
    {
        "query": "بذور كتان عضوية",
        "category": "exact_ar",
        "expected": [["كتان"]]
    },
    {
        "query": "زيت جوز هند بكر",
        "category": "exact_ar",
        "expected": [["زيت", "جوز", "هند", "بكر"]]
    },
    {
        "query": "كركم عضوي مطحون",
        "category": "exact_ar",
        "expected": [["كركم"]]
    },
    {
        "query": "عسل أزهار برية",
        "category": "exact_ar",
        "expected": [["عسل", "أزهار"]]
    },
    {
        "query": "شاي أحمر تركي",
        "category": "exact_ar",
        "expected": [["شاي", "أحمر", "تركي"]]
    },
    {
        "query": "قهوة عربية بالهيل",
        "category": "exact_ar",
        "expected": [["قهوة", "عربية"]]
    },
    {
        "query": "تمر عجوة المدينة",
        "category": "exact_ar",
        "expected": [["عجوة"]]
    },
    {
        "query": "زيت زيتون بلدي",
        "category": "exact_ar",
        "expected": [["زيت", "زيتون", "بلدي"]]
    },
    {
        "query": "حلاوة طحينية",
        "category": "exact_ar",
        "expected": [["حلاوة"]]
    },
    {
        "query": "ماء ورد",
        "category": "exact_ar",
        "expected": [["ماء", "ورد"]]
    },
    {
        "query": "ماء زهر",
        "category": "exact_ar",
        "expected": [["ماء", "زهر"]]
    },

    # ── 2. Exact Matches (English) ────────────────────────────────
    {
        "query": "Matcha Organic",
        "category": "exact_en",
        "expected": [["matcha"]]
    },
    {
        "query": "Arabic Coffee - Dark Roast",
        "category": "exact_en",
        "expected": [["arabic", "coffee"]]
    },
    {
        "query": "Honey - Sidr Premium",
        "category": "exact_en",
        "expected": [["sidr", "honey"]]
    },
    {
        "query": "Dates - Medjool Premium",
        "category": "exact_en",
        "expected": [["medjool", "dates"]]
    },
    {
        "query": "Olive Oil - Extra Virgin",
        "category": "exact_en",
        "expected": [["olive", "oil"]]
    },
    {
        "query": "Saffron - Iranian Grade 1",
        "category": "exact_en",
        "expected": [["saffron"]]
    },
    {
        "query": "Turkish Coffee - Medium",
        "category": "exact_en",
        "expected": [["turkish", "coffee"]]
    },
    {
        "query": "Earl Grey Tea",
        "category": "exact_en",
        "expected": [["earl", "grey"]]
    },
    {
        "query": "Cardamom Pods - Green",
        "category": "exact_en",
        "expected": [["cardamom"]]
    },
    {
        "query": "Pistachios - Roasted Salted",
        "category": "exact_en",
        "expected": [["pistachios"]]
    },
    {
        "query": "Cashews - Raw Organic",
        "category": "exact_en",
        "expected": [["cashews"]]
    },
    {
        "query": "Black Seed Oil",
        "category": "exact_en",
        "expected": [["black", "seed"]]
    },
    {
        "query": "Cinnamon Sticks - Ceylon",
        "category": "exact_en",
        "expected": [["cinnamon"]]
    },
    {
        "query": "Sumac - Ground",
        "category": "exact_en",
        "expected": [["sumac"]]
    },
    {
        "query": "Tahini - Sesame Paste",
        "category": "exact_en",
        "expected": [["tahini"]]
    },

    # ── 3. Typo / Misspellings (Arabic & English) ──────────────────
    {
        "query": "عسير برتغال",
        "category": "misspelling_ar",
        "expected": [["عصير", "برتقال"]]
    },
    {
        "query": "شاهي اخضر",
        "category": "misspelling_ar",
        "expected": [["شاي", "أخضر"]]
    },
    {
        "query": "قهوه تركي",
        "category": "misspelling_ar",
        "expected": [["قهوة", "تركية"], ["turkish", "coffee"]]
    },
    {
        "query": "هيل اخضر فاخر",
        "category": "misspelling_ar",
        "expected": [["هيل", "أخضر"]]
    },
    {
        "query": "فستك حلبي",
        "category": "misspelling_ar",
        "expected": [["فستق", "حلبي"]]
    },
    {
        "query": "زيت حبت البركه",
        "category": "misspelling_ar",
        "expected": [["زيت", "البركة"]]
    },
    {
        "query": "عرفه سيلانيه",
        "category": "misspelling_ar",
        "expected": [["قرفة", "سيلانية"]]
    },
    {
        "query": "سماك مطحون",
        "category": "misspelling_ar",
        "expected": [["سماق", "مطحون"]]
    },
    {
        "query": "طحينه فاخره",
        "category": "misspelling_ar",
        "expected": [["طحينة"]]
    },
    {
        "query": "شاي بابونج عضو",
        "category": "misspelling_ar",
        "expected": [["بابونج"]]
    },
    {
        "query": "زيت جوز هنيد بكر",
        "category": "misspelling_ar",
        "expected": [["جوز", "هند"]]
    },
    {
        "query": "عسل ازهار بريه",
        "category": "misspelling_ar",
        "expected": [["عسل", "أزهار"]]
    },
    {
        "query": "شاي احمر تركيي",
        "category": "misspelling_ar",
        "expected": [["شاي", "أحمر", "تركي"]]
    },
    {
        "query": "تمر عجوه المدينه",
        "category": "misspelling_ar",
        "expected": [["عجوة"]]
    },
    {
        "query": "زيت زتون بلدي",
        "category": "misspelling_ar",
        "expected": [["زيت", "زيتون", "بلدي"]]
    },
    {
        "query": "pepsii can",
        "category": "misspelling_en",
        "expected": [["pepsi"]]
    },
    {
        "query": "aryel powder",
        "category": "misspelling_en",
        "expected": [["ariel"]]
    },
    {
        "query": "downi softener",
        "category": "misspelling_en",
        "expected": [["downy"]]
    },
    {
        "query": "sonflower oil",
        "category": "misspelling_en",
        "expected": [["sunflower", "oil"]]
    },
    {
        "query": "powdred milk",
        "category": "misspelling_en",
        "expected": [["powdered", "milk"], ["milk", "powder"]]
    },

    # ── 4. Arabizi Queries ────────────────────────────────────────
    {
        "query": "7aleeb",
        "category": "arabizi",
        "expected": [["حليب"], ["milk"]]
    },
    {
        "query": "3aseer",
        "category": "arabizi",
        "expected": [["عصير"], ["juice"]]
    },
    {
        "query": "khobz",
        "category": "arabizi",
        "expected": [["خبز"], ["bread"]]
    },
    {
        "query": "shai",
        "category": "arabizi",
        "expected": [["شاي"], ["tea"]]
    },
    {
        "query": "qahwah",
        "category": "arabizi",
        "expected": [["قهوة"], ["coffee"]]
    },
    {
        "query": "3asal",
        "category": "arabizi",
        "expected": [["عسل"], ["honey"]]
    },
    {
        "query": "zayt",
        "category": "arabizi",
        "expected": [["زيت"], ["oil"]]
    },
    {
        "query": "mil7",
        "category": "arabizi",
        "expected": [["ملح"], ["salt"]]
    },
    {
        "query": "sukkar",
        "category": "arabizi",
        "expected": [["سكر"], ["sugar"]]
    },
    {
        "query": "tamr",
        "category": "arabizi",
        "expected": [["تمر"], ["dates"]]
    },

    # ── 5. Semantic Queries (Arabic & English) ────────────────────
    {
        "query": "شيء حلو للشاي",
        "category": "semantic_ar",
        "expected": [["سكر"], ["عسل"], ["sugar"], ["honey"]]
    },
    {
        "query": "منظفات ملابس",
        "category": "semantic_ar",
        "expected": [["غسيل"], ["اريال"], ["تايد"], ["laundry"], ["washing"]]
    },
    {
        "query": "توابل للطبخ",
        "category": "semantic_ar",
        "expected": [["بهارات"], ["بهار"], ["كزبرة"], ["كمون"], ["spices"], ["spice"]]
    },
    {
        "query": "مشروب غازي",
        "category": "semantic_ar",
        "expected": [["بيبسي"], ["pepsi"], ["cola"], ["كولا"]]
    },
    {
        "query": "حليب مركز للحلويات",
        "category": "semantic_ar",
        "expected": [["مكثف"], ["condensed"]]
    },
    {
        "query": "شيء مهدئ للاسترخاء",
        "category": "semantic_ar",
        "expected": [["بابونج"], ["لافندر"], ["أعشاب"], ["chamomile"], ["lavender"]]
    },
    {
        "query": "مكسرات غنية بالسيلينيوم",
        "category": "semantic_ar",
        "expected": [["برازيلية"], ["brazil"]]
    },
    {
        "query": "زيت للشعر والبشرة",
        "category": "semantic_ar",
        "expected": [["جوز هند"], ["لافندر"], ["coconut"], ["lavender"]]
    },
    {
        "query": "مشروب منعش للصيف",
        "category": "semantic_ar",
        "expected": [["عصير"], ["orange juice"], ["apple juice"]]
    },
    {
        "query": "something sweet for tea",
        "category": "semantic_en",
        "expected": [["sugar"], ["honey"], ["سكر"], ["عسل"]]
    },
    {
        "query": "laundry detergent",
        "category": "semantic_en",
        "expected": [["ariel"], ["tide"], ["غسيل"], ["اريال"], ["تايد"]]
    },
    {
        "query": "hot indian spices",
        "category": "semantic_en",
        "expected": [["curry"], ["madras"], ["masala"], ["كاري"], ["هندية"]]
    },
    {
        "query": "carbonated soft drink",
        "category": "semantic_en",
        "expected": [["pepsi"], ["cola"], ["بيبسي"], ["كولا"]]
    },
    {
        "query": "soothing herbal tea",
        "category": "semantic_en",
        "expected": [["chamomile"], ["lavender"], ["بابونج"], ["لافندر"], ["أعشاب"]]
    },
    {
        "query": "hair and skin oil",
        "category": "semantic_en",
        "expected": [["coconut"], ["lavender"], ["tea tree"], ["جوز هند"], ["لافندر"]]
    },

    # ── 6. Cross-Language Queries ─────────────────────────────────
    {
        "query": "green tea",
        "category": "cross_lang",
        "expected": [["شاي", "أخضر"], ["green", "tea"]]
    },
    {
        "query": "turkish coffee",
        "category": "cross_lang",
        "expected": [["قهوة", "تركية"], ["turkish", "coffee"]]
    },
    {
        "query": "green cardamom",
        "category": "cross_lang",
        "expected": [["هيل", "أخضر"], ["cardamom"]]
    },
    {
        "query": "roasted pistachio",
        "category": "cross_lang",
        "expected": [["فستق", "حلبي"], ["pistachio"]]
    },
    {
        "query": "black seed oil",
        "category": "cross_lang",
        "expected": [["زيت", "البركة"], ["black", "seed"]]
    },
    {
        "query": "ceylon cinnamon",
        "category": "cross_lang",
        "expected": [["قرفة", "سيلانية"], ["cinnamon"]]
    },
    {
        "query": "ground sumac",
        "category": "cross_lang",
        "expected": [["سماق"], ["sumac"]]
    },
    {
        "query": "organic flax seeds",
        "category": "cross_lang",
        "expected": [["كتان"], ["flax"]]
    },
    {
        "query": "wildflower honey",
        "category": "cross_lang",
        "expected": [["عسل", "أزهار"], ["honey"]]
    },
    {
        "query": "turkish red tea",
        "category": "cross_lang",
        "expected": [["شاي", "أحمر", "تركي"], ["tea"]]
    },
    {
        "query": "yemeni sidr honey",
        "category": "cross_lang",
        "expected": [["سدر"], ["sidr"]]
    },
    {
        "query": "rose water",
        "category": "cross_lang",
        "expected": [["ماء", "ورد"], ["rose"]]
    },
    {
        "query": "orange blossom water",
        "category": "cross_lang",
        "expected": [["ماء", "زهر"], ["blossom"]]
    },
    {
        "query": "tahini sesame",
        "category": "cross_lang",
        "expected": [["طحينة"], ["tahini"]]
    },
    {
        "query": "acacia honey",
        "category": "cross_lang",
        "expected": [["أكاسيا"], ["acacia"]]
    },
    # ── 7. Numeric Attribute Ranges ────────────────────────────────
    {
        "query": "كرسي بين 50 و 70 سم",
        "category": "numeric_attr",
        "expected": [["60cm"]]
    },
    {
        "query": "شاي 200 جرام",
        "category": "numeric_attr",
        "expected": [["200g"]]
    },
    {
        "query": "عصير اكثر من 1 لتر",
        "category": "numeric_attr",
        "expected": [["2000ml"], ["2l"]]
    },
    {
        "query": "عصير اقل من 500 مل",
        "category": "numeric_attr",
        "expected": [["250ml"]]
    },
    {
        "query": "كرسي مكتب فوق 50 سم",
        "category": "numeric_attr",
        "expected": [["60cm"], ["80cm"], ["120cm"]]
    },
    {
        "query": "كرسي تحت 50 سم",
        "category": "numeric_attr",
        "expected": [["45cm"]]
    }
]

extra_cases = [
    {"query": "organic quinoa", "category": "exact_en", "expected": [["quinoa"]]},
    {"query": "pumpkin seeds", "category": "exact_en", "expected": [["pumpkin"]]},
    {"query": "avocado oil", "category": "exact_en", "expected": [["avocado"]]},
    {"query": "almond butter", "category": "exact_en", "expected": [["almond", "butter"]]},
    {"query": "vanilla beans", "category": "exact_en", "expected": [["vanilla"]]},
    
    {"query": "كزبرة مطحونة", "category": "exact_ar", "expected": [["كزبرة"]]},
    {"query": "بذور عباد الشمس", "category": "exact_ar", "expected": [["عباد", "الشمس"]]},
    {"query": "حلاوة طحينية بالفستق", "category": "exact_ar", "expected": [["حلاوة"]]},
    {"query": "مكسرات مشكلة", "category": "exact_ar", "expected": [["مكسرات"]]},
    {"query": "لوز أخضر طازج", "category": "exact_ar", "expected": [["لوز", "أخضر"]]},
    
    {"query": "كاجو ممص", "category": "misspelling_ar", "expected": [["كاجو"]]},
    {"query": "مشمش مجففف", "category": "misspelling_ar", "expected": [["مشمش"]]},
    {"query": "دبس رمان طبيعيي", "category": "misspelling_ar", "expected": [["دبس", "رمان"]]},
    {"query": "كمون مطحونن", "category": "misspelling_ar", "expected": [["كمون"]]},
    {"query": "يانسون نجميي", "category": "misspelling_ar", "expected": [["يانسون"]]},

    {"query": "almond buter", "category": "misspelling_en", "expected": [["almond", "butter"]]},
    {"query": "pumpkin sedes", "category": "misspelling_en", "expected": [["pumpkin"]]},
    {"query": "avocato oil", "category": "misspelling_en", "expected": [["avocado"]]},
    {"query": "quinua organic", "category": "misspelling_en", "expected": [["quinoa"]]},
    {"query": "vanila beans", "category": "misspelling_en", "expected": [["vanilla"]]},
]

for ec in extra_cases:
    if len(TEST_CASES) < 100:
        TEST_CASES.append(ec)

print(f"Total test cases in benchmark dataset: {len(TEST_CASES)}")

# API URL
API_URL = "http://localhost:8000/api/v1/os-search/hybrid"
LAT = 32.0388
LON = 35.7255

def evaluate_hit(hit, expected_clauses):
    name_ar = hit.get("name_ar", "").lower()
    name_en = hit.get("name_en", "").lower()
    combined_name = f"{name_ar} | {name_en}"
    
    for clause in expected_clauses:
        clause_match = True
        for keyword in clause:
            if keyword.lower() not in combined_name:
                clause_match = False
                break
        if clause_match:
            return True
    return False

def run_benchmark():
    category_stats = {}
    total_latency = 0.0
    latencies = []
    
    overall_p1 = 0
    overall_p3 = 0
    overall_p5 = 0
    overall_mrr = 0.0
    
    results_detailed = []

    for idx, case in enumerate(TEST_CASES, 1):
        q = case["query"]
        cat = case["category"]
        expected = case["expected"]
        
        if cat not in category_stats:
            category_stats[cat] = {
                "count": 0, "p1": 0, "p3": 0, "p5": 0, "mrr": 0.0, "latency": []
            }
            
        payload = {
            "q": q,
            "lat": LAT,
            "lon": LON,
            "radius_km": 10.0
        }
        
        t0 = time.perf_counter()
        try:
            resp = requests.post(API_URL, json=payload, timeout=20)
            t1 = time.perf_counter()
            latency_ms = (t1 - t0) * 1000.0
            
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("results", [])
            else:
                print(f"Request failed with status code {resp.status_code} for query: {q}")
                hits = []
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            print(f"Exception for query '{q}': {e}")
            hits = []
            
        latencies.append(latency_ms)
        category_stats[cat]["latency"].append(latency_ms)
        category_stats[cat]["count"] += 1
        
        match_rank = 0
        for rank, hit in enumerate(hits[:5], 1):
            if evaluate_hit(hit, expected):
                match_rank = rank
                break
                
        p1 = 1 if match_rank == 1 else 0
        p3 = 1 if 1 <= match_rank <= 3 else 0
        p5 = 1 if 1 <= match_rank <= 5 else 0
        mrr = 1.0 / match_rank if match_rank > 0 else 0.0
        
        overall_p1 += p1
        overall_p3 += p3
        overall_p5 += p5
        overall_mrr += mrr
        
        category_stats[cat]["p1"] += p1
        category_stats[cat]["p3"] += p3
        category_stats[cat]["p5"] += p5
        category_stats[cat]["mrr"] += mrr
        
        results_detailed.append({
            "idx": idx,
            "query": q,
            "category": cat,
            "latency_ms": latency_ms,
            "match_rank": match_rank if match_rank > 0 else "N/A",
            "top_hits": [f"{h.get('name_ar')} ({h.get('name_en')})" for h in hits[:3]]
        })

    total_cases = len(TEST_CASES)
    avg_latency = sum(latencies) / total_cases
    p95_latency = sorted(latencies)[int(total_cases * 0.95)]
    
    report_md = f"""# Search Pipeline Benchmark Results

This report evaluates the accuracy, relevance, and performance of the OpenSearch hybrid search pipeline over 100 sample query test cases.

## Core Aggregates

* **Total Test Queries**: {total_cases}
* **Mean Reciprocal Rank (MRR)**: {overall_mrr / total_cases:.4f}
* **Overall Precision @ 1**: {overall_p1 / total_cases * 100.0:.1f}% ({overall_p1}/{total_cases})
* **Overall Precision @ 3**: {overall_p3 / total_cases * 100.0:.1f}% ({overall_p3}/{total_cases})
* **Overall Precision @ 5**: {overall_p5 / total_cases * 100.0:.1f}% ({overall_p5}/{total_cases})
* **Average Latency**: {avg_latency:.2f} ms
* **95th Percentile Latency**: {p95_latency:.2f} ms

---

## Category-wise Performance breakdown

| Category | Query Count | Precision@1 | Precision@3 | Precision@5 | MRR | Avg Latency (ms) |
|---|---|---|---|---|---|---|
"""
    for cat_name, stats in category_stats.items():
        count = stats["count"]
        p1_rate = (stats["p1"] / count) * 100.0 if count > 0 else 0
        p3_rate = (stats["p3"] / count) * 100.0 if count > 0 else 0
        p5_rate = (stats["p5"] / count) * 100.0 if count > 0 else 0
        mrr_rate = stats["mrr"] / count if count > 0 else 0
        avg_cat_latency = sum(stats["latency"]) / count if count > 0 else 0
        
        report_md += f"| {cat_name} | {count} | {p1_rate:.1f}% | {p3_rate:.1f}% | {p5_rate:.1f}% | {mrr_rate:.4f} | {avg_cat_latency:.1f} |\n"
        
    report_md += """
---

## Detailed Test Logs (All cases)

| # | Query | Category | Match Rank | Top 3 Hits | Latency |
|---|---|---|---|---|---|
"""
    for res in results_detailed:
        hits_str = ", ".join(res["top_hits"])
        report_md += f"| {res['idx']} | {res['query']} | {res['category']} | {res['match_rank']} | {hits_str} | {res['latency_ms']:.1f} ms |\n"
        
    artifact_report_path = r"C:\Users\alisa\.gemini\antigravity\brain\20b90a2d-c83a-4750-8458-bc015c3202b1\benchmark_results.md"
    
    with open(artifact_report_path, "w", encoding="utf-8") as f:
        f.write(report_md)
        
    print(f"Benchmark finished successfully! Report written to {artifact_report_path}")

if __name__ == "__main__":
    run_benchmark()
