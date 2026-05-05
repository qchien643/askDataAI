"""
Description Indexer — ChromaDB index for existing column descriptions.

Embeds all human-written descriptions into a ChromaDB collection for
few-shot retrieval. The agent uses this to learn the user's writing style
and find similar column descriptions.

Reuses: VectorStore (ChromaDB wrapper), OpenAIEmbedder.
Embedding model: multilingual-e5-large (configured externally).
"""

import logging
import re
from typing import Any

from askdataai.indexing.vector_store import VectorStore
from askdataai.indexing.embedder import OpenAIEmbedder

logger = logging.getLogger(__name__)

COLLECTION_NAME = "xiyan_desc_examples"


class DescriptionIndexer:
    """
    Index existing column descriptions into ChromaDB for semantic search.

    Usage:
        indexer = DescriptionIndexer(vector_store, embedder)
        count = indexer.index_from_manifest(manifest)
        results = indexer.search("monetary amount price USD", n=3)
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: OpenAIEmbedder,
        collection_name: str = COLLECTION_NAME,
    ):
        self._store = vector_store
        self._embedder = embedder
        self._collection = collection_name

    def index_from_manifest(self, manifest, force_recreate: bool = True) -> int:
        """
        Index all columns that have descriptions from a Manifest.

        Each document = one column description with metadata for filtering.
        Format: "Table={table} | Column={col} | Type={type} | Desc={desc}"

        Args:
            manifest: Manifest object from ManifestBuilder.
            force_recreate: If True, delete and recreate collection.

        Returns:
            Number of documents indexed.
        """
        # Prepare collection
        self._store.create_collection(
            self._collection, recreate=force_recreate
        )

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for model in manifest.models:
            for col in model.columns:
                desc = col.description.strip()
                if not desc:
                    continue

                doc_id = f"{model.name}.{col.name}"
                category = self._classify_from_description(desc, col.type)

                # Document text for embedding
                doc_text = (
                    f"Table={model.name} | Column={col.name} | "
                    f"Type={col.type} | Desc={desc}"
                )

                ids.append(doc_id)
                documents.append(doc_text)
                metadatas.append({
                    "table": model.name,
                    "column": col.name,
                    "type": col.type,
                    "category": category,
                    "description": desc,
                    "has_enum": "true" if col.has_enum else "false",
                })

        if not ids:
            logger.warning("No descriptions found to index")
            return 0

        # Embed all documents in batch
        logger.info(f"Embedding {len(ids)} descriptions...")
        embeddings = self._embedder.embed_batch(documents)

        # Upsert to ChromaDB
        self._store.upsert(
            collection=self._collection,
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(f"Indexed {len(ids)} descriptions into '{self._collection}'")
        return len(ids)

    def search(
        self,
        query: str,
        n: int = 3,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search for similar column descriptions.

        Args:
            query: Natural language query describing the column type.
            n: Number of results (1-10).
            category: Optional filter: ENUM, MEASURE, CODE, TEXT, DATE, FK.

        Returns:
            List of results with metadata and similarity score.
        """
        n = min(max(n, 1), 10)

        # Embed query
        query_embedding = self._embedder.embed_query(query)

        # Build metadata filter
        where = None
        if category:
            where = {"category": category.upper()}

        # Search ChromaDB
        results = self._store.search(
            collection=self._collection,
            query_embedding=query_embedding,
            top_k=n,
            where=where,
        )

        # Format results for agent consumption
        formatted = []
        for r in results:
            meta = r.get("metadata", {})
            distance = r.get("distance", 1.0)
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            similarity = max(0.0, 1.0 - distance)

            formatted.append({
                "table": meta.get("table", ""),
                "column": meta.get("column", ""),
                "type": meta.get("type", ""),
                "category": meta.get("category", ""),
                "description": meta.get("description", ""),
                "similarity": round(similarity, 3),
            })

        return formatted

    def count(self) -> int:
        """Number of indexed descriptions."""
        try:
            return self._store.count(self._collection)
        except Exception:
            return 0

    @staticmethod
    def _classify_from_description(description: str, col_type: str) -> str:
        """
        Heuristic classification of a column based on its description.

        Returns: ENUM, MEASURE, CODE, TEXT, DATE, FK
        """
        desc_lower = description.lower()

        # FK detection
        if any(kw in desc_lower for kw in ["fk ", "foreign key", "fk tới", "fk to"]):
            return "FK"

        # Date detection
        if col_type.lower() in ("date", "datetime") or "ngày" in desc_lower:
            return "DATE"

        # Enum detection: look for listed values pattern
        # Pattern: "value1, value2, value3" or "X = Label, Y = Label"
        if re.search(r':\s*\w+.*,\s*\w+', description):
            return "ENUM"
        if re.search(r'\b[A-Z]\s*=\s*\w+', description):
            return "ENUM"

        # Measure detection
        if any(kw in desc_lower for kw in [
            "price", "cost", "amount", "total", "revenue", "salary",
            "income", "rate", "quantity", "qty", "count", "sum",
            "giá", "chi phí", "tổng", "số lượng", "thu nhập",
            "usd", "vnd", "eur",
        ]):
            return "MEASURE"

        # Code detection
        if any(kw in desc_lower for kw in [
            "code", "mã", "alternate key", "key thay thế", "iso",
        ]):
            return "CODE"

        return "TEXT"
