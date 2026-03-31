"""
Sub-Intent Detector — Stage 4 of Multi-Stage Intent Pipeline.

Sau khi xác định intent = TEXT_TO_SQL, phân loại chi tiết hơn
để SQL Generator chọn strategy phù hợp.

Sub-intents:
- RETRIEVAL: "Lấy danh sách khách hàng" → simple SELECT
- AGGREGATION: "Tổng doanh thu" → GROUP BY + aggregate functions
- COMPARISON: "So sánh Q1 vs Q2" → CASE/subquery comparison
- TREND: "Xu hướng theo tháng" → time-series grouping
- RANKING: "Top 5 sản phẩm" → ORDER BY + TOP/LIMIT
- FILTER: "Khách hàng ở Hà Nội" → WHERE filtering
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

from src.generation.llm_client import LLMClient

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
    sql_hints: str  # Gợi ý cho SQL Generator


# Keyword patterns cho quick detection (trước khi dùng LLM)
SUB_INTENT_PATTERNS = {
    SubIntent.RANKING: [
        r"(top\s*\d+|xếp\s*hạng|ranking|nhiều\s*nhất|ít\s*nhất|cao\s*nhất|thấp\s*nhất)",
        r"(best|worst|largest|smallest|highest|lowest)",
    ],
    SubIntent.AGGREGATION: [
        r"(tổng|trung\s*bình|đếm|count|sum|average|avg|mean|total|tổng\s*cộng)",
        r"(bao\s*nhiêu|how\s*many|how\s*much|số\s*lượng)",
    ],
    SubIntent.TREND: [
        r"(xu\s*hướng|trend|theo\s*tháng|theo\s*năm|qua\s*các\s*tháng|monthly|yearly)",
        r"(biến\s*động|thay\s*đổi|evolution|over\s*time|growth)",
    ],
    SubIntent.COMPARISON: [
        r"(so\s*sánh|compare|vs\.?|versus|khác\s*nhau|chênh\s*lệch|difference)",
        r"(Q[1-4]\s*(vs|với)\s*Q[1-4]|năm\s*\d{4}\s*(vs|với)\s*\d{4})",
    ],
    SubIntent.FILTER: [
        r"(ở\s*(đâu|tại)|where|thuộc|belonging|region|khu\s*vực)",
        r"(trong\s*khoảng|between|from\s*\d|since|before|after|lớn\s*hơn|nhỏ\s*hơn)",
    ],
    SubIntent.RETRIEVAL: [
        r"(danh\s*sách|list|liệt\s*kê|cho\s*xem|hiển\s*thị|show|display)",
        r"(lấy\s*ra|lấy\s*dữ\s*liệu|get|fetch|retrieve)",
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

# LLM prompt cho trường hợp không match pattern
SUB_INTENT_PROMPT = """Phân loại câu hỏi data vào 1 trong 6 sub-intent:

1. RETRIEVAL — lấy danh sách, liệt kê dữ liệu (SELECT đơn giản)
2. AGGREGATION — tính tổng, đếm, trung bình (GROUP BY + aggregate)
3. COMPARISON — so sánh 2+ nhóm dữ liệu (CASE/subquery)
4. TREND — xem xu hướng theo thời gian (time-series)
5. RANKING — xếp hạng top N (ORDER BY + TOP)
6. FILTER — lọc dữ liệu theo điều kiện (WHERE)

Trả lời JSON: {{"sub_intent": "...", "confidence": 0.0-1.0}}

Câu hỏi: {question}"""


class SubIntentDetector:
    """
    Stage 4: Phân loại chi tiết TEXT_TO_SQL intent.

    Ưu tiên keyword matching (instant), fallback LLM nếu ambiguous.
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
        Detect sub-intent cho câu hỏi TEXT_TO_SQL.

        Args:
            question: Câu hỏi user.
            use_llm: Dùng LLM nếu keyword matching không chắc chắn.

        Returns:
            SubIntentResult với sub_intent, confidence, và sql_hints.
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
            # Chọn intent có score cao nhất
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
        """Dùng LLM để phân loại sub-intent."""
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
