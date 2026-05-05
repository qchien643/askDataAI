"""
Column Pruner - Loại bỏ columns không liên quan trước khi build DDL context.

Inspired by: CHESS Schema Selector, X-Linking SFT.

Khi schema lớn (50+ columns), đưa toàn bộ vào prompt gây:
- Token waste (tốn tiền LLM)
- Confusion (LLM bị phân tâm bởi columns không liên quan)
- Accuracy drop (input quá dài → LLM hallucinate)

Column Pruner giải quyết bằng cách LLM chọn chỉ các columns liên quan.
"""

import logging
from copy import deepcopy
from typing import Any

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


COLUMN_PRUNING_SYSTEM_PROMPT = """Bạn là chuyên gia database schema analysis. Nhiệm vụ: chọn các columns LIÊN QUAN đến câu hỏi.

### QUY TẮC ###
1. Chọn TẤT CẢ columns cần thiết để trả lời câu hỏi
2. LUÔN giữ PRIMARY KEY và FOREIGN KEY columns (cần cho JOIN)
3. Giữ columns có tên/description liên quan đến câu hỏi
4. Loại bỏ columns rõ ràng không liên quan
5. Khi không chắc chắn → GIỮ column (tốt hơn thừa hơn thiếu)

### FORMAT KẾT QUẢ ###
Trả lời JSON:
{
    "selected_columns": {
        "table_name": ["col1", "col2", "col3"],
        "table_name2": ["colA", "colB"]
    }
}
"""


COLUMN_PRUNING_USER_PROMPT = """### CÂU HỎI ###
{question}

### DATABASE SCHEMA ###
{schema_summary}

Hãy chọn các columns cần thiết để trả lời câu hỏi trên.
"""


class ColumnPruner:
    """
    LLM-based column pruning.

    Giảm số columns trong DDL context → LLM tập trung hơn → accuracy tăng.
    """

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def prune(
        self,
        question: str,
        db_schemas: list[dict[str, Any]],
        min_columns: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Prune columns không liên quan.

        Args:
            question: Câu hỏi user.
            db_schemas: Full db_schemas từ SchemaRetriever.
            min_columns: Số columns tối thiểu giữ lại mỗi table.

        Returns:
            Pruned db_schemas (copy, không mutate original).
        """
        if not db_schemas:
            return db_schemas

        # Kiểm tra tổng columns — nếu ít thì skip pruning
        total_cols = sum(
            len(s.get("columns", []))
            for s in db_schemas
        )
        if total_cols <= 15:
            logger.info(
                f"Column pruning skipped: only {total_cols} columns total"
            )
            return db_schemas

        # Build schema summary cho LLM
        schema_summary = self._build_schema_summary(db_schemas)

        # Gọi LLM chọn columns
        user_prompt = COLUMN_PRUNING_USER_PROMPT.format(
            question=question,
            schema_summary=schema_summary,
        )

        result = self._llm.chat_json(
            user_prompt=user_prompt,
            system_prompt=COLUMN_PRUNING_SYSTEM_PROMPT,
        )

        selected = result.get("selected_columns", {})
        if not selected:
            logger.warning("Column pruning returned empty — keeping all columns")
            return db_schemas

        # Apply pruning
        pruned = self._apply_pruning(db_schemas, selected, min_columns)

        # Log stats
        pruned_cols = sum(len(s.get("columns", [])) for s in pruned)
        logger.info(
            f"Column pruning: {total_cols} → {pruned_cols} columns "
            f"({total_cols - pruned_cols} removed)"
        )

        return pruned

    @staticmethod
    def _build_schema_summary(db_schemas: list[dict[str, Any]]) -> str:
        """Build readable schema summary cho LLM."""
        parts = []

        for schema in db_schemas:
            name = schema.get("name", "unknown")
            comment = schema.get("comment", "")
            columns = schema.get("columns", [])

            parts.append(f"\n## Table: {name}")
            if comment:
                parts.append(f"Description: {comment}")

            for col in columns:
                if col.get("type") == "COLUMN":
                    col_name = col.get("name", "")
                    col_type = col.get("data_type", "")
                    col_desc = col.get("comment", "")
                    is_pk = " (PK)" if col.get("is_primary_key") else ""
                    parts.append(
                        f"  - {col_name} {col_type}{is_pk}"
                        + (f" — {col_desc}" if col_desc else "")
                    )
                elif col.get("type") == "FOREIGN_KEY":
                    constraint = col.get("constraint", "")
                    parts.append(f"  - FK: {constraint}")

        return "\n".join(parts)

    @staticmethod
    def _apply_pruning(
        db_schemas: list[dict[str, Any]],
        selected: dict[str, list[str]],
        min_columns: int,
    ) -> list[dict[str, Any]]:
        """Apply column selection, giữ PKs và FKs."""
        pruned = []

        for schema in db_schemas:
            schema_copy = deepcopy(schema)
            name = schema_copy.get("name", "")
            columns = schema_copy.get("columns", [])

            if name not in selected:
                # Table không được chọn column nào → giữ nguyên tất cả
                # (table đã qua retrieval nên relevant)
                pruned.append(schema_copy)
                continue

            selected_names = set(selected[name])

            # Filter columns, nhưng LUÔN giữ PK và FK
            filtered = []
            for col in columns:
                col_type = col.get("type", "")
                col_name = col.get("name", "")

                if col_type == "FOREIGN_KEY":
                    # Luôn giữ FK
                    filtered.append(col)
                elif col.get("is_primary_key"):
                    # Luôn giữ PK
                    filtered.append(col)
                elif col_name in selected_names:
                    # Được LLM chọn
                    filtered.append(col)
                # else: bị pruned

            # Đảm bảo min_columns
            if len(filtered) < min_columns and len(columns) >= min_columns:
                # Thêm columns chưa có cho đến min
                for col in columns:
                    if col not in filtered:
                        filtered.append(col)
                    if len(filtered) >= min_columns:
                        break

            schema_copy["columns"] = filtered
            pruned.append(schema_copy)

        return pruned
