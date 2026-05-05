"""
Question Translator — VI → EN translator (Stage 0.7).

Position: After PIGuardrail + ConversationContext, before PreFilter.
Purpose: Translate Vietnamese questions to English so the rest of the
pipeline (English schema, English glossary, English prompts) operates
in a single language for higher LLM accuracy.

Heuristic skip: if the question contains no Vietnamese tonal characters,
skip the LLM call to save cost and latency.
"""

import logging
import re
from dataclasses import dataclass

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


# Vietnamese tonal characters — fast detection without LLM call
_VI_PATTERN = re.compile(
    r"[áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]",
    re.IGNORECASE,
)


@dataclass
class TranslationResult:
    """Result of VI → EN translation."""
    original: str       # Original question (VI or EN)
    translated: str     # English version (= original if skipped)
    skipped: bool       # True if input was already English
    error: str = ""     # Non-empty if LLM call failed


_SYSTEM_PROMPT = """You are a translator for a database query system.

Translate the user's Vietnamese question into precise, schema-aware English.

Rules:
- Preserve technical entities exactly (table names, column names, dates, IDs, codes).
- Use database-domain English vocabulary:
  - "doanh thu" → "revenue", "sales"
  - "khách hàng" → "customer"
  - "đơn hàng" → "order"
  - "sản phẩm" → "product"
  - "danh mục" → "category"
  - "lợi nhuận" → "profit"
  - "doanh số" → "sales"
  - "Quý 1/2/3/4" → "Q1/Q2/Q3/Q4"
  - "tháng" → "month", "năm" → "year"
- Keep numbers, dates, and proper nouns unchanged.
- If the input is already English (or only proper nouns), set "skipped": true and return the input unchanged.
- Output strict JSON: {"translated": "...", "skipped": false}

Examples:
Input: "Top 5 khách hàng mua nhiều nhất"
Output: {"translated": "Top 5 customers with the highest purchase volume", "skipped": false}

Input: "Tổng doanh thu theo tháng năm 2024"
Output: {"translated": "Total revenue by month in year 2024", "skipped": false}

Input: "Sản phẩm nào bán chạy nhất Q1"
Output: {"translated": "Which products had the highest sales in Q1", "skipped": false}

Input: "Show me sales by region"
Output: {"translated": "Show me sales by region", "skipped": true}
"""


class QuestionTranslator:
    """Translate Vietnamese questions to English (Stage 0.7)."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    @staticmethod
    def _is_vietnamese(text: str) -> bool:
        """Fast detection: text contains Vietnamese tonal characters."""
        return bool(_VI_PATTERN.search(text))

    def translate(self, question: str) -> TranslationResult:
        """
        Translate VI question to EN. Skip LLM call if already English.

        Args:
            question: User's question (VI or EN).

        Returns:
            TranslationResult with translated text + skip flag.
        """
        question = question.strip()
        if not question:
            return TranslationResult(original=question, translated=question, skipped=True)

        # Heuristic: no Vietnamese tonal chars → assume English, skip LLM
        if not self._is_vietnamese(question):
            return TranslationResult(original=question, translated=question, skipped=True)

        try:
            result = self._llm.chat_json(
                user_prompt=question,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.0,
            )
            translated = result.get("translated", question).strip()
            skipped = bool(result.get("skipped", False))

            if not translated or "error" in result:
                logger.warning(f"Translation failed, falling back to original: {result}")
                return TranslationResult(
                    original=question,
                    translated=question,
                    skipped=True,
                    error=result.get("error", "empty translation"),
                )

            return TranslationResult(
                original=question,
                translated=translated,
                skipped=skipped,
            )
        except Exception as e:
            logger.error(f"QuestionTranslator failed: {e}")
            return TranslationResult(
                original=question,
                translated=question,
                skipped=True,
                error=str(e),
            )
