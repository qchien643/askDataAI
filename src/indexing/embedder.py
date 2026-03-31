"""
Embedder - Tạo embeddings bằng OpenAI API.

Dùng model text-embedding-3-small (1536 dims) — nhanh, rẻ, ổn định.
Tương thích API OpenAI nên hoạt động với cả OpenAI gốc lẫn proxy.
"""

import logging
import time
from openai import OpenAI

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # seconds


class OpenAIEmbedder:
    """
    Embed text bằng OpenAI Embeddings API.

    Model: text-embedding-3-small (1536 dimensions)
    - Nhanh, ổn định, rẻ ($0.02/1M tokens)
    - Multilingual tốt

    Usage:
        embedder = OpenAIEmbedder(api_key="sk-...", base_url="https://api.openai.com/v1")
        vector = embedder.embed_text("tổng doanh thu")
        vectors = embedder.embed_batch(["doanh thu", "khách hàng"])
    """

    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = DEFAULT_MODEL,
    ):
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)
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
        """Embed 1 text thành vector, với retry khi lỗi."""
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.embeddings.create(
                    input=text,
                    model=self._model,
                )
                return response.data[0].embedding

            except Exception as e:
                last_error = e
                error_str = str(e)

                is_retryable = any(code in error_str for code in [
                    "429", "500", "502", "503", "504",
                    "rate_limit", "timeout", "Timeout",
                    "overloaded", "capacity",
                ])

                if is_retryable and attempt < MAX_RETRIES:
                    backoff = INITIAL_BACKOFF * (2 ** attempt)
                    logger.warning(
                        f"  OpenAI Embedding error (attempt {attempt + 1}/{MAX_RETRIES + 1}): "
                        f"{error_str[:100]}... Retrying in {backoff}s"
                    )
                    time.sleep(backoff)
                else:
                    raise

        raise last_error  # type: ignore

    def embed_query(self, query: str) -> list[float]:
        """Embed query (e5 prefix không cần cho OpenAI, giữ interface tương thích)."""
        return self.embed_text(query)

    def embed_document(self, document: str) -> list[float]:
        """Embed document."""
        return self.embed_text(document)

    def embed_batch(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """
        Embed nhiều texts bằng batch API (OpenAI hỗ trợ native batch).

        OpenAI allows up to 2048 inputs per request, mỗi input max 8191 tokens.
        Gửi batch thay vì từng text → nhanh hơn rất nhiều.
        """
        if not texts:
            return []

        BATCH_SIZE = 100  # OpenAI safe batch size

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]

            last_error = None
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = self._client.embeddings.create(
                        input=batch,
                        model=self._model,
                    )
                    # Response data is sorted by index
                    sorted_data = sorted(response.data, key=lambda x: x.index)
                    batch_embeddings = [d.embedding for d in sorted_data]
                    all_embeddings.extend(batch_embeddings)

                    logger.info(f"  Embedded {min(i + BATCH_SIZE, len(texts))}/{len(texts)} documents")
                    break

                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    is_retryable = any(code in error_str for code in [
                        "429", "500", "502", "503", "504",
                        "rate_limit", "timeout",
                    ])
                    if is_retryable and attempt < MAX_RETRIES:
                        backoff = INITIAL_BACKOFF * (2 ** attempt)
                        logger.warning(
                            f"  Batch embed error (attempt {attempt + 1}): "
                            f"{error_str[:100]}... Retrying in {backoff}s"
                        )
                        time.sleep(backoff)
                    else:
                        raise
            else:
                raise last_error  # type: ignore

        return all_embeddings


# Backward-compatible alias
HuggingFaceEmbedder = OpenAIEmbedder
