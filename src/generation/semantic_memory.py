"""
Semantic Memory - Lưu và truy xuất execution traces.

Inspired by: AgentSM (Agent Semantic Memory), WrenAI HistoricalQuestion.

Lưu lại các cặp (question, sql, success, result_hash) để:
1. Fast-path: query tương tự → suggest SQL cũ
2. Error avoidance: patterns lỗi → tránh trong tương lai
3. Progressive learning: accuracy tăng dần theo thời gian
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExecutionTrace:
    """Một execution trace."""
    question: str
    sql: str
    success: bool
    result_hash: str = ""
    error: str = ""
    timestamp: str = ""
    models_used: list[str] = field(default_factory=list)
    retries: int = 0


class SemanticMemory:
    """
    Lưu và truy xuất execution traces.

    Persistence: JSON file (đơn giản, đủ dùng cho prototype).
    """

    def __init__(self, storage_path: str = "semantic_memory.json"):
        self._storage_path = storage_path
        self._traces: list[ExecutionTrace] = []
        self._load()

    def _load(self) -> None:
        """Load traces từ file."""
        if not os.path.exists(self._storage_path):
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data.get("traces", []):
                self._traces.append(ExecutionTrace(**item))

            logger.info(f"Loaded {len(self._traces)} traces from {self._storage_path}")

        except Exception as e:
            logger.warning(f"Failed to load semantic memory: {e}")

    def save_trace(
        self,
        question: str,
        sql: str,
        success: bool,
        result_hash: str = "",
        error: str = "",
        models_used: list[str] | None = None,
        retries: int = 0,
    ) -> None:
        """
        Lưu execution trace.

        Args:
            question: Câu hỏi user.
            sql: SQL cuối cùng.
            success: Chạy thành công không.
            result_hash: Hash kết quả (nếu success).
            error: Error message (nếu fail).
            models_used: Tables/models đã dùng.
            retries: Số lần retry.
        """
        trace = ExecutionTrace(
            question=question,
            sql=sql,
            success=success,
            result_hash=result_hash,
            error=error,
            timestamp=datetime.now().isoformat(),
            models_used=models_used or [],
            retries=retries,
        )

        self._traces.append(trace)
        self._persist()

        logger.info(
            f"Saved trace: success={success}, "
            f"total={len(self._traces)} traces"
        )

    def find_similar(
        self,
        question: str,
        max_results: int = 3,
    ) -> list[ExecutionTrace]:
        """
        Tìm traces tương tự (keyword matching đơn giản).

        Args:
            question: Câu hỏi mới.
            max_results: Số traces tối đa.

        Returns:
            List traces tương tự, sorted by relevance.
        """
        if not self._traces:
            return []

        question_words = set(question.lower().split())
        scored: list[tuple[float, ExecutionTrace]] = []

        for trace in self._traces:
            if not trace.success:
                continue

            trace_words = set(trace.question.lower().split())
            # Jaccard similarity
            intersection = question_words & trace_words
            union = question_words | trace_words

            if union:
                score = len(intersection) / len(union)
                if score > 0.3:  # Threshold
                    scored.append((score, trace))

        # Sort by score DESC
        scored.sort(key=lambda x: x[0], reverse=True)

        results = [t for _, t in scored[:max_results]]
        logger.info(f"Found {len(results)} similar traces for '{question[:50]}'")
        return results

    def get_error_patterns(self, max_results: int = 5) -> list[str]:
        """Lấy common error patterns để tránh."""
        errors = [t.error for t in self._traces if not t.success and t.error]
        if not errors:
            return []

        # Count errors, return most common
        from collections import Counter
        counter = Counter(errors)
        return [err for err, _ in counter.most_common(max_results)]

    def build_context(
        self,
        similar_traces: list[ExecutionTrace],
    ) -> str:
        """Build context text từ similar traces."""
        if not similar_traces:
            return ""

        parts = ["### CÂU HỎI TƯƠNG TỰ TRƯỚC ĐÂY ###"]
        for t in similar_traces:
            parts.append(f"Q: {t.question}")
            parts.append(f"SQL: {t.sql}")
            parts.append("")

        return "\n".join(parts)

    def _persist(self) -> None:
        """Persist traces ra file."""
        try:
            data = {
                "traces": [asdict(t) for t in self._traces[-500:]],  # Giữ 500 traces mới nhất
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist semantic memory: {e}")

    @property
    def trace_count(self) -> int:
        return len(self._traces)
