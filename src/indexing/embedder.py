"""
Embedder - Tạo embeddings bằng HuggingFace Inference API.

Dùng model multilingual-e5-large (1024 dims) qua HuggingFace Hub,
giống model mà Wren AI gốc sử dụng.
"""

import logging
import time
import numpy as np

from huggingface_hub import InferenceClient

logger = logging.getLogger(__name__)


class HuggingFaceEmbedder:
    """
    Embed text bằng HuggingFace Inference API (huggingface_hub).

    Model: intfloat/multilingual-e5-large (1024 dimensions)
    - Multilingual: hỗ trợ tiếng Việt tốt
    - Giống model Wren AI gốc dùng

    Usage:
        embedder = HuggingFaceEmbedder(api_key="hf_...")
        vector = embedder.embed_text("tổng doanh thu")
        vectors = embedder.embed_batch(["doanh thu", "khách hàng"])
    """

    DEFAULT_MODEL = "intfloat/multilingual-e5-large"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
    ):
        self._model = model
        self._client = InferenceClient(
            provider="hf-inference",
            api_key=api_key,
        )
        self._dimensions: int | None = None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            vec = self.embed_text("test")
            self._dimensions = len(vec)
        return self._dimensions

    def embed_text(self, text: str) -> list[float]:
        """Embed 1 text thành vector."""
        result = self._client.feature_extraction(
            text,
            model=self._model,
        )
        # result là numpy array hoặc nested list: shape (1, seq_len, dim) hoặc (seq_len, dim)
        # Cần mean pooling để lấy 1 vector duy nhất
        arr = np.array(result)
        if arr.ndim == 3:
            # (1, seq_len, dim) → mean over seq_len
            vec = arr[0].mean(axis=0)
        elif arr.ndim == 2:
            # (seq_len, dim) → mean over seq_len
            vec = arr.mean(axis=0)
        elif arr.ndim == 1:
            # Already a single vector
            vec = arr
        else:
            raise ValueError(f"Unexpected embedding shape: {arr.shape}")
        return vec.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed query (thêm prefix 'query: ' cho e5 models)."""
        return self.embed_text(f"query: {query}")

    def embed_document(self, document: str) -> list[float]:
        """Embed document (thêm prefix 'passage: ' cho e5 models)."""
        return self.embed_text(f"passage: {document}")

    def embed_batch(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """
        Embed nhiều texts.

        Args:
            texts: List of texts to embed.
            is_query: True = thêm prefix "query:", False = thêm prefix "passage:"
        """
        prefix = "query: " if is_query else "passage: "
        results = []

        for i, text in enumerate(texts):
            prefixed = f"{prefix}{text}"
            vec = self.embed_text(prefixed)
            results.append(vec)

            # Tránh rate limit
            if i > 0 and i % 5 == 0:
                time.sleep(0.3)

            if (i + 1) % 5 == 0 or (i + 1) == len(texts):
                logger.info(f"  Embedded {i + 1}/{len(texts)} documents")

        return results
