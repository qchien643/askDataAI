"""
Intent Classifier — Stage 3 of Multi-Stage Intent Pipeline.

4 intents (expanded from 3):
- TEXT_TO_SQL: data questions → need SQL generation
- SCHEMA_EXPLORE: schema questions → answer from manifest (NEW)
- GENERAL: unrelated questions → decline response
- AMBIGUOUS: vague questions → ask for clarification

Prompt is more compact because Stage 1 (PreFilter) already filtered out noise.

Equivalent to intent classification in original WrenAI
(wren-ai-service/src/pipelines/generation/intent_validation.py).
"""

import logging
from dataclasses import dataclass
from enum import Enum

from askdataai.generation.llm_client import LLMClient

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

# Compact prompt — Stage 1 already filtered greetings + obvious out-of-scope
INTENT_SYSTEM_PROMPT = """Classify the question into exactly one of 4 categories:

1. TEXT_TO_SQL — Questions that require querying or analyzing data.
   Examples: "Total revenue by month", "Top 5 customers"

2. SCHEMA_EXPLORE — Questions about database structure, no query needed.
   Examples: "What tables are there?", "Describe the customers table", "How are the tables related?"

3. GENERAL — Questions unrelated to the database.
   Examples: "What's the weather?", "Who are you?"

4. AMBIGUOUS — Questions related to data but too vague.
   Examples: "Show me the data", "I want some information"

Database contains: {model_names}

Respond as JSON: {{"intent": "...", "reason": "brief reason"}}"""


class IntentClassifier:
    """Stage 3: Classify intent using LLM (focused prompt)."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def classify(
        self,
        question: str,
        model_names: list[str],
    ) -> IntentResult:
        """
        Classify the question.

        Args:
            question: User question (already passed through PreFilter).
            model_names: List of model names.

        Returns:
            IntentResult with intent and reason.
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
