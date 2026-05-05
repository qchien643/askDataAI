"""LLM-as-judge for benchmark — fallback when canonical exact match fails.

Sends (question, gold_sql, pred_sql, sample rows from each) to OpenAI and asks:
"Does the predicted SQL correctly answer the question?"

Uses GPT-4o-mini for cost-efficiency (~$0.0003/judgment).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class JudgeResult:
    verdict: Literal["correct", "incorrect", "partial"]
    reasoning: str
    confidence: float = 0.0
    error: str = ""


JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for a Text-to-SQL system.

Your task: judge whether a PREDICTED SQL correctly answers a user's natural-language question, by examining both the SQL and the actual result rows.

Evaluation principles:
1. Focus on whether the result CORRECTLY ANSWERS the question's intent. The predicted SQL may differ in syntax, joins, or column ordering — that's fine if results are equivalent.
2. Different but valid alternative interpretations may exist. If the predicted result is a reasonable answer to the question, mark "correct".
3. The predicted result may have:
   - Extra columns (still informative) → usually correct if core data matches
   - Missing key columns → likely incorrect
   - Different column names but same data → correct
   - Different row counts (very different) → likely incorrect
   - Different aggregation (e.g., COUNT(*) vs COUNT(DISTINCT)) → check question intent
4. The predicted SQL was generated WITHOUT seeing the gold SQL. Don't expect identical structure.

Output strict JSON:
{
  "verdict": "correct" | "incorrect" | "partial",
  "reasoning": "<1-2 sentences explaining>",
  "confidence": <0.0 to 1.0, your confidence in this verdict>
}

Use "partial" when the predicted result is partially correct (e.g., right entities but wrong aggregation, or right answer but missing required filter).
"""


def _format_rows_preview(rows: list[dict], cols: list[str], n: int = 5) -> str:
    """Format first N rows as a compact text table."""
    if not rows:
        return "(empty result set)"
    if not cols:
        cols = list(rows[0].keys())
    lines = [" | ".join(str(c) for c in cols)]
    lines.append("-+-".join("-" * len(str(c)) for c in cols))
    for row in rows[:n]:
        lines.append(" | ".join(str(row.get(c, "")) for c in cols))
    if len(rows) > n:
        lines.append(f"... ({len(rows) - n} more rows)")
    return "\n".join(lines)


def judge(
    *,
    question_vi: str,
    question_en: str,
    gold_sql: str,
    pred_sql: str,
    gold_rows: list[dict],
    gold_cols: list[str],
    gold_row_count: int,
    pred_rows: list[dict],
    pred_cols: list[str],
    pred_row_count: int,
    pred_valid: bool,
    pred_error: str,
    llm: LLMClient,
) -> JudgeResult:
    """Ask LLM whether predicted SQL correctly answers the question."""

    # Short-circuit: pred SQL didn't execute → automatically incorrect
    if not pred_valid:
        return JudgeResult(
            verdict="incorrect",
            reasoning=f"Predicted SQL failed to execute: {pred_error[:200]}",
            confidence=1.0,
        )

    user_prompt = f"""# Question
Vietnamese: {question_vi}
English: {question_en}

# GOLD SQL (reference correct answer)
```sql
{gold_sql.strip()}
```

# GOLD RESULT
columns: {gold_cols}
total_rows: {gold_row_count}
preview:
{_format_rows_preview(gold_rows, gold_cols)}

# PREDICTED SQL (system output)
```sql
{pred_sql.strip()}
```

# PREDICTED RESULT
columns: {pred_cols}
total_rows: {pred_row_count}
preview:
{_format_rows_preview(pred_rows, pred_cols)}

Is the predicted SQL a correct answer to the question? Respond with strict JSON."""

    try:
        result = llm.chat_json(
            user_prompt=user_prompt,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            temperature=0.0,
        )
    except Exception as e:
        logger.error(f"Judge LLM call failed: {e}")
        return JudgeResult(
            verdict="incorrect",
            reasoning=f"judge LLM error: {e}",
            confidence=0.0,
            error=str(e),
        )

    if "error" in result and "verdict" not in result:
        return JudgeResult(
            verdict="incorrect",
            reasoning=f"judge JSON parse failed: {result.get('error', 'unknown')}",
            confidence=0.0,
            error=str(result),
        )

    verdict = str(result.get("verdict", "incorrect")).lower().strip()
    if verdict not in ("correct", "incorrect", "partial"):
        verdict = "incorrect"

    return JudgeResult(
        verdict=verdict,  # type: ignore
        reasoning=str(result.get("reasoning", ""))[:500],
        confidence=float(result.get("confidence", 0.0)),
    )
