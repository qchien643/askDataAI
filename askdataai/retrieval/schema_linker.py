"""
Schema Linker - Map entities trong câu hỏi → tables/columns cụ thể.

Inspired by: DIN-SQL (Decomposed Schema Linking), CHESS (Information Retriever),
RSL-SQL (Bidirectional Schema Linking).

Bước này chạy SAU schema retrieval, TRƯỚC column pruning.
LLM phân tích câu hỏi + schema → xác định:
- Entity mentions → table/column mappings
- Value mentions → filter conditions
- Ambiguity flags → cần clarification

Output được dùng để:
1. Enrich context cho SQL generation
2. Guide column pruning (bước sau)
3. Detect ambiguity sớm
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class EntityLink:
    """Một entity link: mention → table.column."""
    mention: str           # Từ/cụm từ trong câu hỏi
    table: str             # Table name
    column: str            # Column name
    confidence: float = 1.0


@dataclass
class ValueLink:
    """Một value link: value mention → filter condition."""
    mention: str           # Giá trị trong câu hỏi (vd: "Hà Nội")
    table: str
    column: str
    value: str             # Giá trị thực (vd: "Ha Noi" hoặc "Hà Nội")
    operator: str = "="    # =, LIKE, >, <, etc.


@dataclass
class SchemaLinkResult:
    """Kết quả schema linking."""
    entity_links: list[EntityLink] = field(default_factory=list)
    value_links: list[ValueLink] = field(default_factory=list)
    linked_tables: list[str] = field(default_factory=list)
    linked_columns: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    context_hints: str = ""  # Text hints để inject vào prompt


SCHEMA_LINKING_SYSTEM_PROMPT = """Bạn là chuyên gia schema linking cho hệ thống Text-to-SQL trên SQL Server.

Nhiệm vụ: Phân tích câu hỏi và liên kết (link) các entities/values trong câu hỏi với tables/columns trong database schema.

### QUY TẮC ###
1. Xác định mỗi entity (khái niệm) trong câu hỏi map tới table/column nào
2. Xác định mỗi value (giá trị cụ thể) trong câu hỏi tương ứng filter condition nào
3. Nếu một entity có thể map tới NHIỀU columns → ghi nhận ambiguity
4. CHỈ dùng tables/columns có trong schema
5. Đưa ra confidence (0.0-1.0) cho mỗi link

### DATABASE SCHEMA ###
{ddl_context}

### FORMAT KẾT QUẢ (JSON) ###
{{
    "entity_links": [
        {{"mention": "doanh thu", "table": "internet_sales", "column": "SalesAmount", "confidence": 0.9}},
        {{"mention": "khách hàng", "table": "customers", "column": "*", "confidence": 1.0}}
    ],
    "value_links": [
        {{"mention": "Hà Nội", "table": "geography", "column": "City", "value": "Hà Nội", "operator": "="}}
    ],
    "ambiguities": [
        "doanh thu có thể là SalesAmount hoặc TotalProductCost"
    ]
}}
"""


SCHEMA_LINKING_USER_PROMPT = """### CÂU HỎI ###
{question}

Hãy liên kết các entities và values trong câu hỏi với database schema.
"""


class SchemaLinker:
    """
    Explicit schema linking: map câu hỏi → schema elements.

    Chạy sau schema retrieval, trước column pruning.
    Output dùng để enrich context và guide pruning.
    """

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def link(
        self,
        question: str,
        ddl_context: str,
    ) -> SchemaLinkResult:
        """
        Link entities/values trong câu hỏi tới schema.

        Args:
            question: Câu hỏi user.
            ddl_context: DDL context từ context builder.

        Returns:
            SchemaLinkResult với entity links, value links, ambiguities.
        """
        system_prompt = SCHEMA_LINKING_SYSTEM_PROMPT.format(
            ddl_context=ddl_context,
        )
        user_prompt = SCHEMA_LINKING_USER_PROMPT.format(
            question=question,
        )

        result = self._llm.chat_json(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
        )

        # Parse entity links
        entity_links = []
        for e in result.get("entity_links", []):
            entity_links.append(EntityLink(
                mention=e.get("mention", ""),
                table=e.get("table", ""),
                column=e.get("column", ""),
                confidence=e.get("confidence", 1.0),
            ))

        # Parse value links
        value_links = []
        for v in result.get("value_links", []):
            value_links.append(ValueLink(
                mention=v.get("mention", ""),
                table=v.get("table", ""),
                column=v.get("column", ""),
                value=v.get("value", ""),
                operator=v.get("operator", "="),
            ))

        # Collect linked tables/columns
        linked_tables = list({e.table for e in entity_links})
        linked_columns = [
            f"{e.table}.{e.column}"
            for e in entity_links
            if e.column != "*"
        ]

        ambiguities = result.get("ambiguities", [])

        # Build context hints
        context_hints = self._build_context_hints(
            entity_links, value_links, ambiguities
        )

        logger.info(
            f"Schema linking: {len(entity_links)} entity links, "
            f"{len(value_links)} value links, "
            f"{len(ambiguities)} ambiguities"
        )

        return SchemaLinkResult(
            entity_links=entity_links,
            value_links=value_links,
            linked_tables=linked_tables,
            linked_columns=linked_columns,
            ambiguities=ambiguities,
            context_hints=context_hints,
        )

    @staticmethod
    def _build_context_hints(
        entity_links: list[EntityLink],
        value_links: list[ValueLink],
        ambiguities: list[str],
    ) -> str:
        """Build context hints text cho SQL generation prompt."""
        parts = []

        if entity_links:
            parts.append("### SCHEMA LINKING ###")
            for e in entity_links:
                if e.column == "*":
                    parts.append(f"- \"{e.mention}\" → table {e.table}")
                else:
                    parts.append(
                        f"- \"{e.mention}\" → {e.table}.{e.column}"
                    )

        if value_links:
            parts.append("\n### VALUE FILTERS ###")
            for v in value_links:
                parts.append(
                    f"- \"{v.mention}\" → {v.table}.{v.column} {v.operator} '{v.value}'"
                )

        if ambiguities:
            parts.append("\n### LƯU Ý ###")
            for a in ambiguities:
                parts.append(f"- ⚠ {a}")

        return "\n".join(parts)
