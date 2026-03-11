"""
SchemaRetriever - Tìm models liên quan khi user hỏi.

Tương đương DbSchemaRetrieval pipeline trong WrenAI gốc
(wren-ai-service/src/pipelines/retrieval/db_schema_retrieval.py).

Luồng:
  1. Table Retrieval: search table_descriptions → top-K model names
  2. Relationship Expansion: kéo thêm related models (1-hop)
  3. Schema Retrieval: fetch TABLE + TABLE_COLUMNS docs từ db_schema

Usage:
    retriever = SchemaRetriever(indexer, manifest)
    result = retriever.retrieve("tổng doanh thu theo khách hàng")
    # result.model_names = ["internet_sales", "customers"]
    # result.db_schemas = [{type: TABLE, name: ..., columns: [...]}, ...]
"""

import ast
import logging
from dataclasses import dataclass, field
from typing import Any

from src.indexing.schema_indexer import (
    SchemaIndexer,
    COLLECTION_DB_SCHEMA,
    COLLECTION_TABLE_DESCRIPTIONS,
)
from src.modeling.mdl_schema import Manifest

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Kết quả retrieval."""
    query: str
    model_names: list[str]              # Models tìm được (sau relationship expansion)
    expanded_from: list[str]            # Models gốc từ vector search (trước expansion)
    db_schemas: list[dict[str, Any]]    # Assembled TABLE + TABLE_COLUMNS dicts
    raw_documents: list[dict] = field(default_factory=list)


class SchemaRetriever:
    """
    Tìm models/columns liên quan từ câu hỏi user.

    3 bước giống WrenAI gốc:
    1. table_retrieval: search table_descriptions → top-K table names
    2. relationship_expansion: kéo thêm related models (1-hop)
    3. schema_retrieval: fetch TABLE + TABLE_COLUMNS từ db_schema
    """

    def __init__(
        self,
        indexer: SchemaIndexer,
        manifest: Manifest,
        table_retrieval_size: int = 5,
    ):
        self._indexer = indexer
        self._manifest = manifest
        self._table_retrieval_size = table_retrieval_size

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        expand_relationships: bool = True,
    ) -> RetrievalResult:
        """
        Retrieve schema context cho câu hỏi.

        Args:
            query: Câu hỏi user.
            top_k: Số models tìm (default: table_retrieval_size).
            expand_relationships: Có kéo thêm related models không.

        Returns:
            RetrievalResult với model_names, db_schemas.
        """
        k = top_k or self._table_retrieval_size

        # ── Step 1: Table Retrieval ──
        # Search table_descriptions collection (giống WrenAI table_retrieval)
        table_results = self._indexer.search_descriptions(query, top_k=k)
        original_names = [r["metadata"]["name"] for r in table_results]
        logger.info(f"Table retrieval: {original_names}")

        # ── Step 2: Relationship Expansion ──
        if expand_relationships:
            expanded_names = self._expand_relationships(original_names)
        else:
            expanded_names = list(original_names)

        logger.info(f"After expansion: {expanded_names}")

        # ── Step 3: Schema Retrieval ──
        # Fetch TABLE + TABLE_COLUMNS docs từ db_schema collection
        # (giống WrenAI dbschema_retrieval → construct_db_schemas)
        db_schemas = self._fetch_db_schemas(expanded_names)
        logger.info(f"Retrieved {len(db_schemas)} db_schema dicts")

        return RetrievalResult(
            query=query,
            model_names=expanded_names,
            expanded_from=original_names,
            db_schemas=db_schemas,
            raw_documents=table_results,
        )

    def _expand_relationships(self, model_names: list[str]) -> list[str]:
        """
        Kéo thêm related models (1-hop) từ manifest relationships.

        Ví dụ: ["internet_sales"] → ["internet_sales", "customers", "products", ...]
        """
        expanded = set(model_names)
        all_model_names = {m.name for m in self._manifest.models}

        for name in model_names:
            rels = self._manifest.get_relationships_for(name)
            for rel in rels:
                # Thêm cả 2 đầu relationship
                if rel.model_from in all_model_names:
                    expanded.add(rel.model_from)
                if rel.model_to in all_model_names:
                    expanded.add(rel.model_to)

        # Giữ thứ tự: original models trước, expanded sau
        result = list(model_names)
        for name in expanded:
            if name not in result:
                result.append(name)

        return result

    def _fetch_db_schemas(self, model_names: list[str]) -> list[dict[str, Any]]:
        """
        Fetch + assemble TABLE + TABLE_COLUMNS docs.

        Giống construct_db_schemas() trong WrenAI gốc:
        - Gom TABLE doc và TABLE_COLUMNS docs cùng name
        - Merge columns vào TABLE dict
        """
        if not model_names:
            return []

        # Fetch tất cả docs từ db_schema có name trong model_names
        all_docs = self._indexer._store.get_by_metadata(
            collection=COLLECTION_DB_SCHEMA,
            where={"type": "TABLE_SCHEMA"},
        )

        # Filter và assemble
        db_schemas: dict[str, dict] = {}

        for doc in all_docs:
            meta = doc.get("metadata", {})
            name = meta.get("name", "")
            if name not in model_names:
                continue

            content = doc.get("document", "")
            try:
                parsed = ast.literal_eval(content)
            except (ValueError, SyntaxError):
                continue

            if parsed.get("type") == "TABLE":
                if name not in db_schemas:
                    db_schemas[name] = parsed
                else:
                    # Merge: giữ columns đã có
                    existing_cols = db_schemas[name].get("columns", [])
                    db_schemas[name] = {**parsed, "columns": existing_cols}
            elif parsed.get("type") == "TABLE_COLUMNS":
                if name not in db_schemas:
                    db_schemas[name] = {"columns": parsed.get("columns", [])}
                else:
                    if "columns" not in db_schemas[name]:
                        db_schemas[name]["columns"] = parsed.get("columns", [])
                    else:
                        db_schemas[name]["columns"] += parsed.get("columns", [])

        # Loại bỏ incomplete schemas (phải có cả type và columns)
        db_schemas = {
            k: v for k, v in db_schemas.items()
            if "type" in v and "columns" in v
        }

        return list(db_schemas.values())
