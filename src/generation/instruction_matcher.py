"""
Instruction Matcher — Stage 2 of Multi-Stage Intent Pipeline.

Lấy ý tưởng từ WrenAI Interactive Mode Step 2:
"Apply relevant instructions — checks predefined instructions or
business rules that should be applied before generating the query."

Matches user questions against Knowledge Instructions và inject
business rules vào context trước khi SQL generation.

Ví dụ:
- Instruction: "Khi tính doanh thu, luôn exclude Status = 'Cancelled'"
- Question: "Tổng doanh thu tháng 1" → match → inject filter
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Instruction:
    """Một instruction/business rule."""
    id: str
    description: str
    # Keywords hoặc regex patterns để match
    match_patterns: list[str] = field(default_factory=list)
    # SQL condition hoặc context hint để inject
    sql_condition: str = ""
    context_hint: str = ""
    # Scope: global (mọi query) hoặc question-matching
    scope: str = "question"  # "global" | "question"
    enabled: bool = True


@dataclass
class InstructionMatchResult:
    matched_instructions: list[Instruction]
    context_text: str  # Combined context để inject vào prompt
    sql_conditions: list[str]  # SQL WHERE conditions để inject


class InstructionMatcher:
    """
    Stage 2: Match câu hỏi với Knowledge Instructions.

    Không dùng LLM — chỉ keyword/regex matching.
    Global instructions luôn được apply.
    """

    def __init__(self, instructions: list[Instruction] | None = None):
        self._instructions = instructions or []
        self._compiled: list[tuple[Instruction, list[re.Pattern]]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns cho mỗi instruction."""
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
        """Thêm instruction mới."""
        self._instructions.append(instruction)
        self._compile_patterns()

    def set_instructions(self, instructions: list[Instruction]) -> None:
        """Set toàn bộ instructions."""
        self._instructions = instructions
        self._compile_patterns()

    @property
    def instruction_count(self) -> int:
        return len(self._instructions)

    def match(self, question: str) -> InstructionMatchResult:
        """
        Match câu hỏi với instructions.

        Returns:
            InstructionMatchResult với matched instructions, context, và SQL conditions.
        """
        matched = []

        for inst, patterns in self._compiled:
            # Global instructions luôn match
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
                "Áp dụng các quy tắc sau khi sinh SQL:\n"
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
        Tạo InstructionMatcher từ glossary terms.
        
        Mỗi glossary term trở thành một instruction hint.
        """
        # Sẽ integrate với BusinessGlossary sau
        return cls()
