"""
Intent Classifier - Phân loại câu hỏi user.

3 intents:
- TEXT_TO_SQL: câu hỏi về data → cần sinh SQL
- GENERAL: câu hỏi không liên quan → trả lời từ chối
- AMBIGUOUS: câu hỏi mơ hồ → hỏi lại

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
    GENERAL = "GENERAL"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class IntentResult:
    intent: Intent
    reason: str


INTENT_SYSTEM_PROMPT = """Bạn là hệ thống phân loại câu hỏi cho một ứng dụng Text-to-SQL trên SQL Server.

Nhiệm vụ: phân loại câu hỏi của user thành 1 trong 3 loại:

1. TEXT_TO_SQL — Câu hỏi yêu cầu truy vấn dữ liệu. Ví dụ:
   - "Tổng doanh thu theo tháng"
   - "Top 5 khách hàng mua nhiều nhất"
   - "Số lượng sản phẩm theo danh mục"

2. GENERAL — Câu hỏi KHÔNG liên quan đến data. Ví dụ:
   - "Xin chào"
   - "Bạn là ai?"
   - "Thời tiết hôm nay thế nào?"

3. AMBIGUOUS — Câu hỏi có liên quan đến data nhưng quá mơ hồ. Ví dụ:
   - "Cho tôi xem dữ liệu"
   - "Tôi muốn biết thông tin"

Database hiện tại chứa dữ liệu về: {model_names}

Trả lời dưới dạng JSON:
{{"intent": "TEXT_TO_SQL" | "GENERAL" | "AMBIGUOUS", "reason": "lý do ngắn gọn"}}
"""


class IntentClassifier:
    """Phân loại intent của câu hỏi user."""

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
            question: Câu hỏi user.
            model_names: Danh sách model names (để LLM biết scope).

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
