"""
Schema Explorer — Answer schema questions from the manifest.

When intent = SCHEMA_EXPLORE, answer directly without generating SQL.

Inspired by WrenAI "Database Schema Exploration":
- "What tables do I have?"
- "Explain the customer table to me."
- "How many tables do I have?"
- "What can I ask?"
"""

import logging
import re
from dataclasses import dataclass

from askdataai.modeling.mdl_schema import Manifest

logger = logging.getLogger(__name__)


@dataclass
class SchemaAnswer:
    """A schema question answer."""
    answer: str
    tables_mentioned: list[str]
    answer_type: str  # "table_list" | "table_detail" | "relationship" | "suggestion"


class SchemaExplorer:
    """
    Answer schema questions from the manifest (no SQL needed).

    Usage:
        explorer = SchemaExplorer(manifest)
        answer = explorer.explore("What tables are there?")
    """

    def __init__(self, manifest: Manifest):
        self._manifest = manifest

    def explore(self, question: str) -> SchemaAnswer:
        """
        Answer a schema question.

        Dispatches to the appropriate handler based on question content.
        """
        q = question.lower().strip()

        # Table list question
        if self._is_table_list_query(q):
            return self._list_tables()

        # Single table detail question
        table_name = self._extract_table_name(q)
        if table_name:
            return self._describe_table(table_name)

        # Relationship question
        if self._is_relationship_query(q):
            return self._describe_relationships()

        # "What can I ask?" question
        if self._is_suggestion_query(q):
            return self._suggest_questions()

        # Default: list tables + suggestions
        return self._list_tables()

    def _is_table_list_query(self, q: str) -> bool:
        patterns = [
            r"(list.*tables?|what.*tables?|which.*tables?|show.*tables?)",
            r"(how\\s*many\\s*tables?|tables?\\s*count)",
            r"(what.*data|schema|database.*have)",
            r"(c\\u00f3.*b\\u1ea3ng|b\\u1ea3ng.*n\\u00e0o)",
        ]
        return any(re.search(p, q, re.IGNORECASE) for p in patterns)

    def _is_relationship_query(self, q: str) -> bool:
        patterns = [
            r"(relationship|foreign\\s*key|join|how.*related|how.*connected)",
            r"(m\\u1ed1i.*quan\\s*h\\u1ec7|li\\u00ean.*k\\u1ebft|k\\u1ebft.*n\\u1ed1i)",
        ]
        return any(re.search(p, q, re.IGNORECASE) for p in patterns)

    def _is_suggestion_query(self, q: str) -> bool:
        patterns = [
            r"(what\\s*can\\s*i\\s*ask|suggest|recommend|example.*question)",
            r"(how.*use|what.*ask|sample.*question)",
        ]
        return any(re.search(p, q, re.IGNORECASE) for p in patterns)

    def _extract_table_name(self, q: str) -> str | None:
        """Find a specific table name in the question."""
        # Pattern: "table customers", "describe DimCustomer", "explain customers table"
        patterns = [
            r"(?:table|describe|explain|about|show)\\s+(\\w+)",
            r"(\\w+)\\s+(?:table|columns?)\\s+(?:have|contain|include|with)",
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

        # Also check if any model name appears directly in the question
        for model in self._manifest.models:
            if model.name.lower() in q:
                return model.name

        return None

    def _list_tables(self) -> SchemaAnswer:
        """List all tables in the manifest."""
        models = self._manifest.models
        table_names = [m.name for m in models]

        lines = [f"📊 **Database has {len(models)} table(s):**\n"]
        for i, model in enumerate(models, 1):
            desc = model.description.strip() if model.description else "No description"
            col_count = len(model.columns)
            lines.append(f"{i}. **{model.name}** ({col_count} columns) — {desc[:80]}")

        if table_names:
            lines.append(f"\n💡 Ask for details about a specific table, e.g.: \"Describe the {table_names[0]} table\"")

        return SchemaAnswer(
            answer="\n".join(lines),
            tables_mentioned=table_names,
            answer_type="table_list",
        )

    def _describe_table(self, table_name: str) -> SchemaAnswer:
        """Describe a single table in detail."""
        model = None
        for m in self._manifest.models:
            if m.name.lower() == table_name.lower():
                model = m
                break

        if not model:
            return SchemaAnswer(
                answer=f"❌ Table '{table_name}' not found in the database.",
                tables_mentioned=[],
                answer_type="table_detail",
            )

        lines = [f"📋 **Table: {model.name}**"]
        if model.description:
            lines.append(f"📝 Description: {model.description.strip()}")
        if model.table_reference:
            lines.append(f"🗄️ DB Reference: `{model.table_reference}`")
        if model.primary_key:
            lines.append(f"🔑 Primary Key: `{model.primary_key}`")

        lines.append(f"\n**Columns ({len(model.columns)}):**")
        for col in model.columns:
            pk_icon = "🔑 " if col.name == model.primary_key else ""
            desc = f" — {col.description}" if col.description else ""
            display = f" (display: {col.display_name})" if col.display_name else ""
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
        """Describe all relationships."""
        rels = self._manifest.relationships
        if not rels:
            return SchemaAnswer(
                answer="No relationships have been defined yet.",
                tables_mentioned=[],
                answer_type="relationship",
            )

        lines = [f"🔗 **{len(rels)} relationship(s):**\n"]
        tables_mentioned = set()

        for i, rel in enumerate(rels, 1):
            lines.append(
                f"{i}. **{rel.model_from}** → **{rel.model_to}** "
                f"({rel.join_type.value})\n"
                f"   Condition: `{rel.condition}`"
            )
            tables_mentioned.add(rel.model_from)
            tables_mentioned.add(rel.model_to)

        return SchemaAnswer(
            answer="\n".join(lines),
            tables_mentioned=list(tables_mentioned),
            answer_type="relationship",
        )

    def _suggest_questions(self) -> SchemaAnswer:
        """Suggest questions the user can ask."""
        models = self._manifest.models
        suggestions = [
            "💡 **Some questions you can ask:**\n",
        ]

        for model in models[:5]:
            name = model.name
            # Suggest based on columns
            numeric_cols = [c for c in model.columns if "int" in c.type.lower() or "decimal" in c.type.lower() or "money" in c.type.lower()]
            date_cols = [c for c in model.columns if "date" in c.type.lower()]

            if numeric_cols:
                col = numeric_cols[0]
                suggestions.append(f"• \"Total {col.display_name or col.name} by {name}\"")
            if date_cols:
                suggestions.append(f"• \"Trend of {name} by month\"")

            suggestions.append(f"• \"Top 5 {name} by ...\"")

        suggestions.append(f"\n📊 Database has {len(models)} table(s). Ask \"What tables are there?\" to see details.")

        return SchemaAnswer(
            answer="\n".join(suggestions),
            tables_mentioned=[m.name for m in models[:5]],
            answer_type="suggestion",
        )
