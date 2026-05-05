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

from askdataai.modeling.mdl_schema import Manifest, Model

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

    # ─── M-Schema format (Sprint 2 — XiYan-SQL inspired) ─────────────────

    def build_for_llm(
        self,
        db_schemas: list[dict[str, Any]],
        model_names: list[str],
        enable_mschema: bool | None = None,
    ) -> str:
        """Smart dispatch: M-Schema if enabled, else legacy DDL.

        Centralized switch so callers (ask_pipeline) don't branch on settings.
        Per-request override via `enable_mschema` parameter; falls back to
        `settings.enable_mschema` when None.
        """
        if enable_mschema is None:
            from askdataai.config import settings  # late import to avoid cycle
            enable_mschema = getattr(settings, "enable_mschema", False)

        if enable_mschema:
            return self.build_mschema(model_names)
        return self.build(db_schemas, model_names)

    def build_mschema(self, model_names: list[str]) -> str:
        """Build M-Schema format string from manifest column metadata.

        Format example:
            # Database Schema (M-Schema)

            # Table: customers
            [Description]: Individual customer information...
            [Fields]:
              CustomerKey: INTEGER, PK, examples: [11000, 11001, 11002]
              YearlyIncome: DECIMAL, range: [10000, 170000], desc: "Annual income (USD)"
              Gender: STRING, enum: ["M", "F"], desc: "Gender code"
              GeographyKey: INTEGER, FK -> geography.GeographyKey

            [Relationships]:
              customers.GeographyKey -> geography.GeographyKey (MANY_TO_ONE)
        """
        if not model_names:
            return ""

        names_set = set(model_names)
        lines: list[str] = ["# Database Schema (M-Schema)\n"]
        included: set[str] = set()

        for name in model_names:
            model = self._manifest.get_model(name)
            if not model:
                continue
            included.add(model.name)

            lines.append(f"# Table: {model.name}")
            if model.description:
                desc = model.description.strip()
                lines.append(f"[Description]: {desc}")
            lines.append("[Fields]:")
            for col in model.columns:
                lines.append(self._format_mschema_column(model, col, names_set))
            lines.append("")  # blank line between tables

        # Relationships section — only between included models
        rel_lines: list[str] = []
        for rel in self._manifest.relationships:
            if rel.model_from in included and rel.model_to in included:
                rel_lines.append(
                    f"  {rel.condition} ({rel.join_type.value})"
                )
        if rel_lines:
            lines.append("[Relationships]:")
            lines.extend(rel_lines)

        return "\n".join(lines)

    def _format_mschema_column(
        self,
        model: Model,
        col,
        names_set: set[str],
    ) -> str:
        """Format one column as a single M-Schema line."""
        data_type = TYPE_MAP.get(col.type.lower(), col.type.upper())
        line = f"  {col.name}: {data_type}"

        # PK marker
        if col.name == model.primary_key:
            line += ", PK"

        # FK — prefer inline `foreign_key` field, fallback to manifest relationships
        fk_ref = self._lookup_fk(model, col, names_set)
        if fk_ref:
            line += f", FK -> {fk_ref}"

        # Display name (skip if same as raw name)
        if col.display_name and col.display_name != col.name:
            line += f", display: {col.display_name!r}"

        # Description (often the most signal-rich field)
        if col.description:
            line += f", desc: {col.description!r}"

        # Examples (preferred over enum if both present, since examples can include enum)
        if col.examples:
            ex_preview = ", ".join(repr(s) for s in col.examples[:3])
            line += f", examples: [{ex_preview}]"
        elif col.enum_values:
            enum_preview = ", ".join(repr(s) for s in col.enum_values[:5])
            line += f", enum: [{enum_preview}]"

        # Range for numeric/date columns
        if col.range and len(col.range) == 2:
            line += f", range: [{col.range[0]} - {col.range[1]}]"

        return line

    def _lookup_fk(self, model: Model, col, names_set: set[str]) -> str | None:
        """Find FK reference for a column.

        Priority:
          1. Inline `col.foreign_key` field (Sprint 1.5 enriched YAML)
          2. Scan manifest relationships matching col.name
        Returns None if not an FK or referenced table not in scope.
        """
        # Path 1: inline annotation
        if col.foreign_key:
            target = col.foreign_key.split(".")[0] if "." in col.foreign_key else None
            if target and target in names_set:
                return col.foreign_key
            return None

        # Path 2: derive from relationships
        for rel in self._manifest.get_relationships_for(model.name):
            # Parse condition: "model_a.col_a = model_b.col_b"
            parts = [p.strip() for p in rel.condition.split("=")]
            if len(parts) != 2:
                continue
            for side in parts:
                if side.startswith(f"{model.name}.") and side.endswith(f".{col.name}"):
                    other = parts[1] if side == parts[0] else parts[0]
                    target_table = other.split(".")[0] if "." in other else None
                    if target_table and target_table in names_set:
                        return other  # full "table.col"
        return None

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
            if col.has_enum:
                col_props["enum_values"] = col.enum_values  # ← inject enum context

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

        # Inject enum values into the comment if present
        enum_vals = col.get("enum_values", [])
        if enum_vals and not comment:
            vals_str = ", ".join(f"'{v}'" for v in enum_vals)
            comment = f'-- {{"enum_values": [{vals_str}]}}\n  '
        elif enum_vals and comment:
            # Append enum info to existing comment
            vals_str = ", ".join(f"'{v}'" for v in enum_vals)
            comment = comment.rstrip() + f' enum_values: [{vals_str}] -->\n  '

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
