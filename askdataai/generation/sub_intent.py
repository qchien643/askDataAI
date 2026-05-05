"""
Sub-Intent Detector — Stage 4 of Multi-Stage Intent Pipeline.

After confirming intent = TEXT_TO_SQL, classify in more detail
so the SQL Generator can choose the right strategy.

Sub-intents:
- RETRIEVAL: "List all customers" → simple SELECT
- AGGREGATION: "Total revenue" → GROUP BY + aggregate functions
- COMPARISON: "Compare Q1 vs Q2" → CASE/subquery comparison
- TREND: "Trend by month" → time-series grouping
- RANKING: "Top 5 products" → ORDER BY + TOP/LIMIT
- FILTER: "Customers in Hanoi" → WHERE filtering
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


class SubIntent(str, Enum):
    RETRIEVAL = "RETRIEVAL"
    AGGREGATION = "AGGREGATION"
    COMPARISON = "COMPARISON"
    TREND = "TREND"
    RANKING = "RANKING"
    FILTER = "FILTER"
    MULTI_HOP = "MULTI_HOP"


@dataclass
class SubIntentResult:
    sub_intent: SubIntent
    confidence: float
    sql_hints: str  # Hints for SQL Generator


# Keyword patterns for quick detection (before using LLM)
SUB_INTENT_PATTERNS = {
    SubIntent.RANKING: [
        r"(top\s*\d+|ranking|highest|lowest|best|worst|largest|smallest)",
        r"(best|worst|largest|smallest|highest|lowest)",
    ],
    SubIntent.AGGREGATION: [
        r"(count|sum|average|avg|mean|total|how\s*many|how\s*much)",
        r"(aggregate|grouped?\s*by|subtotal)",
    ],
    SubIntent.TREND: [
        r"(trend|monthly|yearly|over\s*time|evolution|growth)",
        r"(by\s*month|by\s*year|by\s*quarter|time\s*series)",
    ],
    SubIntent.COMPARISON: [
        r"(compare|vs\.?|versus|difference|contrast)",
        r"(Q[1-4]\s*(vs|versus)\s*Q[1-4])",
    ],
    SubIntent.FILTER: [
        r"(where|filter|belonging|region|between|since|before|after)",
        r"(greater than|less than|more than|fewer than)",
    ],
    SubIntent.RETRIEVAL: [
        r"(list|show|display|get|fetch|retrieve|give me)",
        r"(all\s+\w+|every\s+\w+)",
    ],
}

SQL_HINTS = {
    SubIntent.RETRIEVAL: "Use simple SELECT with relevant columns. Consider adding LIMIT for large result sets.",
    SubIntent.AGGREGATION: "Use aggregate functions (SUM, COUNT, AVG) with GROUP BY. Consider adding meaningful aliases.",
    SubIntent.COMPARISON: "Use CASE WHEN or subqueries for side-by-side comparison. Consider using pivoting.",
    SubIntent.TREND: "Group by time period (MONTH, QUARTER, YEAR). Use DATEPART or FORMAT for time extraction. Order by time.",
    SubIntent.RANKING: "Use TOP N or ORDER BY with DESC/ASC. Consider using ROW_NUMBER() for complex rankings.",
    SubIntent.FILTER: "Focus on WHERE clause conditions. Consider appropriate operators (=, IN, BETWEEN, LIKE).",
    SubIntent.MULTI_HOP: "This is a multi-hop query. Use CTE chain: each step as a CTE, final SELECT references previous CTEs.",
}

# LLM prompt for cases that don't match any pattern
SUB_INTENT_PROMPT = """Classify the data question into exactly one of 6 sub-intents:

1. RETRIEVAL — retrieve a list, enumerate data (simple SELECT)
2. AGGREGATION — calculate total, count, average (GROUP BY + aggregate)
3. COMPARISON — compare 2+ groups of data (CASE/subquery)
4. TREND — view trend over time (time-series)
5. RANKING — rank top N (ORDER BY + TOP)
6. FILTER — filter data by condition (WHERE)

Respond as JSON: {{"sub_intent": "...", "confidence": 0.0-1.0}}

Question: {question}"""


class SubIntentDetector:
    """
    Stage 4: Detailed TEXT_TO_SQL intent classification.

    Priority: keyword matching (instant), LLM fallback if ambiguous.
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client
        self._patterns = {}
        for intent, patterns in SUB_INTENT_PATTERNS.items():
            self._patterns[intent] = [
                re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns
            ]

    def detect(self, question: str, use_llm: bool = False) -> SubIntentResult:
        """
        Detect sub-intent for a TEXT_TO_SQL question.

        Args:
            question: User question.
            use_llm: Use LLM if keyword matching is not confident enough.

        Returns:
            SubIntentResult with sub_intent, confidence, and sql_hints.
        """
        # Step 1: Keyword matching
        scores: dict[SubIntent, int] = {}
        for intent, compiled_patterns in self._patterns.items():
            score = 0
            for pattern in compiled_patterns:
                if pattern.search(question):
                    score += 1
            if score > 0:
                scores[intent] = score

        if scores:
            # Choose intent with highest score
            best = max(scores, key=scores.get)  # type: ignore
            total_matches = sum(scores.values())
            confidence = scores[best] / max(total_matches, 1)

            logger.info(
                f"SubIntent (keyword): {best.value} "
                f"(confidence={confidence:.2f}, scores={scores})"
            )
            return SubIntentResult(
                sub_intent=best,
                confidence=confidence,
                sql_hints=SQL_HINTS.get(best, ""),
            )

        # Step 2: LLM fallback
        if use_llm and self._llm:
            return self._detect_with_llm(question)

        # Default: RETRIEVAL
        logger.info("SubIntent: default RETRIEVAL (no pattern match)")
        return SubIntentResult(
            sub_intent=SubIntent.RETRIEVAL,
            confidence=0.5,
            sql_hints=SQL_HINTS[SubIntent.RETRIEVAL],
        )

    def _detect_with_llm(self, question: str) -> SubIntentResult:
        """Use LLM to classify sub-intent."""
        try:
            result = self._llm.chat_json(
                user_prompt=SUB_INTENT_PROMPT.format(question=question),
            )
            intent_str = result.get("sub_intent", "RETRIEVAL").upper()
            confidence = float(result.get("confidence", 0.7))

            try:
                sub_intent = SubIntent(intent_str)
            except ValueError:
                sub_intent = SubIntent.RETRIEVAL

            logger.info(
                f"SubIntent (LLM): {sub_intent.value} (confidence={confidence:.2f})"
            )
            return SubIntentResult(
                sub_intent=sub_intent,
                confidence=confidence,
                sql_hints=SQL_HINTS.get(sub_intent, ""),
            )
        except Exception as e:
            logger.warning(f"SubIntent LLM failed: {e}, defaulting to RETRIEVAL")
            return SubIntentResult(
                sub_intent=SubIntent.RETRIEVAL,
                confidence=0.5,
                sql_hints=SQL_HINTS[SubIntent.RETRIEVAL],
            )
