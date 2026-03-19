"""
SQL Reasoner - Chain-of-Thought reasoning trước SQL generation.

Inspired by: SQL-of-Thought, STaR-SQL, DIN-SQL.

LLM phân tích câu hỏi → output reasoning plan:
- Reasoning steps (bước logic)
- Tables/columns cần dùng
- Aggregations, filters, ordering

Plan này inject vào SQL generation prompt → LLM sinh SQL tốt hơn.
"""

import logging
from dataclasses import dataclass, field

from src.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ReasoningResult:
    """Kết quả reasoning step."""
    steps: list[str]              # Các bước logic
    tables_needed: list[str]      # Tables cần dùng
    columns_needed: list[str]     # Columns cần dùng
    aggregations: list[str]       # SUM, COUNT, AVG, etc.
    filters: list[str]            # WHERE conditions
    ordering: str = ""            # ASC/DESC
    grouping: list[str] = field(default_factory=list)
    reasoning_text: str = ""      # Full reasoning text cho prompt injection


REASONING_SYSTEM_PROMPT = """Bạn là chuyên gia phân tích truy vấn dữ liệu. Nhiệm vụ: phân tích câu hỏi tự nhiên và tạo kế hoạch truy vấn chi tiết.

### QUY TẮC ###
1. Phân tích câu hỏi thành các bước logic rõ ràng
2. Xác định chính xác tables và columns cần dùng từ schema
3. Xác định aggregations (SUM, COUNT, AVG, MAX, MIN), filters (WHERE), grouping (GROUP BY), ordering (ORDER BY)
4. CHỈ dùng tables/columns có trong schema
5. Suy nghĩ về JOIN conditions giữa các tables

### DATABASE SCHEMA ###
{ddl_context}

### FORMAT KẾT QUẢ (JSON) ###
{{
    "steps": [
        "Bước 1: ...",
        "Bước 2: ...",
        "Bước 3: ..."
    ],
    "tables_needed": ["table1", "table2"],
    "columns_needed": ["table1.col1", "table2.col2"],
    "aggregations": ["SUM(table1.col1)"],
    "filters": ["table1.col2 = 'value'"],
    "grouping": ["table2.col3"],
    "ordering": "DESC"
}}
"""


REASONING_USER_PROMPT = """### CÂU HỎI ###
{question}

Hãy phân tích câu hỏi trên và tạo kế hoạch truy vấn chi tiết.
"""


class SQLReasoner:
    """
    Chain-of-Thought reasoning trước SQL generation.

    Phân tích câu hỏi → reasoning plan → inject vào generation prompt.
    """

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def reason(
        self,
        question: str,
        ddl_context: str,
    ) -> ReasoningResult:
        """
        Phân tích câu hỏi, tạo reasoning plan.

        Args:
            question: Câu hỏi user.
            ddl_context: DDL context từ schema retrieval.

        Returns:
            ReasoningResult với reasoning plan.
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

        # Build reasoning text để inject vào SQL generation prompt
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
        """Build reasoning text dạng readable cho prompt injection."""
        parts = []

        if steps:
            parts.append("### KẾ HOẠCH TRUY VẤN ###")
            for step in steps:
                parts.append(f"- {step}")

        if tables:
            parts.append(f"\nTables cần dùng: {', '.join(tables)}")

        if columns:
            parts.append(f"Columns cần dùng: {', '.join(columns)}")

        if aggregations:
            parts.append(f"Aggregations: {', '.join(aggregations)}")

        if filters:
            parts.append(f"Filters: {', '.join(filters)}")

        if grouping:
            parts.append(f"Group by: {', '.join(grouping)}")

        if ordering:
            parts.append(f"Order: {ordering}")

        return "\n".join(parts)
