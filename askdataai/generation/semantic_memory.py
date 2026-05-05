"""
Semantic Memory - Store and retrieve execution traces.

Inspired by: AgentSM (Agent Semantic Memory), WrenAI HistoricalQuestion.

Stores (question, sql, success, result_hash) pairs to enable:
1. Fast-path: similar query → suggest cached SQL
2. Error avoidance: known error patterns → avoid in the future
3. Progressive learning: accuracy improves over time
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
    """A single execution trace.

    `question` is the English version (post-translator) used for matching.
    `question_vi` is the original user input (Vietnamese or English) preserved for audit + UI.
    For traces saved before the bilingual upgrade, `question_vi` may be empty.
    """
    question: str
    sql: str
    success: bool
    result_hash: str = ""
    error: str = ""
    timestamp: str = ""
    models_used: list[str] = field(default_factory=list)
    retries: int = 0
    question_vi: str = ""


class SemanticMemory:
    """
    Store and retrieve execution traces.

    Persistence: JSON file (simple, sufficient for prototype).
    """

    def __init__(self, storage_path: str = "data/semantic_memory.json"):
        self._storage_path = storage_path
        self._traces: list[ExecutionTrace] = []
        self._load()

    def _load(self) -> None:
        """Load traces from file."""
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
        question_vi: str = "",
    ) -> None:
        """
        Save an execution trace.

        Args:
            question: English question (post-translator) used downstream.
            sql: Final SQL query executed.
            success: Whether the query ran successfully.
            result_hash: Hash of the result (if success).
            error: Error message (if failed).
            models_used: Tables/models used.
            retries: Number of retry attempts.
            question_vi: Original user input (Vietnamese) preserved for audit/UI.
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
            question_vi=question_vi,
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
        Find similar traces (simple keyword matching).

        Args:
            question: New question to match against.
            max_results: Maximum number of traces to return.

        Returns:
            List of similar traces sorted by relevance.
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
        """Get common error patterns to avoid in the future."""
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
        """Build context text from similar traces."""
        if not similar_traces:
            return ""

        parts = ["### SIMILAR PREVIOUS QUESTIONS ###"]
        for t in similar_traces:
            parts.append(f"Q: {t.question}")
            parts.append(f"SQL: {t.sql}")
            parts.append("")

        return "\n".join(parts)

    def _persist(self) -> None:
        """Persist traces to file."""
        try:
            data = {
                "traces": [asdict(t) for t in self._traces[-500:]],  # Keep 500 most recent
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist semantic memory: {e}")

    @property
    def trace_count(self) -> int:
        return len(self._traces)
