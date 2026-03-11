"""
ContextBuilder - Build DDL context string cho LLM.

Tương đương build_table_ddl() + construct_retrieval_results()
trong WrenAI gốc (wren-ai-service/src/pipelines/common.py).

Tạo CREATE TABLE DDL dùng MODEL NAMES (không dùng table_reference).
LLM sinh SQL với model names → Phase 5 SQL Rewriter convert → DB names.

Output example:
    /* {"alias": "customers", "description": "Thông tin khách hàng..."} */
    CREATE TABLE customers (
      -- {"alias": "Mã khách hàng", "description": "Mã KH (PK)"}
      CustomerKey INTEGER PRIMARY KEY,
      -- {"alias": "Tên", "description": "Tên khách hàng"}
      FirstName VARCHAR,
      FOREIGN KEY (GeographyKey) REFERENCES geography(GeographyKey)
    );
"""

import logging
from typing import Any

from src.modeling.mdl_schema import Manifest, Model

logger = logging.getLogger(__name__)

# Map types gọn lại cho DDL
TYPE_MAP = {
    "integer": "INTEGER",
    "string": "VARCHAR",
    "decimal": "DECIMAL",
    "date": "DATE",
    "datetime": "DATETIME",
    "boolean": "BOOLEAN",
    "float": "FLOAT",
}


class ContextBuilder:
    """
    Build DDL context từ retrieved db_schemas + manifest.

    DDL dùng MODEL NAMES (không dùng tên DB thật).
    LLM sinh SQL dùng model names → Rewriter (Phase 5) convert.
    """

    def __init__(self, manifest: Manifest):
        self._manifest = manifest

    def build(
        self,
        db_schemas: list[dict[str, Any]],
        model_names: list[str],
    ) -> str:
        """
        Build DDL context string.

        Args:
            db_schemas: Assembled TABLE + TABLE_COLUMNS dicts (từ SchemaRetriever).
            model_names: Tên models cần build DDL (for relationship section).

        Returns:
            DDL string sẵn sàng nhét vào prompt LLM.
        """
        ddl_parts = []

        # Build DDL cho mỗi model schema
        for schema in db_schemas:
            ddl = self._build_table_ddl(schema, model_names_set=set(model_names))
            if ddl:
                ddl_parts.append(ddl)

        # Thêm relationships section
        rel_section = self._build_relationships_section(model_names)
        if rel_section:
            ddl_parts.append(rel_section)

        return "\n\n".join(ddl_parts)

    def build_from_models(self, model_names: list[str]) -> str:
        """
        Build DDL trực tiếp từ manifest models (không cần db_schemas).
        Dùng khi muốn skip vector search, build DDL cho models đã biết.
        """
        ddl_parts = []

        for name in model_names:
            model = self._manifest.get_model(name)
            if not model:
                continue
            ddl = self._build_model_ddl(model, model_names_set=set(model_names))
            ddl_parts.append(ddl)

        rel_section = self._build_relationships_section(model_names)
        if rel_section:
            ddl_parts.append(rel_section)

        return "\n\n".join(ddl_parts)

    def _build_table_ddl(
        self,
        schema: dict[str, Any],
        model_names_set: set[str],
    ) -> str | None:
        """
        Build 1 CREATE TABLE DDL từ schema dict.

        Giống build_table_ddl() trong WrenAI gốc:
        - Dùng schema['name'] (model name) trong CREATE TABLE
        - Column comment chứa alias + description
        """
        if "type" not in schema or "name" not in schema:
            return None

        name = schema["name"]
        comment = schema.get("comment", "")
        columns = schema.get("columns", [])

        columns_ddl = []
        for col in columns:
            if col.get("type") == "COLUMN":
                col_ddl = self._column_to_ddl(col)
                columns_ddl.append(col_ddl)
            elif col.get("type") == "FOREIGN_KEY":
                # Chỉ include FK nếu cả 2 tables đều trong context
                fk_tables = col.get("tables", [])
                if set(fk_tables).issubset(model_names_set):
                    fk_comment = col.get("comment", "")
                    fk_constraint = col.get("constraint", "")
                    columns_ddl.append(f"{fk_comment}{fk_constraint}")

        if not columns_ddl:
            return None

        body = ",\n  ".join(columns_ddl)
        return f"{comment}CREATE TABLE {name} (\n  {body}\n);"

    def _build_model_ddl(
        self,
        model: Model,
        model_names_set: set[str],
    ) -> str:
        """Build DDL trực tiếp từ Model object (không qua db_schemas)."""
        # Table comment
        props = {
            "alias": model.name,
            "description": model.description.strip() if model.description else "",
        }
        comment = f'\n/* {props} */\n'

        # Columns
        columns_ddl = []
        for col in model.columns:
            col_props = {}
            if col.display_name:
                col_props["alias"] = col.display_name
            if col.description:
                col_props["description"] = col.description

            col_comment = f"-- {col_props}\n  " if col_props else ""
            data_type = TYPE_MAP.get(col.type.lower(), col.type.upper())
            pk = " PRIMARY KEY" if col.name == model.primary_key else ""
            columns_ddl.append(f"{col_comment}{col.name} {data_type}{pk}")

        # FK constraints
        rels = self._manifest.get_relationships_for(model.name)
        for rel in rels:
            fk_tables = {rel.model_from, rel.model_to}
            if fk_tables.issubset(model_names_set):
                parts = rel.condition.split(" = ")
                if len(parts) == 2:
                    is_from = model.name == rel.model_from
                    fk_col = parts[0 if is_from else 1].strip().split(".")[-1]
                    ref_table = rel.model_to if is_from else rel.model_from
                    ref_model = self._manifest.get_model(ref_table)
                    ref_pk = ref_model.primary_key if ref_model else ""
                    fk_comment = f'-- {{"condition": "{rel.condition}", "joinType": "{rel.join_type.value}"}}\n  '
                    columns_ddl.append(
                        f"{fk_comment}FOREIGN KEY ({fk_col}) REFERENCES {ref_table}({ref_pk})"
                    )

        body = ",\n  ".join(columns_ddl)
        return f"{comment}CREATE TABLE {model.name} (\n  {body}\n);"

    @staticmethod
    def _column_to_ddl(col: dict) -> str:
        """Convert column dict → DDL line."""
        comment = col.get("comment", "")
        name = col.get("name", "")
        display_name = col.get("display_name", name)
        data_type = TYPE_MAP.get(
            col.get("data_type", "string").lower(),
            col.get("data_type", "VARCHAR").upper(),
        )
        pk = " PRIMARY KEY" if col.get("is_primary_key") else ""

        return f"{comment}{name} {data_type}{pk}"

    def _build_relationships_section(self, model_names: list[str]) -> str:
        """Build -- Relationships section."""
        lines = []
        model_set = set(model_names)

        for rel in self._manifest.relationships:
            if rel.model_from in model_set and rel.model_to in model_set:
                lines.append(
                    f"-- {rel.condition} ({rel.join_type.value})"
                )

        if lines:
            return "-- Relationships:\n" + "\n".join(lines)
        return ""
