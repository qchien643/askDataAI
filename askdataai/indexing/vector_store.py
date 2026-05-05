"""
VectorStore - Wrapper quanh ChromaDB cho vector search.

Tương đương Qdrant document store trong Wren AI gốc,
nhưng dùng ChromaDB (cài bằng pip, không cần Docker).
"""

import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB vector store wrapper.

    Usage:
        store = VectorStore(persist_dir="./chroma_data")
        store.create_collection("schema_models")
        store.upsert(
            collection="schema_models",
            ids=["customers"],
            documents=["Model: customers ..."],
            embeddings=[[0.1, 0.2, ...]],
            metadatas=[{"model_name": "customers", "type": "TABLE"}]
        )
        results = store.search("schema_models", query_embedding=[...], top_k=3)
    """

    def __init__(self, persist_dir: str = "./chroma_data"):
        """
        Khởi tạo ChromaDB client với persistent storage.

        Args:
            persist_dir: Thư mục lưu trữ ChromaDB data.
        """
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._persist_dir = persist_dir
        logger.info(f"ChromaDB initialized at: {persist_dir}")

    def create_collection(
        self,
        name: str,
        recreate: bool = False,
    ) -> None:
        """
        Tạo collection mới. Nếu recreate=True, xoá cũ tạo lại.

        Args:
            name: Tên collection.
            recreate: True = xoá collection cũ rồi tạo lại.
        """
        if recreate:
            try:
                self._client.delete_collection(name)
                logger.info(f"Deleted existing collection: {name}")
            except Exception:
                pass  # Collection chưa tồn tại

        self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},  # Cosine similarity
        )
        logger.info(f"Collection ready: {name}")

    def delete_collection(self, name: str) -> bool:
        """Xoá collection. Trả về True nếu thành công."""
        try:
            self._client.delete_collection(name)
            logger.info(f"Deleted collection: {name}")
            return True
        except Exception:
            return False

    def upsert(
        self,
        collection: str,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Thêm hoặc cập nhật documents vào collection.

        Args:
            collection: Tên collection.
            ids: Unique IDs cho mỗi document.
            documents: Nội dung text gốc.
            embeddings: Pre-computed embeddings.
            metadatas: Metadata kèm theo (optional).
        """
        coll = self._client.get_collection(collection)
        coll.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info(f"Upserted {len(ids)} documents to '{collection}'")

    def search(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search trong collection.

        Args:
            collection: Tên collection.
            query_embedding: Vector embedding của query.
            top_k: Số kết quả trả về.
            where: Filter metadata (optional).

        Returns:
            List of results, mỗi result là dict:
            {"id", "document", "metadata", "distance"}
        """
        coll = self._client.get_collection(collection)

        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = coll.query(**kwargs)

        # Flatten results
        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i] if results["documents"] else None,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else None,
                "distance": results["distances"][0][i] if results["distances"] else None,
            })

        return output

    def count(self, collection: str) -> int:
        """Số lượng documents trong collection."""
        coll = self._client.get_collection(collection)
        return coll.count()

    def get_by_metadata(
        self,
        collection: str,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch documents bằng metadata filter (không cần embedding).

        Giống Haystack's retriever.run(query_embedding=[], filters=...)
        trong WrenAI gốc — dùng để fetch tất cả docs theo name/type.

        Returns:
            List of {"id", "document", "metadata"}.
        """
        coll = self._client.get_collection(collection)

        kwargs: dict[str, Any] = {
            "include": ["documents", "metadatas"],
        }
        if where:
            kwargs["where"] = where
        if limit:
            kwargs["limit"] = limit

        results = coll.get(**kwargs)

        output = []
        for i in range(len(results["ids"])):
            output.append({
                "id": results["ids"][i],
                "document": results["documents"][i] if results["documents"] else None,
                "metadata": results["metadatas"][i] if results["metadatas"] else None,
            })

        return output

    def list_collections(self) -> list[str]:
        """Danh sách tên tất cả collections."""
        return [c.name for c in self._client.list_collections()]
