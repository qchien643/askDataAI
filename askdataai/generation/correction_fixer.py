"""CorrectionFixer — Sprint 5.

Given a failed SQL + a CorrectionPlan (from CorrectionPlanner), generate a
corrected SQL that applies the plan's repair_strategy.

This is the second step in taxonomy-guided correction:
    Planner: failure → CorrectionPlan{category, sub_category, root_cause, repair_strategy}
    Fixer:   plan + original SQL → corrected SQL

The split (vs single-call execution_only correction) allows:
  - Planner can deeply analyze without committing to a fix
  - Fixer prompt is laser-focused on applying the strategy
  - Each LLM call has a tighter scope → better accuracy

Inspired by SQL-of-Thought (arXiv 2509.00581).
"""

from __future__ import annotations

import logging
import re

from askdataai.generation.correction_planner import CorrectionPlan
from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are an expert T-SQL SQL Server developer.

You will be given:
- The user's question
- The DDL schema available
- A broken SQL query
- A diagnostic plan describing what went wrong + a repair strategy

Your task: produce a CORRECTED SQL that applies the repair strategy.

Rules:
- ONLY use tables/columns present in the DDL schema
- Follow T-SQL syntax (TOP not LIMIT, GETDATE not NOW, [dbo].[Table] qualifier)
- DO NOT use DECLARE @variable — inline values directly
- Do NOT use ORDER BY inside CTEs unless TOP is also present
- Output the corrected SQL ONLY — no markdown fences, no commentary

Output JSON:
{
  "sql": "<CORRECTED SQL>",
  "explanation": "<1-sentence summary of what changed>"
}
"""


class CorrectionFixer:
    """Apply a CorrectionPlan to produce corrected SQL."""

    def __init__(self, llm: LLMClient):
        self._llm = llm

    def fix(
        self,
        question: str,
        original_sql: str,
        plan: CorrectionPlan,
        ddl_context: str = "",
        exec_error: str = "",
    ) -> tuple[str, str]:
        """Apply the repair strategy.

        Returns:
            (corrected_sql, explanation). On failure, (original_sql, error_msg).
        """
        user_prompt = f"""# Question
{question}

# DDL Schema
{ddl_context[:6000]}

# Broken SQL
```sql
{original_sql}
```

# Execution Error
{exec_error}

# Diagnostic Plan
- Category: {plan.category} / {plan.sub_category}
- Root cause: {plan.root_cause}
- Repair strategy: {plan.repair_strategy}

Apply the repair strategy. Output JSON with the corrected SQL."""

        try:
            result = self._llm.chat_json(
                user_prompt=user_prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.0,
            )
        except Exception as e:
            logger.error(f"CorrectionFixer LLM call failed: {e}")
            return original_sql, f"fixer LLM error: {e}"

        sql = str(result.get("sql", "")).strip()
        # Strip leftover markdown fences if any
        sql = re.sub(r"^```(?:sql)?\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        explanation = str(result.get("explanation", "")).strip()

        if not sql:
            return original_sql, "fixer returned empty SQL"

        return sql, explanation
