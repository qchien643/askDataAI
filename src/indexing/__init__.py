"""
Indexing module — Embed manifest vào Vector DB.
"""

from src.indexing.embedder import HuggingFaceEmbedder
from src.indexing.vector_store import VectorStore
from src.indexing.schema_indexer import (
    SchemaIndexer,
    DDLChunker,
    TableDescriptionChunker,
    COLLECTION_DB_SCHEMA,
    COLLECTION_TABLE_DESCRIPTIONS,
)

__all__ = [
    "HuggingFaceEmbedder",
    "VectorStore",
    "SchemaIndexer",
    "DDLChunker",
    "TableDescriptionChunker",
    "COLLECTION_DB_SCHEMA",
    "COLLECTION_TABLE_DESCRIPTIONS",
]
