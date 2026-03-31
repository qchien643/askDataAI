"""
Intent Classifier — Stage 3 of Multi-Stage Intent Pipeline.

4 intents (expanded from 3):
- TEXT_TO_SQL: câu hỏi về data → cần sinh SQL
- SCHEMA_EXPLORE: câu hỏi về schema → trả lời từ manifest (NEW)
- GENERAL: câu hỏi không liên quan → trả lời từ chối
- AMBIGUOUS: câu hỏi mơ hồ → hỏi lại

Prompt nhỏ gọn hơn vì Stage 1 (PreFilter) đã lọc bớt noise.

Tương đương intent classification trong WrenAI gốc
(wren-ai-service/src/pipelines/generation/intent_validation.py).
"""

import logging
from dataclasses import dataclass
from enum import Enum

from src.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    TEXT_TO_SQL = "TEXT_TO_SQL"
    SCHEMA_EXPLORE = "SCHEMA_EXPLORE"
    GENERAL = "GENERAL"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class IntentResult:
    intent: Intent
    reason: str


# Prompt nhỏ gọn — Stage 1 đã lọc greeting + obvious out-of-scope
INTENT_SYSTEM_PROMPT = """Phân loại câu hỏi thành 1 trong 4 loại:

1. TEXT_TO_SQL — Câu hỏi yêu cầu truy vấn/phân tích dữ liệu.
   Ví dụ: "Tổng doanh thu theo tháng", "Top 5 khách hàng"

2. SCHEMA_EXPLORE — Câu hỏi về cấu trúc database, không cần query.
   Ví dụ: "Có bảng nào?", "Mô tả bảng customers", "Mối quan hệ giữa các bảng"

3. GENERAL — Câu hỏi không liên quan đến database.
   Ví dụ: "Thời tiết hôm nay", "Bạn là ai?"

4. AMBIGUOUS — Câu hỏi liên quan data nhưng quá mơ hồ.
   Ví dụ: "Cho xem dữ liệu", "Tôi muốn biết thông tin"

Database chứa: {model_names}

Trả lời JSON: {{"intent": "...", "reason": "lý do ngắn gọn"}}"""


class IntentClassifier:
    """Stage 3: Phân loại intent bằng LLM (focused prompt)."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def classify(
        self,
        question: str,
        model_names: list[str],
    ) -> IntentResult:
        """
        Phân loại câu hỏi.

        Args:
            question: Câu hỏi user (đã qua PreFilter).
            model_names: Danh sách model names.

        Returns:
            IntentResult với intent và reason.
        """
        system_prompt = INTENT_SYSTEM_PROMPT.format(
            model_names=", ".join(model_names)
        )

        result = self._llm.chat_json(
            user_prompt=question,
            system_prompt=system_prompt,
        )

        intent_str = result.get("intent", "GENERAL").upper()
        reason = result.get("reason", "")

        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.GENERAL
            reason = f"Unknown intent '{intent_str}', defaulting to GENERAL"

        logger.info(f"Intent: {intent.value} — {reason}")
        return IntentResult(intent=intent, reason=reason)
