"""
SQL Generator - Generate SQL from question + DDL context.

System prompt optimized for T-SQL (SQL Server):
- TOP instead of LIMIT
- GETDATE() instead of NOW()
- ISNULL instead of COALESCE
- Anti-hallucination rules

Equivalent to SQLGeneration in WrenAI
(wren-ai-service/src/pipelines/generation/sql_generation.py).
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class SQLGenerationResult:
    sql: str
    explanation: str = ""
    raw_response: dict | None = None


SQL_GENERATION_SYSTEM_PROMPT = """You are a T-SQL expert for Microsoft SQL Server. Your task is to generate SQL queries from natural language questions.

### SQL SERVER RULES ###
- Use TOP instead of LIMIT. Example: SELECT TOP 10 * FROM ...
- Use GETDATE() instead of NOW()
- Use ISNULL() instead of COALESCE() when only 2 parameters are needed
- Use CONVERT() or CAST() for type conversion
- String concatenation: use + instead of ||
- Use [name] or "name" for names with special characters
- Date format: use CONVERT(VARCHAR, date_col, format_code) instead of TO_CHAR()
- DO NOT use DECLARE @variable — inline values directly in the query

### ANTI-HALLUCINATION RULES ###
- ONLY use tables and columns present in the DATABASE SCHEMA below
- DO NOT invent table or column names that do not exist
- DO NOT use DELETE, UPDATE, INSERT, DROP or any data-modifying statement
- ONLY use SELECT statements
- Use column aliases (if provided) to understand column semantics

### JOIN RULES ###
- ALWAYS use JOIN when querying multiple tables
- Prefer CTEs (WITH) over subqueries
- Use JOIN conditions from the Relationships section of the schema

### RANKING RULES ###
- For ranking problems (top X, bottom X), use DENSE_RANK() or ROW_NUMBER()
- Include the ranking column in the final SELECT

### STRING COMPARISON RULES ###
- Use LOWER(column) = LOWER(value) for case-insensitive comparisons
- Use LIKE with % for pattern matching

### CRITICAL LOGIC RULES ###
When the question asks for "TOP N <entity> with detail <detail>":
1. CTE step 1: Find TOP N DISTINCT <entity> based on the metric (GROUP BY entity key, ORDER BY metric DESC)
2. Final SELECT: JOIN the CTE result with tables containing <detail> information
3. NEVER DO: SELECT TOP N entity, detail FROM ... GROUP BY entity, detail
   → This returns the SAME entity repeated with different details!

WRONG: SELECT TOP 10 ProductName, City FROM ... GROUP BY ProductName, City
→ Result: 1 product × 10 cities (NOT 10 products!)

CORRECT:
WITH top_products AS (
  SELECT TOP 10 p.ProductKey, p.ProductName, SUM(s.Sales) AS TotalSales
  FROM products p JOIN sales s ON p.ProductKey = s.ProductKey
  GROUP BY p.ProductKey, p.ProductName
  ORDER BY TotalSales DESC
)
SELECT tp.ProductName, tp.TotalSales, g.City
FROM top_products tp
JOIN sales s ON tp.ProductKey = s.ProductKey
JOIN geography g ON s.GeographyKey = g.GeographyKey

### OUTPUT FORMAT ###
Respond as JSON:
{
    "sql": "<T-SQL query>",
    "explanation": "<brief explanation in English>"
}
"""



SQL_GENERATION_USER_PROMPT = """### DATABASE SCHEMA ###
{ddl_context}

### QUESTION ###
{question}

Generate the correct T-SQL query to answer the question above.
"""


class SQLGenerator:
    """Generate SQL from question + DDL context."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def generate(
        self,
        question: str,
        ddl_context: str,
        sql_samples: list[dict] | None = None,
    ) -> SQLGenerationResult:
        """
        Generate SQL query.

        Args:
            question: User question.
            ddl_context: DDL context from Phase 4 ContextBuilder.
            sql_samples: Few-shot SQL examples (optional).

        Returns:
            SQLGenerationResult with sql and explanation.
        """
        user_prompt = SQL_GENERATION_USER_PROMPT.format(
            ddl_context=ddl_context,
            question=question,
        )

        # Append SQL samples if provided
        if sql_samples:
            samples_text = "\n### SQL SAMPLES ###\n"
            for s in sql_samples:
                samples_text += f"Question: {s['question']}\nSQL: {s['sql']}\n\n"
            user_prompt = samples_text + user_prompt

        result = self._llm.chat_json(
            user_prompt=user_prompt,
            system_prompt=SQL_GENERATION_SYSTEM_PROMPT,
        )

        sql = result.get("sql", "")
        explanation = result.get("explanation", "")

        if not sql:
            logger.error(f"No SQL generated: {result}")

        logger.info(f"Generated SQL: {sql[:100]}...")
        return SQLGenerationResult(
            sql=sql,
            explanation=explanation,
            raw_response=result,
        )

    def generate_stream(
        self,
        question: str,
        ddl_context: str,
        on_token: Callable[[str], None] | None = None,
    ) -> SQLGenerationResult:
        """
        Stream SQL generation tokens in real-time via on_token callback.

        Uses text-format prompt (SQL in code fence) to enable token streaming.
        After streaming completes, extracts SQL from ```sql ... ``` block.

        Args:
            question: User question.
            ddl_context: DDL context from schema retrieval.
            on_token: Callback(chunk) — called for each token received.

        Returns:
            SQLGenerationResult with sql and explanation.
        """
        # Text prompt — not using json_object so streaming works
        system_prompt = (
            "You are a T-SQL expert for Microsoft SQL Server.\n\n"
            "SQL SERVER RULES:\n"
            "- Use TOP instead of LIMIT (e.g. SELECT TOP 10 ...)\n"
            "- Use GETDATE() instead of NOW()\n"
            "- Use ISNULL() when only 2 parameters are needed\n"
            "- String concat: use + instead of ||\n"
            "- DO NOT use DELETE/UPDATE/INSERT/DROP — SELECT ONLY\n"
            "- ONLY use tables/columns present in DATABASE SCHEMA below\n"
            "- ALWAYS use JOIN when querying multiple tables\n"
            "- Prefer CTEs (WITH ...) over subqueries\n"
            "- TOP N + detail: use CTE to identify TOP N first, then JOIN to get detail\n\n"
            "RESPONSE FORMAT (required):\n"
            "SQL:\n"
            "```sql\n"
            "<T-SQL query>\n"
            "```\n\n"
            "EXPLANATION: <brief explanation in English>"
        )
        user_prompt = (
            f"### DATABASE SCHEMA ###\n{ddl_context}\n\n"
            f"### QUESTION ###\n{question}\n\n"
            "Generate the correct T-SQL query to answer the question above."
        )

        # Stream tokens
        full_text = ""
        for chunk in self._llm.chat_stream(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        ):
            full_text += chunk
            if on_token:
                on_token(chunk)

        # Extract SQL from ```sql ... ``` code fence
        sql = ""
        sql_match = re.search(r"```(?:sql)?\s*([\s\S]+?)```", full_text, re.IGNORECASE)
        if sql_match:
            sql = sql_match.group(1).strip()
        else:
            # Fallback: look for SELECT ... pattern
            sel_match = re.search(r"((?:WITH|SELECT)[\s\S]+)", full_text, re.IGNORECASE)
            if sel_match:
                sql = sel_match.group(1).strip()

        # Extract explanation
        explanation = ""
        expl_match = re.search(r"EXPLANATION[:\s]+([^\n]+(?:\n(?!SQL:|```)[^\n]+)*)", full_text, re.IGNORECASE)
        if expl_match:
            explanation = expl_match.group(1).strip()

        if not sql:
            logger.error(f"generate_stream: no SQL extracted from streamed text ({len(full_text)} chars)")
        else:
            logger.info(f"generate_stream SQL: {sql[:80]}...")

        return SQLGenerationResult(
            sql=sql,
            explanation=explanation,
            raw_response={"full_text": full_text},
        )
