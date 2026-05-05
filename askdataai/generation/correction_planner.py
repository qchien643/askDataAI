"""CorrectionPlanner — Sprint 5.

Given a failed SQL + execution error + DDL context, classify the failure
into a structured taxonomy (askdataai/generation/error_taxonomy.yaml) and
produce a concrete repair strategy.

Inspired by SQL-of-Thought (arXiv 2509.00581) — taxonomy-guided correction
outperforms execution-only retry by ~5-8% EX accuracy on Spider, primarily
because 95-99% of failed SQL is syntactically valid; the issues are LOGICAL.

Usage:
    planner = CorrectionPlanner(llm, taxonomy_path)
    plan = planner.plan(question, sql, error, ddl_context)
    # plan.category, plan.sub_category, plan.root_cause, plan.repair_strategy
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_TAXONOMY_PATH = Path(__file__).parent / "error_taxonomy.yaml"


@dataclass
class CorrectionPlan:
    """Output of taxonomy-guided diagnosis."""
    category: str               # e.g. "schema_linking"
    sub_category: str           # e.g. "nonexistent_column"
    root_cause: str             # 1-sentence natural-language explanation
    repair_strategy: str        # specific fix instruction
    confidence: float = 0.0     # LLM's self-reported confidence
    error: str = ""             # populated if planner itself failed


_SYSTEM_PROMPT = """You are an expert T-SQL debugger.

Given:
1. The user's question
2. The DDL schema available
3. A failed SQL query
4. The execution error from SQL Server
5. A taxonomy of common error categories

Your task: classify the failure into the taxonomy and propose a SPECIFIC repair strategy that the next agent will apply.

Rules:
- Pick exactly ONE category and ONE sub_category from the taxonomy
- root_cause: explain in 1 sentence WHY the SQL failed (not what the error literally says — explain semantically)
- repair_strategy: a SPECIFIC instruction. Reference exact column names, table names, values from the schema. Avoid generic advice.
- confidence: 0.0-1.0, your certainty in the diagnosis

Output STRICT JSON only:
{
  "category": "<one of taxonomy categories>",
  "sub_category": "<one of taxonomy sub_categories>",
  "root_cause": "<1 sentence>",
  "repair_strategy": "<specific instruction>",
  "confidence": 0.0
}
"""


class CorrectionPlanner:
    """Diagnose SQL failures via LLM + structured taxonomy."""

    def __init__(
        self,
        llm: LLMClient,
        taxonomy_path: str | Path = DEFAULT_TAXONOMY_PATH,
    ):
        self._llm = llm
        self._taxonomy = self._load_taxonomy(taxonomy_path)
        self._taxonomy_text = self._format_taxonomy_for_prompt()
        self._valid_categories = set(self._taxonomy.get("categories", {}).keys())
        self._valid_subcats: dict[str, set[str]] = {
            cat: {item["id"] for item in info.get("items", [])}
            for cat, info in self._taxonomy.get("categories", {}).items()
        }

    def _load_taxonomy(self, path: str | Path) -> dict:
        try:
            return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load taxonomy from {path}: {e}")
            return {"categories": {}}

    def _format_taxonomy_for_prompt(self) -> str:
        """Render taxonomy as compact text for LLM prompt."""
        lines = ["# Error Taxonomy"]
        for cat_name, cat_info in self._taxonomy.get("categories", {}).items():
            lines.append(f"\n## {cat_name} — {cat_info.get('label', '')}")
            for item in cat_info.get("items", []):
                lines.append(f"  - {item['id']}: {item['description']}")
        return "\n".join(lines)

    def plan(
        self,
        question: str,
        sql: str,
        exec_error: str,
        ddl_context: str = "",
    ) -> CorrectionPlan:
        """Run 1 LLM call to classify failure and propose repair."""
        if not self._valid_categories:
            return CorrectionPlan(
                category="semantic_errors",
                sub_category="misinterpreted_intent",
                root_cause="taxonomy unavailable",
                repair_strategy="Re-analyze question and SQL; rewrite from scratch.",
                error="taxonomy_not_loaded",
            )

        user_prompt = f"""# Question
{question}

# DDL Schema
{ddl_context[:6000]}

# Failed SQL
```sql
{sql}
```

# Execution Error
{exec_error}

{self._taxonomy_text}

Diagnose the failure and propose a repair strategy. Output JSON."""

        try:
            result = self._llm.chat_json(
                user_prompt=user_prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.0,
            )
        except Exception as e:
            logger.error(f"CorrectionPlanner LLM call failed: {e}")
            return CorrectionPlan(
                category="semantic_errors",
                sub_category="misinterpreted_intent",
                root_cause=f"planner LLM error: {e}",
                repair_strategy="Re-analyze question; rewrite SQL from scratch using DDL.",
                error=str(e),
            )

        # Validate + normalize output
        cat = str(result.get("category", "")).strip()
        sub = str(result.get("sub_category", "")).strip()

        if cat not in self._valid_categories:
            logger.warning(f"Planner returned unknown category '{cat}', defaulting to semantic_errors")
            cat = "semantic_errors"
            sub = "misinterpreted_intent"
        elif sub not in self._valid_subcats.get(cat, set()):
            logger.warning(f"Planner returned unknown sub_category '{sub}' for '{cat}'")
            # Pick first sub_cat as fallback
            subs = self._valid_subcats.get(cat, set())
            sub = next(iter(subs)) if subs else ""

        return CorrectionPlan(
            category=cat,
            sub_category=sub,
            root_cause=str(result.get("root_cause", ""))[:500],
            repair_strategy=str(result.get("repair_strategy", ""))[:500],
            confidence=float(result.get("confidence", 0.0)),
        )
