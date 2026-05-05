"""Spider-style execution match — fast path before LLM judge.

Compares two result sets with column permutation + ORDER BY awareness.
If exact match found, skip LLM call (saves cost + latency).

Inspired by:
  test-suite-sql-eval / exec_eval.py (Spider's official evaluation)
  https://github.com/taoyds/test-suite-sql-eval/blob/master/exec_eval.py
"""

from __future__ import annotations

import itertools
import re
from typing import Any

# Cap permutations to avoid factorial blow-up. With 8+ columns, permutations
# are too many; just try identity + alphabetical sort.
PERMUTATION_CAP = 5040  # 7! — past this, fall back to alphabetical only


def detect_order_matters(sql: str) -> bool:
    """True if outermost SELECT has ORDER BY (ignoring inner subqueries).

    Strips parenthesized subqueries first, then checks for ORDER BY in remainder.
    """
    if not sql:
        return False
    # Strip nested parenthesized blocks repeatedly until no more nesting
    stripped = sql
    prev = None
    while prev != stripped:
        prev = stripped
        stripped = re.sub(r'\([^()]*\)', '', stripped)
    return bool(re.search(r'\bORDER\s+BY\b', stripped, re.IGNORECASE))


def _row_to_tuple(row: dict, cols: list[str]) -> tuple:
    return tuple(row.get(c) for c in cols)


def _hashable(t: tuple) -> tuple:
    """Make tuple hashable — convert lists/dicts to repr."""
    out = []
    for v in t:
        if isinstance(v, (list, dict)):
            out.append(repr(v))
        else:
            out.append(v)
    return tuple(out)


def exec_match(
    pred_rows: list[dict],
    pred_cols: list[str],
    gold_rows: list[dict],
    gold_cols: list[str],
    *,
    order_matters: bool,
) -> tuple[bool, str]:
    """Spider-style execution match.

    Returns (match, reason). Tries column permutations to handle different
    projection orderings.
    """
    # Quick row-count check (multiset cardinality)
    if len(pred_rows) != len(gold_rows):
        return False, f"row_count mismatch ({len(pred_rows)} pred vs {len(gold_rows)} gold)"

    # Quick column-count check — if pipeline returns extra/missing columns,
    # permutation alone won't help. Spider also fails this case.
    if len(pred_cols) != len(gold_cols):
        return False, f"column_count mismatch ({len(pred_cols)} pred vs {len(gold_cols)} gold)"

    # Empty result: both empty → match
    if not pred_rows:
        return True, "both empty"

    # Convert to tuples in gold column order for stable comparison
    gold_tuples = [_hashable(_row_to_tuple(r, gold_cols)) for r in gold_rows]

    # Choose permutations to try
    if len(pred_cols) <= 7:
        permutations = list(itertools.permutations(range(len(pred_cols))))
    else:
        # Too many — try identity + alphabetical sort permutation only
        identity = tuple(range(len(pred_cols)))
        sorted_idx = sorted(range(len(pred_cols)), key=lambda i: pred_cols[i])
        permutations = [identity, tuple(sorted_idx)]

    for perm in permutations:
        permuted_cols = [pred_cols[i] for i in perm]
        permuted_rows = [
            _hashable(tuple(r.get(c) for c in permuted_cols))
            for r in pred_rows
        ]

        if order_matters:
            if permuted_rows == gold_tuples:
                return True, f"exact match (order required, perm={perm})"
        else:
            # Multiset equality: count each tuple
            if sorted(permuted_rows, key=str) == sorted(gold_tuples, key=str):
                return True, f"set match (perm={perm})"

    return False, "no permutation matches"
