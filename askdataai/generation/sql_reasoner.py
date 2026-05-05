"""
SQL Reasoner - Chain-of-Thought reasoning before SQL generation.

Inspired by: SQL-of-Thought, STaR-SQL, DIN-SQL.

LLM analyzes the question → outputs a reasoning plan:
- Reasoning steps (logical steps)
- Tables/columns needed
- Aggregations, filters, ordering

This plan is injected into the SQL generation prompt to help the LLM produce better SQL.
"""

import logging
import re
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ReasoningResult:
    """Result of a reasoning step."""
    steps: list[str]              # Logical steps
    tables_needed: list[str]      # Tables to use
    columns_needed: list[str]     # Columns to use
    aggregations: list[str]       # SUM, COUNT, AVG, etc.
    filters: list[str]            # WHERE conditions
    ordering: str = ""            # ASC/DESC
    grouping: list[str] = field(default_factory=list)
    reasoning_text: str = ""      # Full reasoning text for prompt injection


REASONING_SYSTEM_PROMPT = """You are a data query analysis expert. Your task is to analyze a natural language question and create a detailed query plan.

### RULES ###
1. Break down the question into clear logical steps
2. Identify the exact tables and columns needed from the schema
3. Identify aggregations (SUM, COUNT, AVG, MAX, MIN), filters (WHERE), grouping (GROUP BY), ordering (ORDER BY)
4. ONLY use tables/columns present in the schema
5. Think about JOIN conditions between tables

### DATABASE SCHEMA ###
{ddl_context}

### OUTPUT FORMAT (JSON) ###
{{
    "steps": [
        "Step 1: ...",
        "Step 2: ...",
        "Step 3: ..."
    ],
    "tables_needed": ["table1", "table2"],
    "columns_needed": ["table1.col1", "table2.col2"],
    "aggregations": ["SUM(table1.col1)"],
    "filters": ["table1.col2 = 'value'"],
    "grouping": ["table2.col3"],
    "ordering": "DESC"
}}
"""


REASONING_USER_PROMPT = """### QUESTION ###
{question}

Analyze the question above and create a detailed query plan.
"""


class SQLReasoner:
    """
    Chain-of-Thought reasoning before SQL generation.

    Analyzes the question → reasoning plan → injects into generation prompt.
    """

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def reason(
        self,
        question: str,
        ddl_context: str,
    ) -> ReasoningResult:
        """
        Analyze the question and create a reasoning plan.

        Args:
            question: User question.
            ddl_context: DDL context from schema retrieval.

        Returns:
            ReasoningResult with reasoning plan.
        """
        system_prompt = REASONING_SYSTEM_PROMPT.format(
            ddl_context=ddl_context,
        )
        user_prompt = REASONING_USER_PROMPT.format(
            question=question,
        )

        result = self._llm.chat_json(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        )

        steps = result.get("steps", [])
        tables = result.get("tables_needed", [])
        columns = result.get("columns_needed", [])
        aggregations = result.get("aggregations", [])
        filters = result.get("filters", [])
        grouping = result.get("grouping", [])
        ordering = result.get("ordering", "")

        # Build reasoning text to inject into SQL generation prompt
        reasoning_text = self._build_reasoning_text(
            steps, tables, columns, aggregations, filters, grouping, ordering
        )

        logger.info(
            f"Reasoning: {len(steps)} steps, "
            f"{len(tables)} tables, {len(columns)} columns"
        )

        return ReasoningResult(
            steps=steps,
            tables_needed=tables,
            columns_needed=columns,
            aggregations=aggregations,
            filters=filters,
            ordering=ordering,
            grouping=grouping,
            reasoning_text=reasoning_text,
        )

    @staticmethod
    def _build_reasoning_text(
        steps: list[str],
        tables: list[str],
        columns: list[str],
        aggregations: list[str],
        filters: list[str],
        grouping: list[str],
        ordering: str,
    ) -> str:
        """Build reasoning text in readable form for prompt injection."""
        parts = []

        if steps:
            parts.append("### QUERY PLAN ###")
            for step in steps:
                parts.append(f"- {step}")

        if tables:
            parts.append(f"\nTables needed: {', '.join(tables)}")

        if columns:
            parts.append(f"Columns needed: {', '.join(columns)}")

        if aggregations:
            parts.append(f"Aggregations: {', '.join(aggregations)}")

        if filters:
            parts.append(f"Filters: {', '.join(filters)}")

        if grouping:
            parts.append(f"Group by: {', '.join(grouping)}")

        if ordering:
            parts.append(f"Order: {ordering}")

        return "\n".join(parts)

    def reason_stream(
        self,
        question: str,
        ddl_context: str,
        on_token: Callable[[str], None] | None = None,
    ) -> "ReasoningResult":
        """
        Stream CoT reasoning tokens in real-time via on_token callback.

        Uses text-format prompt (not JSON) to enable token streaming.
        After streaming completes, parses structured fields from accumulated text.

        Args:
            question: User question.
            ddl_context: DDL context from schema retrieval.
            on_token: Callback(chunk) — called for each token received.

        Returns:
            ReasoningResult with full reasoning_text.
        """
        system_prompt = (
            "You are a SQL Server data query analysis expert. "
            "Your task: analyze the question and create a detailed query plan.\n\n"
            "RULES:\n"
            "- Break down into clear logical steps\n"
            "- Identify tables and columns needed from the schema\n"
            "- Identify aggregations (SUM, COUNT, AVG), filters, GROUP BY, ORDER BY\n"
            "- ONLY use tables/columns present in DATABASE SCHEMA below\n\n"
            f"DATABASE SCHEMA:\n{ddl_context}\n\n"
            "FORMAT: Respond in plain text, structured as:\n"
            "ANALYSIS STEPS:\n"
            "1. [step 1 description]\n"
            "2. [step 2 description]\n"
            "...\n\n"
            "TABLES NEEDED: [list]\n"
            "COLUMNS NEEDED: [list]\n"
            "AGGREGATIONS: [list if any]\n"
            "FILTERS: [WHERE conditions if any]\n"
            "GROUP BY: [if any]\n"
            "ORDER BY: [if any]"
        )
        user_prompt = f"### QUESTION ###\n{question}\n\nAnalyze the question and create a query plan."

        # Stream tokens
        full_text = ""
        for chunk in self._llm.chat_stream(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        ):
            full_text += chunk
            if on_token:
                on_token(chunk)

        # Parse structured fields from accumulated text
        steps = self._extract_list_section(full_text, "ANALYSIS STEPS")
        tables = self._extract_inline_list(full_text, "TABLES NEEDED")
        columns = self._extract_inline_list(full_text, "COLUMNS NEEDED")
        aggregations = self._extract_inline_list(full_text, "AGGREGATIONS")
        filters = self._extract_inline_list(full_text, "FILTERS")
        grouping = self._extract_inline_list(full_text, "GROUP BY")
        ordering_parts = self._extract_inline_list(full_text, "ORDER BY")
        ordering = ", ".join(ordering_parts) if ordering_parts else ""

        logger.info(
            f"CoT stream: {len(steps)} steps, {len(full_text)} chars"
        )

        return ReasoningResult(
            steps=steps if steps else [full_text[:200]],
            tables_needed=tables,
            columns_needed=columns,
            aggregations=aggregations,
            filters=filters,
            ordering=ordering,
            grouping=grouping,
            reasoning_text=full_text,
        )

    @staticmethod
    def _extract_list_section(text: str, header: str) -> list[str]:
        """Extract numbered list items after a header."""
        pattern = rf"{re.escape(header)}[:\s]*([\s\S]*?)(?:\n[A-Z][^\n]*:|$)"
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return []
        block = m.group(1).strip()
        items = re.findall(r"^\s*\d+\.\s*(.+)", block, re.MULTILINE)
        return [i.strip() for i in items if i.strip()]

    @staticmethod
    def _extract_inline_list(text: str, header: str) -> list[str]:
        """Extract comma-separated items after 'HEADER: ...' pattern."""
        pattern = rf"{re.escape(header)}[:\s]*([^\n]+)"
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return []
        raw = m.group(1).strip()
        if raw.lower() in ("none", "n/a", "-", ""):
            return []
        return [x.strip() for x in raw.split(",") if x.strip()]
