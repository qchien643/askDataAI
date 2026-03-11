"""
SchemaIndexer - Embed manifest vào ChromaDB.

Upgrade theo pattern DDLChunker của Wren AI gốc:
- 2 collections riêng biệt:
  1. db_schema: TABLE chunks + TABLE_COLUMNS batches (có FK)
  2. table_descriptions: TABLE_DESCRIPTION (name + description + column names)

- Mỗi model tạo ra nhiều documents:
  + 1 TABLE chunk: tên model + alias + description
  + 1+ TABLE_COLUMNS batch: columns + FK constraints, batch 50 cols/batch
  + 1 TABLE_DESCRIPTION: name + description + danh sách tên columns

Tham khảo:
  wren-ai-service/src/pipelines/indexing/db_schema.py — DDLChunker
  wren-ai-service/src/pipelines/indexing/table_description.py — TableDescriptionChunker
"""

import logging
import uuid
from typing import Any

from src.indexing.embedder import HuggingFaceEmbedder
from src.indexing.vector_store import VectorStore
from src.modeling.mdl_schema import Manifest, Model, Relationship

logger = logging.getLogger(__name__)

# Collection names (giống WrenAI dùng 2 stores riêng)
COLLECTION_DB_SCHEMA = "db_schema"
COLLECTION_TABLE_DESCRIPTIONS = "table_descriptions"

# Default column batch size (giống WrenAI: 50)
DEFAULT_COLUMN_BATCH_SIZE = 50


class DDLChunker:
    """
    Chuyển Manifest → documents theo pattern WrenAI gốc.

    Mỗi model tạo ra:
    - 1 TABLE chunk: metadata bảng (name, alias, description)
    - 1+ TABLE_COLUMNS batches: columns + FK, batch 50 cols/batch
    """

    def __init__(self, column_batch_size: int = DEFAULT_COLUMN_BATCH_SIZE):
        self._column_batch_size = column_batch_size

    def chunk(self, manifest: Manifest) -> list[dict[str, Any]]:
        """
        Tạo tất cả chunks từ manifest.

        Returns:
            List of chunks, mỗi chunk:
            {"id": str, "content": str, "metadata": dict}
        """
        chunks = []

        # Build primary keys map (cần cho FK constraint)
        pk_map = {
            m.name: m.primary_key or ""
            for m in manifest.models
        }

        for model in manifest.models:
            # 1. TABLE chunk
            chunks.append(self._table_chunk(model))

            # 2. TABLE_COLUMNS batches (columns + FK)
            model_rels = manifest.get_relationships_for(model.name)
            batches = self._column_batches(model, model_rels, pk_map)
            chunks.extend(batches)

        return chunks

    def _table_chunk(self, model: Model) -> dict[str, Any]:
        """
        Tạo TABLE chunk — giống _model_command() trong WrenAI.

        Format:
        {'type': 'TABLE',
         'comment': '/* {"alias": "...", "description": "..."} */',
         'name': 'customers'}
        """
        properties = {
            "alias": model.name,
            "description": model.description.strip() if model.description else "",
        }
        comment = f'\n/* {properties} */\n'

        payload = {
            "type": "TABLE",
            "comment": comment,
            "name": model.name,
        }

        return {
            "id": str(uuid.uuid4()),
            "content": str(payload),
            "metadata": {
                "type": "TABLE_SCHEMA",
                "name": model.name,
                "chunk_type": "TABLE",
                "table_reference": model.table_reference,
            },
        }

    def _column_batches(
        self,
        model: Model,
        relationships: list[Relationship],
        pk_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        """
        Tạo TABLE_COLUMNS batches — giống _column_batch() trong WrenAI.

        Mỗi batch chứa tối đa column_batch_size items (columns + FKs).
        """
        # Build column commands
        commands = []
        for col in model.columns:
            cmd = self._column_command(col, model)
            if cmd:
                commands.append(cmd)

        # Build FK commands
        for rel in relationships:
            cmd = self._fk_command(rel, model.name, pk_map)
            if cmd:
                commands.append(cmd)

        # Batch
        batches = []
        for i in range(0, max(len(commands), 1), self._column_batch_size):
            batch_items = commands[i : i + self._column_batch_size]

            payload = {
                "type": "TABLE_COLUMNS",
                "columns": batch_items,
            }

            batches.append({
                "id": str(uuid.uuid4()),
                "content": str(payload),
                "metadata": {
                    "type": "TABLE_SCHEMA",
                    "name": model.name,
                    "chunk_type": "TABLE_COLUMNS",
                    "batch_index": i // self._column_batch_size,
                    "column_count": len(batch_items),
                },
            })

        return batches

    @staticmethod
    def _column_command(col, model: Model) -> dict | None:
        """Tạo COLUMN command — giống _column_command() trong WrenAI."""
        comment_parts = []

        # Properties comment (display_name, description)
        props = {}
        if col.display_name:
            props["alias"] = col.display_name
        if col.description:
            props["description"] = col.description
        if col.is_calculated and col.expression:
            comment_parts.append(
                f"-- This column is a Calculated Field\n"
                f"  -- column expression: {col.expression}\n  "
            )
        if props:
            comment_parts.append(f"-- {props}\n  ")

        return {
            "type": "COLUMN",
            "comment": "".join(comment_parts),
            "name": col.name,               # Tên cột gốc DB
            "display_name": col.ai_name,     # Tên cho AI đọc
            "data_type": col.type,
            "is_primary_key": col.name == model.primary_key,
        }

    @staticmethod
    def _fk_command(
        rel: Relationship,
        table_name: str,
        pk_map: dict[str, str],
    ) -> dict | None:
        """Tạo FOREIGN_KEY command — giống _relationship_command() trong WrenAI."""
        # Chỉ xử lý relationship liên quan đến table này
        if rel.model_from != table_name and rel.model_to != table_name:
            return None

        if rel.join_type.value not in ("MANY_TO_ONE", "ONE_TO_MANY", "ONE_TO_ONE"):
            return None

        # Parse condition: "model_a.col_a = model_b.col_b"
        parts = rel.condition.split(" = ")
        if len(parts) != 2:
            return None

        is_source = table_name == rel.model_from
        related_table = rel.model_to if is_source else rel.model_from
        fk_column = parts[0 if is_source else 1].strip().split(".")[-1]
        ref_pk = pk_map.get(related_table, "")

        fk_constraint = f"FOREIGN KEY ({fk_column}) REFERENCES {related_table}({ref_pk})"

        return {
            "type": "FOREIGN_KEY",
            "comment": f'-- {{"condition": "{rel.condition}", "joinType": "{rel.join_type.value}"}}\n  ',
            "constraint": fk_constraint,
            "tables": [rel.model_from, rel.model_to],
        }


class TableDescriptionChunker:
    """
    Tạo TABLE_DESCRIPTION chunks — giống TableDescriptionChunker WrenAI.

    Mỗi model tạo 1 document: name + description + danh sách tên columns.
    Lưu vào collection riêng, dùng cho retrieval khác.
    """

    def chunk(self, manifest: Manifest) -> list[dict[str, Any]]:
        chunks = []
        for model in manifest.models:
            # Dùng ai_name (display_name nếu có, fallback name)
            column_entries = [
                f"{col.ai_name} ({col.type})"
                for col in model.columns
            ]
            content = {
                "name": model.name,
                "description": model.description.strip() if model.description else "",
                "columns": ", ".join(column_entries),
            }
            chunks.append({
                "id": str(uuid.uuid4()),
                "content": str(content),
                "metadata": {
                    "type": "TABLE_DESCRIPTION",
                    "name": model.name,
                    "table_reference": model.table_reference,
                },
            })
        return chunks


class SchemaIndexer:
    """
    Index manifest schema vào ChromaDB — giống DBSchema + TableDescription pipelines.

    Dùng 2 collections:
    - db_schema: TABLE + TABLE_COLUMNS chunks (cho SQL generation)
    - table_descriptions: TABLE_DESCRIPTION chunks (cho model matching)

    Usage:
        indexer = SchemaIndexer(vector_store, embedder)
        indexer.index(manifest)
        results = indexer.search("tổng doanh thu", top_k=3)
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: HuggingFaceEmbedder,
        column_batch_size: int = DEFAULT_COLUMN_BATCH_SIZE,
    ):
        self._store = vector_store
        self._embedder = embedder
        self._ddl_chunker = DDLChunker(column_batch_size)
        self._desc_chunker = TableDescriptionChunker()
        self._indexed_hash: str | None = None

    def index(
        self,
        manifest: Manifest,
        manifest_hash: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Index manifest vào cả 2 collections.

        Returns:
            {"indexed": bool, "db_schema_docs": int,
             "table_desc_docs": int, "reason": str}
        """
        # Hash-based skip
        if not force and manifest_hash and manifest_hash == self._indexed_hash:
            logger.info(f"Manifest unchanged (hash={manifest_hash[:8]}...), skipping.")
            return {
                "indexed": False,
                "db_schema_docs": 0,
                "table_desc_docs": 0,
                "reason": "manifest_unchanged",
            }

        # ── Pipeline 1: DB Schema (TABLE + TABLE_COLUMNS) ──
        ddl_chunks = self._ddl_chunker.chunk(manifest)
        self._store.create_collection(COLLECTION_DB_SCHEMA, recreate=True)

        ddl_texts = [c["content"] for c in ddl_chunks]
        logger.info(f"Embedding {len(ddl_texts)} db_schema documents...")
        ddl_embeddings = self._embedder.embed_batch(ddl_texts, is_query=False)

        self._store.upsert(
            collection=COLLECTION_DB_SCHEMA,
            ids=[c["id"] for c in ddl_chunks],
            documents=ddl_texts,
            embeddings=ddl_embeddings,
            metadatas=[c["metadata"] for c in ddl_chunks],
        )

        # ── Pipeline 2: Table Descriptions ──
        desc_chunks = self._desc_chunker.chunk(manifest)
        self._store.create_collection(COLLECTION_TABLE_DESCRIPTIONS, recreate=True)

        desc_texts = [c["content"] for c in desc_chunks]
        logger.info(f"Embedding {len(desc_texts)} table_description documents...")
        desc_embeddings = self._embedder.embed_batch(desc_texts, is_query=False)

        self._store.upsert(
            collection=COLLECTION_TABLE_DESCRIPTIONS,
            ids=[c["id"] for c in desc_chunks],
            documents=desc_texts,
            embeddings=desc_embeddings,
            metadatas=[c["metadata"] for c in desc_chunks],
        )

        # Save hash
        self._indexed_hash = manifest_hash

        db_count = self._store.count(COLLECTION_DB_SCHEMA)
        desc_count = self._store.count(COLLECTION_TABLE_DESCRIPTIONS)

        logger.info(
            f"Indexed: {db_count} db_schema docs, {desc_count} table_desc docs"
        )

        return {
            "indexed": True,
            "db_schema_docs": db_count,
            "table_desc_docs": desc_count,
            "reason": "success",
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        collection: str = COLLECTION_TABLE_DESCRIPTIONS,
    ) -> list[dict[str, Any]]:
        """
        Semantic search.

        Args:
            query: Câu hỏi user.
            top_k: Số kết quả.
            collection: Collection để search (default: table_descriptions).
        """
        query_embedding = self._embedder.embed_query(query)
        return self._store.search(
            collection=collection,
            query_embedding=query_embedding,
            top_k=top_k,
        )

    def search_schema(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search trong db_schema collection (TABLE + TABLE_COLUMNS)."""
        return self.search(query, top_k, COLLECTION_DB_SCHEMA)

    def search_descriptions(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search trong table_descriptions collection."""
        return self.search(query, top_k, COLLECTION_TABLE_DESCRIPTIONS)
