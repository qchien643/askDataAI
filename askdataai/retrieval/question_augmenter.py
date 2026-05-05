"""QuestionAugmenter — Decompose English question into retrieval-friendly signals.

Used by bidirectional schema retrieval (Sprint 4):
  - keywords: technical/data terms likely matching schema (table or column candidates)
  - entities: specific values, dates, named instances
  - sub_questions: decomposed parts if the question is multi-step

Inspired by:
  Bidirectional Schema Linking (arXiv 2510.14296) — question augmentation step
  AutoLink (arXiv 2511.17190) — agent prompt expansion

Cost: 1 LLM call per ask() invocation (~$0.0003 with gpt-4o-mini).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AugmentationResult:
    """Output of a question augmentation pass."""
    original: str
    keywords: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    sub_questions: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def all_terms(self) -> list[str]:
        """Concat keywords + entities — useful for embedding query."""
        return list(self.keywords) + list(self.entities)

    @property
    def merged_query(self) -> str:
        """Single string suitable as embed-search query."""
        parts = [self.original]
        if self.keywords:
            parts.append(" ".join(self.keywords))
        if self.entities:
            parts.append(" ".join(self.entities))
        return " | ".join(parts)


_SYSTEM_PROMPT = """You are a database query analyst. Given an English question about a database, extract three signals to help schema retrieval.

1. **Keywords**: technical or data-domain terms that likely map to schema elements (table names, column names, business metrics). Use noun-phrases, lowercase, no duplicates.

2. **Entities**: specific values, dates, identifiers, or named instances mentioned in the question (e.g., "Q1 2024", "United States", "ProductName=Mountain-200").

3. **Sub-questions**: if the question has multiple analytical parts, decompose into 2-4 atomic sub-questions. If it's a single-shot query, return [].

Output STRICT JSON only:
{
  "keywords": [...],
  "entities": [...],
  "sub_questions": [...]
}

Examples:

Q: "Top 5 customers with the highest revenue in Q1 2024"
A: {
  "keywords": ["customer", "revenue", "top n", "ranking"],
  "entities": ["Q1 2024"],
  "sub_questions": []
}

Q: "Show me products sold in 2013 but not returned"
A: {
  "keywords": ["product", "sold", "returned", "year filter"],
  "entities": ["2013"],
  "sub_questions": [
    "Which products were sold in 2013?",
    "Which products were returned in 2013?",
    "Difference between the two sets"
  ]
}

Q: "Total revenue by category"
A: {
  "keywords": ["revenue", "category", "aggregation", "group by"],
  "entities": [],
  "sub_questions": []
}
"""


class QuestionAugmenter:
    """Augment a question with structured retrieval signals via LLM."""

    def __init__(self, llm: LLMClient):
        self._llm = llm

    def augment(self, question_en: str) -> AugmentationResult:
        """Run 1 LLM call to extract keywords + entities + sub_questions.

        On any failure, returns a result with empty fields and the original
        question as merged_query — caller can fall back to legacy retrieval.
        """
        question = (question_en or "").strip()
        if not question:
            return AugmentationResult(original=question)

        try:
            result = self._llm.chat_json(
                user_prompt=f"Question: {question}\n\nOutput JSON:",
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.0,
            )
        except Exception as e:
            logger.error(f"QuestionAugmenter LLM call failed: {e}")
            return AugmentationResult(original=question, error=str(e))

        if "error" in result and "keywords" not in result:
            return AugmentationResult(
                original=question,
                error=str(result.get("error", "")),
            )

        return AugmentationResult(
            original=question,
            keywords=[str(k).strip() for k in result.get("keywords", []) if k],
            entities=[str(e).strip() for e in result.get("entities", []) if e],
            sub_questions=[str(s).strip() for s in result.get("sub_questions", []) if s],
        )
