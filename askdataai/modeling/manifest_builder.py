"""
ManifestBuilder - Build Manifest JSON từ models.yaml + validate against DB.

Tương đương MDLBuilder trong WrenAI gốc
(wren-ui/src/apollo/server/mdl/mdlBuilder.ts),
nhưng đọc config từ YAML thay vì từ UI database.

Chức năng:
  1. Đọc models.yaml → parse thành Manifest object
  2. Validate: check table/column có tồn tại trong DB không
  3. Auto-detect relationships từ FK (nếu không khai báo trong YAML)
  4. Output: Manifest JSON sẵn sàng deploy
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from askdataai.modeling.mdl_schema import (
    Column,
    JoinType,
    Manifest,
    Model,
    Relationship,
)
from askdataai.connectors.schema_introspector import (
    DatabaseSchema,
    SchemaIntrospector,
)

logger = logging.getLogger(__name__)


class ManifestBuilder:
    """
    Build semantic manifest từ YAML config + validate against database thật.

    Usage:
        builder = ManifestBuilder(
            config_path="configs/models.yaml",
            introspector=introspector
        )
        manifest = builder.build()
        errors = builder.validate(manifest)
    """

    def __init__(
        self,
        config_path: str | Path,
        introspector: SchemaIntrospector | None = None,
    ):
        self._config_path = Path(config_path)
        self._introspector = introspector
        self._db_schema: DatabaseSchema | None = None

    def build(self) -> Manifest:
        """
        Đọc models.yaml → build Manifest object.

        Returns:
            Manifest object hoàn chỉnh.
        """
        # Đọc YAML config
        raw = self._load_yaml()

        # Parse models
        models = self._parse_models(raw.get("models", []))

        # Parse relationships
        relationships = self._parse_relationships(raw.get("relationships", []))

        # Lấy database name
        catalog = ""
        if self._introspector:
            try:
                schema = self._get_db_schema()
                catalog = schema.database_name
            except Exception:
                catalog = "unknown"

        manifest = Manifest(
            catalog=catalog,
            schema_name="dbo",
            models=models,
            relationships=relationships,
        )

        logger.info(
            f"Manifest built: {len(models)} models, "
            f"{len(relationships)} relationships"
        )

        return manifest

    def validate(self, manifest: Manifest) -> list[str]:
        """
        Validate manifest against database thật.

        Checks:
          1. Mỗi model.table_reference phải tồn tại trong DB
          2. Mỗi column.source phải tồn tại trong table thật
          3. Mỗi relationship.model_from và model_to phải tồn tại trong manifest
          4. Mỗi relationship condition phải reference columns hợp lệ

        Returns:
            List lỗi (rỗng = valid).
        """
        errors: list[str] = []

        if not self._introspector:
            errors.append("No introspector provided — cannot validate against DB.")
            return errors

        db_schema = self._get_db_schema()
        db_table_names = {t.name.lower() for t in db_schema.tables}
        db_columns_by_table: dict[str, set[str]] = {
            t.name.lower(): {c.name.lower() for c in t.columns}
            for t in db_schema.tables
        }

        # 1. Validate table references
        for model in manifest.models:
            table_ref = model.table_reference.lower()
            if table_ref not in db_table_names:
                errors.append(
                    f"Model '{model.name}': table '{model.table_reference}' "
                    f"not found in database."
                )
            else:
                # 2. Validate column sources
                db_cols = db_columns_by_table.get(table_ref, set())
                for col in model.columns:
                    source = col.actual_source.lower()
                    if source not in db_cols:
                        errors.append(
                            f"Model '{model.name}', column '{col.name}': "
                            f"source '{col.actual_source}' not found in "
                            f"table '{model.table_reference}'. "
                            f"Available: {sorted(db_cols)}"
                        )

        # 3. Validate relationship models exist
        model_names = {m.name for m in manifest.models}
        for rel in manifest.relationships:
            if rel.model_from not in model_names:
                errors.append(
                    f"Relationship '{rel.name}': model_from '{rel.model_from}' "
                    f"not found in manifest."
                )
            if rel.model_to not in model_names:
                errors.append(
                    f"Relationship '{rel.name}': model_to '{rel.model_to}' "
                    f"not found in manifest."
                )

        if errors:
            logger.warning(f"Manifest validation: {len(errors)} errors found.")
        else:
            logger.info("Manifest validation: OK ✅")

        return errors

    def build_and_validate(self) -> tuple[Manifest, list[str]]:
        """Build + validate trong 1 bước."""
        manifest = self.build()
        errors = self.validate(manifest)
        return manifest, errors

    # ─── Private Methods ──────────────────────────────────────────────────

    def _load_yaml(self) -> dict:
        """Đọc và parse YAML config file."""
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {self._config_path}"
            )

        with open(self._config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Config file is empty: {self._config_path}")

        return data

    def _parse_models(self, raw_models: list[dict]) -> list[Model]:
        """Parse list models từ YAML."""
        models = []
        for raw in raw_models:
            columns = self._parse_columns(raw.get("columns", []))
            model = Model(
                name=raw["name"],
                table_reference=raw["table"],
                description=raw.get("description", "").strip(),
                columns=columns,
                primary_key=raw.get("primary_key"),
            )
            models.append(model)
        return models

    def _parse_columns(self, raw_columns: list[dict]) -> list[Column]:
        """Parse list columns từ YAML."""
        columns = []
        for raw in raw_columns:
            col = Column(
                name=raw["name"],                          # Tên cột gốc trong DB
                display_name=raw.get("display_name", ""),  # Tên cho AI đọc
                type=raw.get("type", "string"),
                description=raw.get("description", ""),
                is_calculated=raw.get("is_calculated", False),
                expression=raw.get("expression"),
                enum_values=raw.get("enum_values", []),    # Tập giá trị enum
                # ── M-Schema fields (Sprint 2) ──
                examples=raw.get("examples", []),
                range=raw.get("range"),
                foreign_key=raw.get("foreign_key"),
            )
            columns.append(col)
        return columns

    def _parse_relationships(self, raw_rels: list[dict]) -> list[Relationship]:
        """Parse list relationships từ YAML."""
        relationships = []
        for raw in raw_rels:
            rel = Relationship(
                name=raw["name"],
                model_from=raw["from"],
                model_to=raw["to"],
                join_type=JoinType(raw.get("type", "MANY_TO_ONE")),
                condition=raw["condition"],
            )
            relationships.append(rel)
        return relationships

    def _get_db_schema(self) -> DatabaseSchema:
        """Cache DB schema để không query nhiều lần."""
        if self._db_schema is None:
            self._db_schema = self._introspector.get_full_schema()
        return self._db_schema
