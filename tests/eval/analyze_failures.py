"""Analyze failure patterns in benchmark JSON output.

Usage:
  python tests/eval/analyze_failures.py benchmarks/run_*.json
"""
import json
import re
import sys
import io
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def categorize(r: dict) -> str:
    """Heuristic-categorize failure reason from result row."""
    pred_rows = r["pred_row_count"]
    gold_rows = r["gold_row_count"]
    reason = (r.get("judge_reasoning") or "").lower()
    pred_sql = (r.get("pred_sql") or "").upper()
    gold_sql = ""  # We don't have gold_sql here, only pred
    method = r["match_method"]
    if method == "error":
        return "pipeline_error"
    if pred_rows == 100 and gold_rows > 100:
        return "limit_100_cutoff"
    if pred_rows == 0 and gold_rows > 0:
        return "empty_result"
    if "factinternetsales" not in pred_sql.lower() and "factresellersales" in pred_sql.lower():
        return "channel_reseller_used"
    if "column" in reason and ("missing" in reason or "extra" in reason or "different" in reason):
        return "column_projection"
    if "row count" in reason or ("rows" in reason and "differ" in reason):
        return "row_count_mismatch"
    if any(k in reason for k in ["distinct", "duplicate"]):
        return "distinct_handling"
    if any(k in reason for k in ["aggregat", "sum", "count", "average", "avg"]):
        return "aggregation_diff"
    if any(k in reason for k in ["filter", "where", "condition"]):
        return "filter_diff"
    if any(k in reason for k in ["join", "table"]):
        return "join_diff"
    if any(k in reason for k in ["order", "sort", "rank"]):
        return "order_diff"
    return "other"


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_failures.py <benchmark.json>")
        sys.exit(1)
    p = Path(sys.argv[1])
    data = json.loads(p.read_text(encoding="utf-8"))
    results = data["results"]
    fails = [r for r in results if not r["match"]]

    print(f"=== Benchmark: {p.name} ===")
    print(f"Total: {len(results)} | Correct: {len(results) - len(fails)} | Failures: {len(fails)}")
    print()

    # Category counts
    cats = Counter()
    by_diff = defaultdict(Counter)
    examples = defaultdict(list)
    for r in fails:
        cat = categorize(r)
        cats[cat] += 1
        by_diff[cat][r["difficulty"]] += 1
        examples[cat].append(r["example_id"])

    print("=== Failure categories (sorted by count) ===")
    for cat, count in cats.most_common():
        diff_str = f"easy={by_diff[cat]['easy']}, medium={by_diff[cat]['medium']}, hard={by_diff[cat]['hard']}"
        print(f"  {count:3d}  {cat:25s}  ({diff_str})")
        ids = ", ".join(examples[cat][:8])
        if len(examples[cat]) > 8:
            ids += f" ...(+{len(examples[cat])-8} more)"
        print(f"       └─ {ids}")
    print()

    # Detailed look at limit_100 cases
    limit_cases = [r for r in fails if categorize(r) == "limit_100_cutoff"]
    if limit_cases:
        print(f"=== LIMIT 100 cutoff details ({len(limit_cases)} cases) ===")
        for r in limit_cases:
            print(f"  {r['example_id']:14s} ({r['difficulty']:6s}) gold={r['gold_row_count']:6d} pred=100")
        print()

    # Empty result cases
    empty_cases = [r for r in fails if categorize(r) == "empty_result"]
    if empty_cases:
        print(f"=== Empty result details ({len(empty_cases)} cases) ===")
        for r in empty_cases[:10]:
            reason = (r.get("judge_reasoning") or "")[:140]
            print(f"  {r['example_id']:14s} ({r['difficulty']:6s}) gold={r['gold_row_count']:5d} reason={reason}")
        print()

    # Pipeline errors
    err_cases = [r for r in fails if r["match_method"] == "error"]
    if err_cases:
        print(f"=== Pipeline errors ({len(err_cases)} cases) ===")
        for r in err_cases:
            err = (r.get("pred_error") or r.get("compare_reason") or "")[:200]
            print(f"  {r['example_id']:14s} ({r['difficulty']:6s}) error={err}")
        print()

    # Channel ambiguity
    channel_cases = [r for r in fails if categorize(r) == "channel_reseller_used"]
    if channel_cases:
        print(f"=== Reseller channel used by pipeline ({len(channel_cases)} cases) ===")
        for r in channel_cases[:10]:
            print(f"  {r['example_id']:14s} ({r['difficulty']:6s})")
        print()

    # Sample reasoning of "other" category
    other = [r for r in fails if categorize(r) == "other"]
    if other:
        print(f"=== Sample reasoning for 'other' ({len(other)}) ===")
        for r in other[:8]:
            reason = (r.get("judge_reasoning") or "")[:200]
            print(f"  {r['example_id']:14s} ({r['difficulty']:6s}) {reason}")


if __name__ == "__main__":
    main()
