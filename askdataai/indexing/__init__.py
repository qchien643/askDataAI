"""
Indexing module — Embed manifest vào Vector DB.
"""

from askdataai.indexing.embedder import OpenAIEmbedder
from askdataai.indexing.vector_store import VectorStore
from askdataai.indexing.schema_indexer import (
    SchemaIndexer,
    DDLChunker,
    TableDescriptionChunker,
    ColumnDescriptionChunker,
    COLLECTION_DB_SCHEMA,
    COLLECTION_TABLE_DESCRIPTIONS,
    COLLECTION_COLUMN_DESCRIPTIONS,
)

__all__ = [
    "OpenAIEmbedder",
    "VectorStore",
    "SchemaIndexer",
    "DDLChunker",
    "TableDescriptionChunker",
    "ColumnDescriptionChunker",
    "COLLECTION_DB_SCHEMA",
    "COLLECTION_TABLE_DESCRIPTIONS",
    "COLLECTION_COLUMN_DESCRIPTIONS",
]
