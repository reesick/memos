"""
demo/benchmark.py – MemoryOS retrieval quality benchmark

Runs a suite of questions against the memory store and measures:
  - recall@k   (was the correct answer in top-k results?)
  - precision@1 (was the first result correct?)
  - p50 / p95 retrieval latency

Questions are generated from the seed data produced by generate_test_data.py,
so run that first:

    python demo/generate_test_data.py --count 50
    python demo/benchmark.py --api http://localhost:8000 --top-k 5

Output: benchmark_results.json (timestamped)
"""

import argparse
import json
import time
import sys
import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not found. pip install httpx")
    sys.exit(1)

API_DEFAULT = "http://localhost:8000"

# ── Benchmark questions ──────────────────────────────────────────────────────
# Each: (query, must_contain_in_value, must_contain_entity)
# "correct" if ANY result.value contains expected_value_fragment
# AND result.entity == expected_entity (or entity is None = don't check entity)

BENCHMARK_QUESTIONS = [
    # People + roles
    ("What is Arjun's role?",        "engineer",      "Arjun"),
    ("Where does Priya work?",       None,            "Priya"),
    ("What school did Sam attend?",  None,            "Sam"),
    ("What city is Leila based in?", None,            "Leila"),
    ("What tech does Dev use?",      None,            "Dev"),
    # Technologies
    ("Who uses React?",              "React",         None),
    ("Who works with PyTorch?",      "PyTorch",       None),
    ("Who uses Kubernetes?",         "Kubernetes",    None),
    # Companies
    ("Who works at Acme Corp?",      None,            None),
    ("Who joined NexaLabs?",         None,            None),
    # Projects
    ("What is MemoryOS built with?", None,            None),
    ("Who leads ProjectAlpha?",      None,            None),
    # Generic semantic
    ("Who is the backend engineer?", "engineer",      None),
    ("Who studied computer science?",None,            None),
    ("Who is based in Bangalore?",   "Bangalore",     None),
]


def score_result(results: list, expected_value: str | None, expected_entity: str | None) -> bool:
    """Return True if any result matches both constraints."""
    for r in results:
        val_ok   = (expected_value  is None) or (expected_value.lower()  in r.get("value",  "").lower())
        ent_ok   = (expected_entity is None) or (expected_entity.lower() == r.get("entity", "").lower())
        if val_ok and ent_ok:
            return True
    return False


def run_query(client: httpx.Client, query: str, top_k: int) -> tuple:
    """Returns (results, latency_ms)."""
    start = time.perf_counter()
    r = client.post("/memory/search", json={"query": query, "top_k": top_k})
    elapsed = (time.perf_counter() - start) * 1000
    r.raise_for_status()
    return r.json().get("results", []), elapsed


def main():
    parser = argparse.ArgumentParser(description="Benchmark MemoryOS retrieval quality")
    parser.add_argument("--api",   default=API_DEFAULT, help="API base URL")
    parser.add_argument("--top-k", type=int, default=5,  help="top_k for search")
    parser.add_argument("--output", default="benchmark_results.json", help="Output file")
    args = parser.parse_args()

    print(f"🔬  MemoryOS Benchmark — {args.api}  (top_k={args.top_k})")
    print(f"    {len(BENCHMARK_QUESTIONS)} questions\n")

    latencies = []
    recall_hits = 0
    precision1_hits = 0

    with httpx.Client(base_url=args.api, timeout=30) as client:
        # Verify API
        try:
            r = client.get("/health")
            r.raise_for_status()
            total_mems = client.get("/memory/list?limit=1").json().get("total", 0)
        except Exception as e:
            print(f"❌  API not reachable: {e}")
            sys.exit(1)

        print(f"    Total memories in store: {total_mems}\n")

        detailed = []
        for q, exp_val, exp_ent in BENCHMARK_QUESTIONS:
            try:
                results, ms = run_query(client, q, args.top_k)
                latencies.append(ms)

                hit_k = score_result(results,          exp_val, exp_ent)
                hit_1 = score_result(results[:1],      exp_val, exp_ent)

                if hit_k: recall_hits += 1
                if hit_1: precision1_hits += 1

                status = "✓" if hit_k else "✗"
                top_val = results[0]["value"][:50] if results else "—"
                print(f"  {status}  [{ms:5.0f}ms]  {q[:55]:<55}  → {top_val}")

                detailed.append({
                    "query":            q,
                    "expected_value":   exp_val,
                    "expected_entity":  exp_ent,
                    "recall_k":         hit_k,
                    "precision_1":      hit_1,
                    "latency_ms":       round(ms, 1),
                    "top_result":       results[0] if results else None,
                })
            except Exception as e:
                print(f"  ✗  {q[:55]}  → ERROR: {e}")
                detailed.append({"query": q, "error": str(e)})

    n = len(BENCHMARK_QUESTIONS)
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0

    summary = {
        "timestamp":      datetime.datetime.now().isoformat(),
        "api":            args.api,
        "top_k":          args.top_k,
        "total_questions":n,
        "recall_at_k":    round(recall_hits / n, 3),
        "precision_at_1": round(precision1_hits / n, 3),
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "total_memories": total_mems,
        "questions":      detailed,
    }

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Recall@{args.top_k}:     {recall_hits}/{n}  ({summary['recall_at_k']*100:.0f}%)
  Precision@1:  {precision1_hits}/{n}  ({summary['precision_at_1']*100:.0f}%)
  Latency p50:  {p50:.0f}ms
  Latency p95:  {p95:.0f}ms
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")

    out_path = Path(args.output)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\n  Results saved → {out_path.resolve()}\n")
    return summary


if __name__ == "__main__":
    main()
