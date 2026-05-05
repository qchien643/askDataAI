"""
SQL Corrector - Validate SQL on the real DB, retry on error.

Logic:
1. Run SQL on real SQL Server
2. If OK → return result
3. If error → send back to LLM with error message → retry (max 3 times)

Equivalent to SQLCorrection in the original WrenAI
(wren-ai-service/src/pipelines/generation/sql_correction.py).
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy

from askdataai.generation.correction_fixer import CorrectionFixer
from askdataai.generation.correction_planner import CorrectionPlan, CorrectionPlanner
from askdataai.generation.llm_client import LLMClient
from askdataai.generation.sql_rewriter import SQLRewriter

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


@dataclass
class CorrectionResult:
    """Result after the correction loop."""
    valid: bool
    sql: str                          # Final SQL (after rewrite)
    original_sql: str = ""            # Original SQL from LLM (before rewrite)
    result: dict[str, Any] | None = None  # Query result (columns + rows)
    explanation: str = ""
    retries: int = 0
    errors: list[str] = field(default_factory=list)
    # Sprint 5: taxonomy-guided diagnostics
    correction_plans: list[CorrectionPlan] = field(default_factory=list)
    strategy_used: str = "execution_only"  # "execution_only" | "taxonomy_guided"


SQL_CORRECTION_SYSTEM_PROMPT = """You are a T-SQL debugging expert for SQL Server.

Your task: fix a broken SQL query based on the error message and database schema.

### RULES ###
1. Carefully analyze the error message to find the root cause
2. ONLY use tables/columns present in the schema
3. Follow T-SQL syntax (TOP instead of LIMIT, GETDATE instead of NOW, etc.)
4. Preserve the original meaning of the query
5. DO NOT use DECLARE @variable — inline values directly
6. If the query uses CTEs (WITH ... AS):
   - DO NOT use ORDER BY inside a CTE unless TOP is also present
   - DO NOT nest WITH inside another CTE (nested WITH is a syntax error)
   - Use only one WITH keyword at the top; separate CTEs with commas
7. If error is "ORDER BY is invalid in views/CTE": remove ORDER BY or add TOP

### OUTPUT FORMAT ###
{
    "sql": "<CORRECTED_SQL_QUERY>",
    "explanation": "<brief explanation of what was fixed>"
}
"""


SQL_CORRECTION_USER_PROMPT = """### DATABASE SCHEMA ###
{ddl_context}

### BROKEN SQL ###
```sql
{sql}
```

### ERROR MESSAGE ###
{error}

Please fix the SQL query above.
"""


class SQLCorrector:
    """
    Validate + auto-correct SQL queries.

    Runs SQL on real DB → on error → sends to LLM to fix → retry.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        rewriter: SQLRewriter,
        engine: sqlalchemy.Engine,
        max_retries: int = MAX_RETRIES,
        planner: CorrectionPlanner | None = None,  # Sprint 5
        fixer: CorrectionFixer | None = None,      # Sprint 5
    ):
        self._llm = llm_client
        self._rewriter = rewriter
        self._engine = engine
        self._max_retries = max_retries
        # Sprint 5 — taxonomy-guided components (lazy: only used when toggle ON)
        self._planner = planner
        self._fixer = fixer

    def validate_and_correct(
        self,
        sql: str,
        ddl_context: str = "",
        question: str = "",
        explanation: str = "",
        strategy: str | None = None,
    ) -> CorrectionResult:
        """Validate SQL on the real DB, retry on error.

        Sprint 5: dispatches between two correction strategies based on
        settings.correction_strategy:
          - "execution_only" (default, legacy): regex-classify error + LLM fix
          - "taxonomy_guided": full LLM CorrectionPlanner + CorrectionFixer

        Per-request override via `strategy`; falls back to
        `settings.correction_strategy` when None.

        Args:
            sql: SQL query (uses model names, not yet rewritten).
            ddl_context: DDL context for the correction prompt.
            question: Original user question (used by taxonomy_guided path).
            explanation: Explanation from the generator.
            strategy: Optional per-request strategy override.

        Returns:
            CorrectionResult.
        """
        if strategy is None:
            from askdataai.config import settings  # late import to avoid cycle
            strategy = getattr(settings, "correction_strategy", "execution_only")

        if strategy == "taxonomy_guided" and self._planner and self._fixer:
            return self._taxonomy_guided_loop(
                sql=sql, ddl_context=ddl_context,
                question=question, explanation=explanation,
            )
        return self._execution_only_loop(
            sql=sql, ddl_context=ddl_context, explanation=explanation,
        )

    def _execution_only_loop(
        self,
        sql: str,
        ddl_context: str,
        explanation: str,
    ) -> CorrectionResult:
        """Legacy: execute → on error, classify (regex) + 1 LLM call to fix."""
        errors: list[str] = []
        current_sql = sql

        for attempt in range(self._max_retries + 1):
            rewritten_sql = self._rewriter.rewrite(current_sql)
            success, result, error = self._execute_sql(rewritten_sql)

            if success:
                logger.info(f"SQL validated OK (attempt {attempt + 1})")
                return CorrectionResult(
                    valid=True,
                    sql=rewritten_sql,
                    original_sql=sql,
                    result=result,
                    explanation=explanation,
                    retries=attempt,
                    errors=errors,
                    strategy_used="execution_only",
                )

            errors.append(error)
            logger.warning(
                f"SQL failed (attempt {attempt + 1}/{self._max_retries + 1}): {error[:100]}"
            )

            if attempt < self._max_retries:
                corrected = self._correct_sql(current_sql, error, ddl_context)
                if corrected:
                    current_sql = corrected
                    logger.info(f"LLM corrected SQL: {corrected[:100]}...")
                else:
                    break

        return CorrectionResult(
            valid=False,
            sql=self._rewriter.rewrite(current_sql),
            original_sql=sql,
            explanation=explanation,
            retries=self._max_retries,
            errors=errors,
            strategy_used="execution_only",
        )

    def _taxonomy_guided_loop(
        self,
        sql: str,
        ddl_context: str,
        question: str,
        explanation: str,
    ) -> CorrectionResult:
        """Sprint 5: taxonomy-guided correction.

        Per attempt: execute → on error → Planner (classify) → Fixer (apply strategy).
        Two LLM calls per retry (vs one for execution_only) but laser-focused
        prompts → typically higher recovery rate.

        P1 fix: cap at 2 taxonomy retries (vs MAX_RETRIES=3) and bail out when the
        same error repeats — fixer is stuck producing semantically-equivalent SQL.
        """
        errors: list[str] = []
        plans: list[CorrectionPlan] = []
        current_sql = sql
        taxonomy_retry_cap = min(2, self._max_retries)

        for attempt in range(taxonomy_retry_cap + 1):
            rewritten_sql = self._rewriter.rewrite(current_sql)
            success, result, error = self._execute_sql(rewritten_sql)

            if success:
                logger.info(
                    f"SQL validated OK (attempt {attempt + 1}, taxonomy_guided)"
                )
                return CorrectionResult(
                    valid=True,
                    sql=rewritten_sql,
                    original_sql=sql,
                    result=result,
                    explanation=explanation,
                    retries=attempt,
                    errors=errors,
                    correction_plans=plans,
                    strategy_used="taxonomy_guided",
                )

            errors.append(error)
            logger.warning(
                f"SQL failed (attempt {attempt + 1}/{taxonomy_retry_cap + 1}, "
                f"taxonomy_guided): {error[:100]}"
            )

            # Bail out when fixer keeps producing the same failure (no progress).
            if len(errors) >= 2 and errors[-1].strip() == errors[-2].strip():
                logger.warning("Fixer made no progress (same error twice) — breaking retry")
                break

            if attempt >= taxonomy_retry_cap:
                break

            plan = self._planner.plan(
                question=question,
                sql=current_sql,
                exec_error=error,
                ddl_context=ddl_context,
            )
            plans.append(plan)
            logger.info(
                f"Plan: {plan.category}/{plan.sub_category} "
                f"(conf={plan.confidence:.2f}) — {plan.repair_strategy[:120]}"
            )

            corrected, fix_explanation = self._fixer.fix(
                question=question,
                original_sql=current_sql,
                plan=plan,
                ddl_context=ddl_context,
                exec_error=error,
            )
            if corrected and corrected != current_sql:
                current_sql = corrected
                logger.info(f"Fixer produced new SQL: {corrected[:100]}...")
            else:
                logger.warning("Fixer returned same/empty SQL — breaking retry")
                break

        return CorrectionResult(
            valid=False,
            sql=self._rewriter.rewrite(current_sql),
            original_sql=sql,
            explanation=explanation,
            retries=taxonomy_retry_cap,
            errors=errors,
            correction_plans=plans,
            strategy_used="taxonomy_guided",
        )

    def _execute_sql(
        self, sql: str, limit: int | None = None
    ) -> tuple[bool, dict | None, str]:
        """
        Execute SQL on the real DB.

        Returns:
            (success, result_dict, error_message)
        """
        if limit is None:
            from askdataai.config import settings
            limit = getattr(settings, "exec_row_limit", 10000)
        try:
            with self._engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(sql))
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchmany(limit)]

                return True, {"columns": columns, "rows": rows, "row_count": len(rows)}, ""

        except Exception as e:
            error_msg = str(e)
            # Extract the main error part
            if "Original error" in error_msg:
                error_msg = error_msg.split("Original error")[0]
            return False, None, error_msg.strip()

    def _correct_sql(
        self, sql: str, error: str, ddl_context: str
    ) -> str | None:
        """Send SQL to LLM for correction, with error classification to guide targeted fix."""
        try:
            # Classify error type
            error_type, fix_hint = self.classify_error(error)
            logger.info(f"Error taxonomy: {error_type}")

            # Try auto-fix first (no LLM call needed)
            auto_fixed = self._try_auto_fix(sql, error_type)
            if auto_fixed and auto_fixed != sql:
                logger.info(f"Auto-fixed ({error_type}): {auto_fixed[:80]}...")
                return auto_fixed

            # LLM correction with taxonomy hint
            correction_hint = f"\n### ERROR TYPE: {error_type} ###\n{fix_hint}\n"

            user_prompt = SQL_CORRECTION_USER_PROMPT.format(
                ddl_context=ddl_context,
                sql=sql,
                error=error,
            )
            user_prompt = correction_hint + user_prompt

            result = self._llm.chat_json(
                user_prompt=user_prompt,
                system_prompt=SQL_CORRECTION_SYSTEM_PROMPT,
            )

            return result.get("sql", "")
        except Exception as e:
            logger.error(f"SQL correction LLM call failed: {e}")
            return None

    # ── Taxonomy-guided error classification (SQL-of-Thought 2025) ──

    @staticmethod
    def classify_error(error: str) -> tuple[str, str]:
        """
        Classify SQL error into taxonomy for targeted fix.

        Returns:
            (error_type, fix_hint) tuple.

        Error types:
        - INVALID_COLUMN: Column doesn't exist → re-check schema
        - INVALID_OBJECT: Table doesn't exist → re-check table names
        - CTE_SYNTAX: ORDER BY in CTE, nested WITH, etc.
        - MISSING_JOIN: Ambiguous column (exists in multiple tables)
        - SYNTAX_ERROR: General T-SQL syntax issue
        - LOGIC_ERROR: Query runs but wrong results (empty, unexpected)
        """
        import re
        error_upper = error.upper()

        if re.search(r"INVALID COLUMN NAME", error_upper):
            col_match = re.search(r"Invalid column name '(\w+)'", error, re.IGNORECASE)
            col_name = col_match.group(1) if col_match else "unknown"
            return "INVALID_COLUMN", (
                f"Column '{col_name}' does not exist. "
                f"Check the DATABASE SCHEMA and find a similar column. "
                f"You may need to JOIN another table that contains this column."
            )

        if re.search(r"INVALID OBJECT NAME", error_upper):
            obj_match = re.search(r"Invalid object name '([^']+)'", error, re.IGNORECASE)
            obj_name = obj_match.group(1) if obj_match else "unknown"
            return "INVALID_OBJECT", (
                f"Table '{obj_name}' does not exist. "
                f"Check the DATABASE SCHEMA and use the correct table name."
            )

        if re.search(r"ORDER BY.*(VIEW|SUBQUER|INLINE|DERIVED|CTE)", error_upper):
            return "CTE_SYNTAX", (
                "ORDER BY is not allowed inside a CTE/subquery. "
                "Remove ORDER BY or add TOP N before ORDER BY."
            )

        if re.search(r"AMBIGUOUS COLUMN", error_upper):
            return "MISSING_JOIN", (
                "Column exists in multiple tables. "
                "Add a table alias (e.g. t.ColumnName instead of ColumnName)."
            )

        if re.search(r"INCORRECT SYNTAX", error_upper):
            return "SYNTAX_ERROR", (
                "T-SQL syntax error. Check: "
                "- Missing or extra commas "
                "- Misplaced keyword "
                "- DECLARE (should inline values instead)"
            )

        if re.search(r"CONVERSION|CONVERT|CAST|DATATYPE", error_upper):
            return "TYPE_ERROR", (
                "Data type error. Use CAST() or CONVERT() to convert types."
            )

        return "LOGIC_ERROR", "SQL logic error. Review JOIN conditions and WHERE clause."

    @staticmethod
    def _try_auto_fix(sql: str, error_type: str) -> str | None:
        """
        Auto-fix deterministic errors without LLM call.

        Returns fixed SQL or None if can't auto-fix.
        """
        import re

        if error_type == "CTE_SYNTAX":
            # Strip ORDER BY in CTEs (but keep in final SELECT)
            # Find CTEs: WITH name AS (...) and remove ORDER BY inside
            fixed = sql
            # Simple approach: if ORDER BY exists without TOP, strip it
            if re.search(r"\bORDER\s+BY\b", fixed, re.IGNORECASE):
                if not re.search(r"\bTOP\s+\d+\b", fixed, re.IGNORECASE):
                    fixed = re.sub(
                        r"\bORDER\s+BY\s+[^)]+",
                        "",
                        fixed,
                        flags=re.IGNORECASE,
                    )
                    return fixed.strip()

        if error_type == "SYNTAX_ERROR":
            # Strip DECLARE statements
            if "DECLARE" in sql.upper():
                lines = sql.split("\n")
                filtered = [l for l in lines if not l.strip().upper().startswith("DECLARE")]
                if filtered:
                    return "\n".join(filtered)

        return None

