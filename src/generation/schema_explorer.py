"""
Schema Explorer — Trả lời câu hỏi về schema từ manifest.

Khi intent = SCHEMA_EXPLORE, trả lời trực tiếp không cần generate SQL.

Lấy ý tưởng từ WrenAI "Database Schema Exploration":
- "What tables do I have?"
- "Explain the customer table to me."
- "How many tables do I have?"
- "What can I ask?"
"""

import logging
import re
from dataclasses import dataclass

from src.modeling.mdl_schema import Manifest

logger = logging.getLogger(__name__)


@dataclass
class SchemaAnswer:
    """Câu trả lời về schema."""
    answer: str
    tables_mentioned: list[str]
    answer_type: str  # "table_list" | "table_detail" | "relationship" | "suggestion"


class SchemaExplorer:
    """
    Trả lời câu hỏi về schema từ manifest (không cần SQL).

    Usage:
        explorer = SchemaExplorer(manifest)
        answer = explorer.explore("có những bảng nào?")
    """

    def __init__(self, manifest: Manifest):
        self._manifest = manifest

    def explore(self, question: str) -> SchemaAnswer:
        """
        Trả lời câu hỏi schema.

        Dispatch tới handler phù hợp dựa trên nội dung câu hỏi.
        """
        q = question.lower().strip()

        # Hỏi danh sách bảng
        if self._is_table_list_query(q):
            return self._list_tables()

        # Hỏi chi tiết 1 bảng cụ thể
        table_name = self._extract_table_name(q)
        if table_name:
            return self._describe_table(table_name)

        # Hỏi về relationship
        if self._is_relationship_query(q):
            return self._describe_relationships()

        # Hỏi "tôi có thể hỏi gì?"
        if self._is_suggestion_query(q):
            return self._suggest_questions()

        # Default: list tables + gợi ý
        return self._list_tables()

    def _is_table_list_query(self, q: str) -> bool:
        patterns = [
            r"(có\s*những?\s*bảng\s*nào|bảng\s*nào|list.*table|what.*table)",
            r"(bao\s*nhiêu\s*bảng|how\s*many\s*table|tables?\s*count)",
            r"(dữ\s*liệu\s*gì|data.*have|schema)",
        ]
        return any(re.search(p, q, re.IGNORECASE) for p in patterns)

    def _is_relationship_query(self, q: str) -> bool:
        patterns = [
            r"(mối\s*quan\s*hệ|relationship|liên\s*kết|foreign\s*key|join)",
            r"(kết\s*nối|connected|related)",
        ]
        return any(re.search(p, q, re.IGNORECASE) for p in patterns)

    def _is_suggestion_query(self, q: str) -> bool:
        patterns = [
            r"(tôi\s*có\s*thể\s*hỏi\s*gì|what\s*can\s*i\s*ask)",
            r"(gợi\s*ý|suggest|recommend|ví\s*dụ\s*câu\s*hỏi)",
            r"(hỏi\s*gì\s*được|câu\s*hỏi\s*mẫu)",
        ]
        return any(re.search(p, q, re.IGNORECASE) for p in patterns)

    def _extract_table_name(self, q: str) -> str | None:
        """Tìm tên bảng cụ thể trong câu hỏi."""
        # Pattern: "bảng customers", "table DimCustomer", "mô tả bảng X"
        patterns = [
            r"(?:bảng|table|mô\s*tả|describe|explain)\s+(\w+)",
            r"(\w+)\s+(?:table|bảng)\s+(?:có|gồm|chứa|contains?)",
        ]
        for p in patterns:
            match = re.search(p, q, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Verify name exists in manifest
                for model in self._manifest.models:
                    if model.name.lower() == name.lower():
                        return model.name
                return None

        # Also check if any model name appears in the question
        for model in self._manifest.models:
            if model.name.lower() in q:
                return model.name

        return None

    def _list_tables(self) -> SchemaAnswer:
        """List tất cả bảng trong manifest."""
        models = self._manifest.models
        table_names = [m.name for m in models]

        lines = [f"📊 **Database có {len(models)} bảng:**\n"]
        for i, model in enumerate(models, 1):
            desc = model.description.strip() if model.description else "Chưa có mô tả"
            col_count = len(model.columns)
            lines.append(f"{i}. **{model.name}** ({col_count} cột) — {desc[:80]}")

        lines.append(f"\n💡 Hãy hỏi chi tiết về bảng cụ thể, ví dụ: \"Mô tả bảng {table_names[0]}\"")

        return SchemaAnswer(
            answer="\n".join(lines),
            tables_mentioned=table_names,
            answer_type="table_list",
        )

    def _describe_table(self, table_name: str) -> SchemaAnswer:
        """Mô tả chi tiết 1 bảng."""
        model = None
        for m in self._manifest.models:
            if m.name.lower() == table_name.lower():
                model = m
                break

        if not model:
            return SchemaAnswer(
                answer=f"❌ Không tìm thấy bảng '{table_name}' trong database.",
                tables_mentioned=[],
                answer_type="table_detail",
            )

        lines = [f"📋 **Bảng: {model.name}**"]
        if model.description:
            lines.append(f"📝 Mô tả: {model.description.strip()}")
        if model.table_reference:
            lines.append(f"🗄️ DB Reference: `{model.table_reference}`")
        if model.primary_key:
            lines.append(f"🔑 Primary Key: `{model.primary_key}`")

        lines.append(f"\n**Columns ({len(model.columns)}):**")
        for col in model.columns:
            pk_icon = "🔑 " if col.name == model.primary_key else ""
            desc = f" — {col.description}" if col.description else ""
            display = f" (hiển thị: {col.display_name})" if col.display_name else ""
            lines.append(f"  • {pk_icon}`{col.name}` ({col.type}){display}{desc}")

        # Show relationships
        rels = self._manifest.get_relationships_for(model.name)
        if rels:
            lines.append(f"\n**Relationships ({len(rels)}):**")
            for rel in rels:
                other = rel.model_to if rel.model_from == model.name else rel.model_from
                lines.append(f"  • → {other} ({rel.join_type.value}): `{rel.condition}`")

        return SchemaAnswer(
            answer="\n".join(lines),
            tables_mentioned=[model.name],
            answer_type="table_detail",
        )

    def _describe_relationships(self) -> SchemaAnswer:
        """Mô tả tất cả relationships."""
        rels = self._manifest.relationships
        if not rels:
            return SchemaAnswer(
                answer="Chưa có mối quan hệ nào được định nghĩa.",
                tables_mentioned=[],
                answer_type="relationship",
            )

        lines = [f"🔗 **{len(rels)} mối quan hệ:**\n"]
        tables_mentioned = set()

        for i, rel in enumerate(rels, 1):
            lines.append(
                f"{i}. **{rel.model_from}** → **{rel.model_to}** "
                f"({rel.join_type.value})\n"
                f"   Điều kiện: `{rel.condition}`"
            )
            tables_mentioned.add(rel.model_from)
            tables_mentioned.add(rel.model_to)

        return SchemaAnswer(
            answer="\n".join(lines),
            tables_mentioned=list(tables_mentioned),
            answer_type="relationship",
        )

    def _suggest_questions(self) -> SchemaAnswer:
        """Gợi ý câu hỏi có thể hỏi."""
        models = self._manifest.models
        suggestions = [
            "💡 **Một số câu hỏi bạn có thể hỏi:**\n",
        ]

        for model in models[:5]:
            name = model.name
            # Gợi ý dựa trên columns
            numeric_cols = [c for c in model.columns if "int" in c.type.lower() or "decimal" in c.type.lower() or "money" in c.type.lower()]
            date_cols = [c for c in model.columns if "date" in c.type.lower()]

            if numeric_cols:
                col = numeric_cols[0]
                suggestions.append(f"• \"Tổng {col.display_name or col.name} theo {name}\"")
            if date_cols:
                suggestions.append(f"• \"Xu hướng {name} theo tháng\"")

            suggestions.append(f"• \"Top 5 {name} theo ...\"")

        suggestions.append(f"\n📊 Database có {len(models)} bảng. Hỏi \"có những bảng nào?\" để xem chi tiết.")

        return SchemaAnswer(
            answer="\n".join(suggestions),
            tables_mentioned=[m.name for m in models[:5]],
            answer_type="suggestion",
        )
