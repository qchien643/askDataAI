"""
Candidate Generator - Sinh nhiều SQL candidates cho voting.

Inspired by: CHASE-SQL (multi-path generation), CSC-SQL (corrective self-consistency).

Sinh N SQL candidates bằng cách:
- Varied temperature (0.0, 0.3, 0.7)
- Có/không reasoning plan
- Different prompt variations

Nhiều candidates → execution voting → chọn SQL tốt nhất.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from src.generation.llm_client import LLMClient
from src.generation.sql_generator import SQLGenerator, SQLGenerationResult

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    """Một SQL candidate."""
    sql: str
    explanation: str = ""
    temperature: float = 0.0
    strategy: str = "default"  # "default", "with_reasoning", "creative"
    raw_response: dict | None = None


@dataclass
class CandidateSet:
    """Tập hợp candidates cho 1 câu hỏi."""
    question: str
    candidates: list[Candidate] = field(default_factory=list)
    reasoning_plan: str = ""


# Strategies: (temperature, include_reasoning, label)
DEFAULT_STRATEGIES = [
    (0.0, True, "precise_with_reasoning"),
    (0.3, True, "balanced_with_reasoning"),
    (0.7, False, "creative_no_reasoning"),
]


class CandidateGenerator:
    """
    Sinh nhiều SQL candidates cho voting.

    Dùng varied temperatures + có/không reasoning plan.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        num_candidates: int = 3,
    ):
        self._llm = llm_client
        self._generator = SQLGenerator(llm_client)
        self._num_candidates = num_candidates

    def generate(
        self,
        question: str,
        ddl_context: str,
        reasoning_plan: str = "",
        schema_hints: str = "",
        sql_samples: list[dict] | None = None,
    ) -> CandidateSet:
        """
        Sinh N SQL candidates.

        Args:
            question: Câu hỏi user.
            ddl_context: DDL context.
            reasoning_plan: CoT reasoning plan (optional).
            schema_hints: Schema linking hints (optional).
            sql_samples: Few-shot examples (optional).

        Returns:
            CandidateSet với N candidates.
        """
        strategies = DEFAULT_STRATEGIES[:self._num_candidates]
        candidates = []

        for temp, use_reasoning, label in strategies:
            try:
                # Build enriched prompt
                enriched_ddl = ddl_context
                if use_reasoning and reasoning_plan:
                    enriched_ddl = f"{reasoning_plan}\n\n{enriched_ddl}"
                if schema_hints:
                    enriched_ddl = f"{schema_hints}\n\n{enriched_ddl}"

                # Generate với temperature cụ thể
                result = self._generate_with_temperature(
                    question=question,
                    ddl_context=enriched_ddl,
                    temperature=temp,
                    sql_samples=sql_samples,
                )

                if result.sql:
                    candidates.append(Candidate(
                        sql=result.sql,
                        explanation=result.explanation,
                        temperature=temp,
                        strategy=label,
                        raw_response=result.raw_response,
                    ))
                    logger.info(
                        f"Candidate [{label}] (temp={temp}): "
                        f"{result.sql[:80]}..."
                    )

            except Exception as e:
                logger.warning(f"Candidate generation failed [{label}]: {e}")

        logger.info(f"Generated {len(candidates)}/{self._num_candidates} candidates")

        return CandidateSet(
            question=question,
            candidates=candidates,
            reasoning_plan=reasoning_plan,
        )

    def _generate_with_temperature(
        self,
        question: str,
        ddl_context: str,
        temperature: float,
        sql_samples: list[dict] | None = None,
    ) -> SQLGenerationResult:
        """Generate SQL với temperature cụ thể."""
        # Tạm thay temperature của LLM client
        original_temp = self._llm._temperature
        self._llm._temperature = temperature

        try:
            result = self._generator.generate(
                question=question,
                ddl_context=ddl_context,
                sql_samples=sql_samples,
            )
            return result
        finally:
            # Restore temperature
            self._llm._temperature = original_temp
