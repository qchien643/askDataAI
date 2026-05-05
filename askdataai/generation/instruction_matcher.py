"""
Instruction Matcher — Stage 2 of Multi-Stage Intent Pipeline.

Inspired by WrenAI Interactive Mode Step 2:
"Apply relevant instructions — checks predefined instructions or
business rules that should be applied before generating the query."

Matches user questions against Knowledge Instructions and injects
business rules into context before SQL generation.

Example:
- Instruction: "When calculating revenue, always exclude Status = 'Cancelled'"
- Question: "Total revenue in January" → match → inject filter
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Instruction:
    """A single instruction / business rule."""
    id: str
    description: str
    # Keywords or regex patterns for matching
    match_patterns: list[str] = field(default_factory=list)
    # SQL condition or context hint to inject
    sql_condition: str = ""
    context_hint: str = ""
    # Scope: global (all queries) or question-matching
    scope: str = "question"  # "global" | "question"
    enabled: bool = True


@dataclass
class InstructionMatchResult:
    matched_instructions: list[Instruction]
    context_text: str  # Combined context to inject into prompt
    sql_conditions: list[str]  # SQL WHERE conditions to inject


class InstructionMatcher:
    """
    Stage 2: Match user question against Knowledge Instructions.

    No LLM used — keyword/regex matching only.
    Global instructions are always applied.
    """

    def __init__(self, instructions: list[Instruction] | None = None):
        self._instructions = instructions or []
        self._compiled: list[tuple[Instruction, list[re.Pattern]]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for each instruction."""
        self._compiled = []
        for inst in self._instructions:
            if not inst.enabled:
                continue
            patterns = []
            for p in inst.match_patterns:
                try:
                    patterns.append(re.compile(p, re.IGNORECASE | re.UNICODE))
                except re.error:
                    logger.warning(f"Invalid instruction pattern: {p}")
            self._compiled.append((inst, patterns))

    def add_instruction(self, instruction: Instruction) -> None:
        """Add a new instruction."""
        self._instructions.append(instruction)
        self._compile_patterns()

    def set_instructions(self, instructions: list[Instruction]) -> None:
        """Replace all instructions."""
        self._instructions = instructions
        self._compile_patterns()

    @property
    def instruction_count(self) -> int:
        return len(self._instructions)

    def match(self, question: str) -> InstructionMatchResult:
        """
        Match a question against instructions.

        Returns:
            InstructionMatchResult with matched instructions, context, and SQL conditions.
        """
        matched = []

        for inst, patterns in self._compiled:
            # Global instructions always match
            if inst.scope == "global":
                matched.append(inst)
                continue

            # Question-matching: check patterns
            for pattern in patterns:
                if pattern.search(question):
                    matched.append(inst)
                    break

        # Build combined context
        context_parts = []
        sql_conditions = []

        for inst in matched:
            if inst.context_hint:
                context_parts.append(f"• {inst.context_hint}")
            if inst.sql_condition:
                sql_conditions.append(inst.sql_condition)

        context_text = ""
        if context_parts:
            context_text = (
                "## Business Rules (Instructions)\n"
                "Apply the following rules when generating SQL:\n"
                + "\n".join(context_parts)
            )

        if matched:
            logger.info(
                f"InstructionMatcher: {len(matched)} instructions matched "
                f"({', '.join(m.id for m in matched)})"
            )

        return InstructionMatchResult(
            matched_instructions=matched,
            context_text=context_text,
            sql_conditions=sql_conditions,
        )

    @classmethod
    def from_glossary_terms(cls, glossary_path: str = "") -> "InstructionMatcher":
        """
        Create an InstructionMatcher from glossary terms.

        Each glossary term becomes an instruction hint.
        Will integrate with BusinessGlossary later.
        """
        return cls()
