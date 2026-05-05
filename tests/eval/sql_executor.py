"""Safe SQL execution helper for benchmark.

Executes a SQL query on AdventureWorks SQL Server with:
- Timeout per query
- Row cap (don't pull millions of rows for comparison)
- Graceful error capture
- Decimal/datetime normalization for downstream comparison
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy
from sqlalchemy import text


# Cap rows we pull for comparison. If a query returns more, we still record
# total count but only compare first N rows. Most benchmark queries should
# return < 100 rows; queries returning thousands are usually projection mistakes.
DEFAULT_ROW_CAP = 1000


@dataclass
class ExecutionResult:
    """Result of executing one SQL query."""
    sql: str
    success: bool
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: int = 0          # total rows (may exceed len(rows) if capped)
    truncated: bool = False     # True if row_count > len(rows)
    error: str = ""
    duration_ms: int = 0


def _normalize_value(val: Any) -> Any:
    """Make values JSON-serializable + comparable.

    - Decimal → float (rounded to 6 decimals)
    - datetime at midnight → date string
    - bytes → repr (rare)
    """
    if val is None:
        return None
    if isinstance(val, Decimal):
        return round(float(val), 6)
    if isinstance(val, datetime):
        if val.hour == val.minute == val.second == val.microsecond == 0:
            return val.strftime("%Y-%m-%d")
        return val.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(val, date):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, bytes):
        return f"<bytes:{len(val)}>"
    return val


def execute_sql(
    engine: sqlalchemy.Engine,
    sql: str,
    *,
    row_cap: int = DEFAULT_ROW_CAP,
    timeout_sec: int = 30,
) -> ExecutionResult:
    """Run a SQL query, return rows + metadata.

    On error, success=False and error contains the message. Never raises.
    """
    start = time.time()
    try:
        with engine.connect() as conn:
            # Best-effort timeout for SQL Server (LOCK_TIMEOUT in ms)
            try:
                conn.execute(text(f"SET LOCK_TIMEOUT {timeout_sec * 1000}"))
            except Exception:
                pass

            result = conn.execute(text(sql))
            cols = list(result.keys()) if result.returns_rows else []

            rows: list[dict] = []
            row_count = 0
            for raw_row in result:
                row_count += 1
                if len(rows) < row_cap:
                    rows.append({c: _normalize_value(v) for c, v in zip(cols, raw_row)})

            return ExecutionResult(
                sql=sql,
                success=True,
                rows=rows,
                columns=cols,
                row_count=row_count,
                truncated=row_count > len(rows),
                duration_ms=int((time.time() - start) * 1000),
            )
    except Exception as e:
        return ExecutionResult(
            sql=sql,
            success=False,
            error=str(e)[:500],
            duration_ms=int((time.time() - start) * 1000),
        )
