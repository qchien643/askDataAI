"""
SQL Corrector - Validate SQL trên DB thật, retry nếu lỗi.

Logic:
1. Chạy SQL trên SQL Server thật
2. Nếu OK → trả kết quả
3. Nếu lỗi → gửi lại LLM kèm error message → retry (max 3 lần)

Tương đương SQLCorrection trong WrenAI gốc
(wren-ai-service/src/pipelines/generation/sql_correction.py).
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy

from src.generation.llm_client import LLMClient
from src.generation.sql_rewriter import SQLRewriter

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


@dataclass
class CorrectionResult:
    """Kết quả sau correction loop."""
    valid: bool
    sql: str                          # SQL cuối cùng (đã rewrite)
    original_sql: str = ""            # SQL gốc từ LLM (trước rewrite)
    result: dict[str, Any] | None = None  # Query result (columns + rows)
    explanation: str = ""
    retries: int = 0
    errors: list[str] = field(default_factory=list)


SQL_CORRECTION_SYSTEM_PROMPT = """Bạn là chuyên gia T-SQL debugging cho SQL Server.

Nhiệm vụ: sửa SQL query bị lỗi dựa trên error message và database schema.

### QUY TẮC ###
1. Phân tích kỹ error message để tìm root cause
2. CHỈ dùng tables/columns có trong schema
3. Tuân thủ T-SQL syntax (TOP thay LIMIT, GETDATE thay NOW, v.v.)
4. Giữ nguyên ý nghĩa của query gốc
5. KHÔNG dùng DECLARE @variable — inline giá trị trực tiếp
6. Nếu query có CTE (WITH ... AS):
   - KHÔNG dùng ORDER BY trong CTE trừ khi có TOP
   - KHÔNG lồng WITH bên trong CTE (nested WITH là lỗi cú pháp)
   - Chỉ dùng 1 keyword WITH ở đầu, các CTE cách nhau bằng dấu phẩy
7. Nếu lỗi "ORDER BY is invalid in views/CTE": xóa ORDER BY hoặc thêm TOP

### FORMAT KẾT QUẢ ###
{
    "sql": "<CORRECTED_SQL_QUERY>",
    "explanation": "<giải thích ngắn gọn đã sửa gì>"
}
"""


SQL_CORRECTION_USER_PROMPT = """### DATABASE SCHEMA ###
{ddl_context}

### SQL BỊ LỖI ###
```sql
{sql}
```

### ERROR MESSAGE ###
{error}

Hãy sửa lại SQL query trên.
"""


class SQLCorrector:
    """
    Validate + auto-correct SQL queries.

    Chạy SQL thật trên DB → nếu lỗi → gửi LLM sửa → retry.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        rewriter: SQLRewriter,
        engine: sqlalchemy.Engine,
        max_retries: int = MAX_RETRIES,
    ):
        self._llm = llm_client
        self._rewriter = rewriter
        self._engine = engine
        self._max_retries = max_retries

    def validate_and_correct(
        self,
        sql: str,
        ddl_context: str = "",
        question: str = "",
        explanation: str = "",
    ) -> CorrectionResult:
        """
        Validate SQL trên DB thật, retry nếu lỗi.

        Args:
            sql: SQL query (dùng model names, chưa rewrite).
            ddl_context: DDL context cho correction prompt.
            question: Câu hỏi gốc.
            explanation: Giải thích từ generator.

        Returns:
            CorrectionResult.
        """
        errors: list[str] = []
        current_sql = sql

        for attempt in range(self._max_retries + 1):
            # Rewrite model names → DB names
            rewritten_sql = self._rewriter.rewrite(current_sql)

            # Thử chạy trên DB
            success, result, error = self._execute_sql(rewritten_sql)

            if success:
                logger.info(
                    f"SQL validated OK (attempt {attempt + 1})"
                )
                return CorrectionResult(
                    valid=True,
                    sql=rewritten_sql,
                    original_sql=sql,
                    result=result,
                    explanation=explanation,
                    retries=attempt,
                    errors=errors,
                )

            # Lỗi
            errors.append(error)
            logger.warning(
                f"SQL failed (attempt {attempt + 1}/{self._max_retries + 1}): {error[:100]}"
            )

            # Nếu còn retry, gửi LLM sửa
            if attempt < self._max_retries:
                corrected = self._correct_sql(current_sql, error, ddl_context)
                if corrected:
                    current_sql = corrected
                    logger.info(f"LLM corrected SQL: {corrected[:100]}...")
                else:
                    break

        # Hết retry
        return CorrectionResult(
            valid=False,
            sql=self._rewriter.rewrite(current_sql),
            original_sql=sql,
            explanation=explanation,
            retries=self._max_retries,
            errors=errors,
        )

    def _execute_sql(
        self, sql: str, limit: int = 100
    ) -> tuple[bool, dict | None, str]:
        """
        Chạy SQL trên DB thật.

        Returns:
            (success, result_dict, error_message)
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(sqlalchemy.text(sql))
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchmany(limit)]

                return True, {"columns": columns, "rows": rows, "row_count": len(rows)}, ""

        except Exception as e:
            error_msg = str(e)
            # Lấy phần error chính
            if "Original error" in error_msg:
                error_msg = error_msg.split("Original error")[0]
            return False, None, error_msg.strip()

    def _correct_sql(
        self, sql: str, error: str, ddl_context: str
    ) -> str | None:
        """Gửi LLM sửa SQL, kèm error classification để guide targeted fix."""
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
            correction_hint = f"\n### LOẠI LỖI: {error_type} ###\n{fix_hint}\n"

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
                f"Column '{col_name}' không tồn tại. "
                f"Kiểm tra lại DATABASE SCHEMA, tìm column tương tự. "
                f"Có thể cần JOIN thêm table khác chứa column này."
            )

        if re.search(r"INVALID OBJECT NAME", error_upper):
            obj_match = re.search(r"Invalid object name '([^']+)'", error, re.IGNORECASE)
            obj_name = obj_match.group(1) if obj_match else "unknown"
            return "INVALID_OBJECT", (
                f"Table '{obj_name}' không tồn tại. "
                f"Kiểm tra lại DATABASE SCHEMA, dùng đúng tên table."
            )

        if re.search(r"ORDER BY.*(VIEW|SUBQUER|INLINE|DERIVED|CTE)", error_upper):
            return "CTE_SYNTAX", (
                "ORDER BY không được phép trong CTE/subquery. "
                "Xóa ORDER BY hoặc thêm TOP N trước ORDER BY."
            )

        if re.search(r"AMBIGUOUS COLUMN", error_upper):
            return "MISSING_JOIN", (
                "Column tồn tại ở nhiều tables. "
                "Thêm table alias (ví dụ: t.ColumnName thay vì ColumnName)."
            )

        if re.search(r"INCORRECT SYNTAX", error_upper):
            return "SYNTAX_ERROR", (
                "Lỗi cú pháp T-SQL. Kiểm tra: "
                "- Dấu phẩy thừa/thiếu "
                "- Keyword sai vị trí "
                "- DECLARE (nên inline giá trị)"
            )

        if re.search(r"CONVERSION|CONVERT|CAST|DATATYPE", error_upper):
            return "TYPE_ERROR", (
                "Lỗi kiểu dữ liệu. Dùng CAST() hoặc CONVERT() để chuyển đổi."
            )

        return "LOGIC_ERROR", "Lỗi logic SQL. Kiểm tra lại JOIN conditions và WHERE clause."

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

