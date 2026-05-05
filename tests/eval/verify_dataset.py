"""Pre-flight: run all gold_sql in benchmark_dataset.yaml on AdventureWorks.

Ensures every gold SQL:
  - Executes without error
  - Returns at least 1 row (unless explicitly empty-expected)

Run before benchmark to catch dataset bugs.

Usage:
  python tests/eval/verify_dataset.py
  python tests/eval/verify_dataset.py --dataset path/to/dataset.yaml
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows so Unicode arrows / Vietnamese print correctly.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import yaml
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from askdataai.config import settings  # noqa: E402

from tests.eval.sql_executor import execute_sql  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("verify")

DEFAULT_DATASET = ROOT / "tests" / "eval" / "benchmark_dataset.yaml"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    p.add_argument("--allow-empty", action="store_true",
                   help="Don't fail on empty result sets")
    args = p.parse_args()

    if not args.dataset.exists():
        logger.error(f"Dataset not found: {args.dataset}")
        return 1

    raw = yaml.safe_load(args.dataset.read_text(encoding="utf-8"))
    examples = raw.get("examples", [])
    if not examples:
        logger.error("No examples in dataset")
        return 1

    engine = create_engine(settings.connection_string)

    ok = 0
    failed: list[tuple[str, str]] = []
    empty: list[str] = []

    for ex in examples:
        ex_id = ex.get("id", "?")
        sql = ex.get("gold_sql", "").strip()
        if not sql:
            failed.append((ex_id, "empty gold_sql"))
            continue

        result = execute_sql(engine, sql, row_cap=10)
        if not result.success:
            failed.append((ex_id, result.error[:120]))
            print(f"[FAIL]  {ex_id:14s} → {result.error[:120]}")
            continue

        if result.row_count == 0:
            empty.append(ex_id)
            print(f"[EMPTY] {ex_id:14s} ({len(result.columns)} cols, 0 rows)")
        else:
            ok += 1
            preview = str(result.rows[0])[:80] if result.rows else ""
            print(f"[OK]    {ex_id:14s} ({len(result.columns)} cols, {result.row_count} rows) → {preview}")

    print()
    print("=" * 60)
    print(f"Total:    {len(examples)}")
    print(f"OK:       {ok}")
    print(f"FAIL:     {len(failed)}")
    print(f"EMPTY:    {len(empty)}")
    print("=" * 60)

    if failed:
        print("\nFailures:")
        for fid, err in failed:
            print(f"  {fid}: {err}")

    if empty and not args.allow_empty:
        print(f"\nEmpty results (use --allow-empty to ignore): {empty}")

    if failed:
        return 1
    if empty and not args.allow_empty:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
