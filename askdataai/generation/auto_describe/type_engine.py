"""
Type Engine — Batch column type classification.

Classifies columns into categories (ENUM, MEASURE, CODE, TEXT, DATE, FK, BOOL)
using LLM-based batch classification. Used in Phase 3 of XiYan pipeline to
give the agent type hints before generating descriptions.

Reuses: LLMClient.chat_json() for structured classification.
"""

import logging
from typing import Any

from askdataai.generation.llm_client import LLMClient
from askdataai.generation.auto_describe.prompts import CLASSIFY_PROMPT

logger = logging.getLogger(__name__)


class TypeEngine:
    """
    Batch column classifier using LLM.

    Usage:
        engine = TypeEngine(llm_client)
        results = engine.classify_batch(columns, table_name, primary_key, relationships)
    """

    def __init__(self, llm_client: LLMClient, batch_size: int = 20):
        self._llm = llm_client
        self._batch_size = batch_size

    def classify_batch(
        self,
        columns: list[dict[str, Any]],
        table_name: str,
        primary_key: str | None = None,
        relationships: list[dict] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Classify columns into categories in batches.

        Args:
            columns: List of column dicts with keys: name, type
            table_name: Table name for context
            primary_key: Primary key column name
            relationships: FK relationships for context

        Returns:
            Dict mapping column_name -> {"category": "...", "confidence": 0.0-1.0, "reason": "..."}
        """
        all_results: dict[str, dict[str, Any]] = {}

        # Process in batches to stay within LLM context limits
        for i in range(0, len(columns), self._batch_size):
            batch = columns[i : i + self._batch_size]
            batch_results = self._classify_one_batch(
                batch, table_name, primary_key, relationships
            )
            all_results.update(batch_results)

        logger.info(
            f"Classified {len(all_results)} columns in {table_name}: "
            f"{self._summarize(all_results)}"
        )
        return all_results

    def _classify_one_batch(
        self,
        columns: list[dict[str, Any]],
        table_name: str,
        primary_key: str | None,
        relationships: list[dict] | None,
    ) -> dict[str, dict[str, Any]]:
        """Classify a single batch via LLM."""
        # Build column info for prompt
        columns_json = [
            {"name": c["name"], "type": c["type"]}
            for c in columns
        ]

        rel_summary = "None"
        if relationships:
            rel_summary = "; ".join(
                f"{r.get('name', '?')}: {r.get('from', '?')} -> {r.get('to', '?')}"
                for r in relationships
            )

        prompt = CLASSIFY_PROMPT.format(
            columns_json=columns_json,
            table_name=table_name,
            primary_key=primary_key or "N/A",
            relationships=rel_summary,
        )

        try:
            response = self._llm.chat_json(
                user_prompt=prompt,
                system_prompt="You are a database schema analyst. Classify columns accurately.",
                temperature=0.0,
            )

            results = {}
            for item in response.get("classifications", []):
                col_name = item.get("column", "")
                results[col_name] = {
                    "category": item.get("category", "TEXT"),
                    "confidence": item.get("confidence", 0.5),
                    "reason": item.get("reason", ""),
                }
            return results

        except Exception as e:
            logger.error(f"Classification failed for {table_name}: {e}")
            # Fallback: all TEXT
            return {
                c["name"]: {"category": "TEXT", "confidence": 0.0, "reason": "fallback"}
                for c in columns
            }

    @staticmethod
    def _summarize(results: dict[str, dict]) -> str:
        """Summary string of classification counts."""
        counts: dict[str, int] = {}
        for v in results.values():
            cat = v.get("category", "TEXT")
            counts[cat] = counts.get(cat, 0) + 1
        return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
