"""
Ask Pipeline - Full pipeline từ câu hỏi → SQL → kết quả.

UPGRADED ARCHITECTURE (SOTA Text-to-SQL):
  question → intent → retrieve → schema link → column prune
    → context build → glossary inject → CoT reason
    → multi-candidate generate → execution vote → correct → memory save → result

Components:
  - IntentClassifier: phân loại câu hỏi (giữ nguyên)
  - SchemaRetriever: vector search + relationship expansion (giữ nguyên)
  - SchemaLinker: explicit entity→table/column mapping (NEW)
  - ColumnPruner: LLM-based column pruning (NEW)
  - ContextBuilder: build DDL (giữ nguyên)
  - BusinessGlossary: inject business terms context (NEW)
  - SQLReasoner: CoT reasoning plan (NEW)
  - CandidateGenerator: multi-candidate generation (NEW)
  - ExecutionVoter: execution-based voting (NEW)
  - SQLCorrector: validate + auto-correct (giữ nguyên)
  - SemanticMemory: save execution traces (NEW)
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy

from src.config import settings
from src.modeling.mdl_schema import Manifest
from src.indexing.schema_indexer import SchemaIndexer
from src.indexing.embedder import HuggingFaceEmbedder
from src.indexing.vector_store import VectorStore
from src.retrieval.schema_retriever import SchemaRetriever
from src.retrieval.context_builder import ContextBuilder
from src.retrieval.schema_linker import SchemaLinker
from src.retrieval.column_pruner import ColumnPruner
from src.retrieval.business_glossary import BusinessGlossary
from src.generation.llm_client import LLMClient
from src.generation.intent_classifier import IntentClassifier, Intent
from src.generation.sql_generator import SQLGenerator
from src.generation.sql_reasoner import SQLReasoner
from src.generation.sql_rewriter import SQLRewriter
from src.generation.sql_corrector import SQLCorrector
from src.generation.candidate_generator import CandidateGenerator
from src.generation.execution_voter import ExecutionVoter
from src.generation.semantic_memory import SemanticMemory

logger = logging.getLogger(__name__)


@dataclass
class AskResult:
    """Kết quả từ Ask Pipeline."""
    question: str
    intent: str
    sql: str = ""                      # SQL cuối (DB names)
    original_sql: str = ""             # SQL gốc (model names)
    explanation: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    valid: bool = False
    retries: int = 0
    error: str = ""
    models_used: list[str] = field(default_factory=list)
    # NEW: Advanced pipeline metadata
    reasoning_steps: list[str] = field(default_factory=list)
    schema_links: dict = field(default_factory=dict)
    columns_pruned: int = 0
    candidates_generated: int = 0
    voting_method: str = ""
    glossary_matches: int = 0
    similar_traces: int = 0
    active_features: dict = field(default_factory=dict)


class AskPipeline:
    """
    Full upgraded pipeline: question → SQL → data.

    Kiến trúc SOTA với CoT reasoning, schema linking,
    column pruning, multi-candidate voting, and semantic memory.
    """

    def __init__(
        self,
        manifest: Manifest,
        indexer: SchemaIndexer,
        engine: sqlalchemy.Engine,
        # NEW: Advanced pipeline settings
        num_candidates: int = 3,
        enable_column_pruning: bool = True,
        enable_cot_reasoning: bool = True,
        enable_schema_linking: bool = True,
        enable_voting: bool = True,
        enable_glossary: bool = True,
        enable_memory: bool = True,
        glossary_path: str = "",
        memory_path: str = "semantic_memory.json",
    ):
        self._manifest = manifest
        self._indexer = indexer
        self._engine = engine

        # Feature flags
        self._enable_column_pruning = enable_column_pruning
        self._enable_cot_reasoning = enable_cot_reasoning
        self._enable_schema_linking = enable_schema_linking
        self._enable_voting = enable_voting
        self._enable_glossary = enable_glossary
        self._enable_memory = enable_memory
        self._num_candidates = num_candidates

        # Init all components
        self._llm = LLMClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self._retriever = SchemaRetriever(indexer, manifest)
        self._context_builder = ContextBuilder(manifest)
        self._classifier = IntentClassifier(self._llm)
        self._generator = SQLGenerator(self._llm)
        self._rewriter = SQLRewriter(manifest)
        self._corrector = SQLCorrector(self._llm, self._rewriter, engine)

        # NEW components
        self._schema_linker = SchemaLinker(self._llm)
        self._column_pruner = ColumnPruner(self._llm)
        self._reasoner = SQLReasoner(self._llm)
        self._candidate_gen = CandidateGenerator(self._llm, num_candidates)
        self._voter = ExecutionVoter(engine, self._rewriter)
        self._glossary = BusinessGlossary(glossary_path)
        self._memory = SemanticMemory(memory_path)

        logger.info(
            f"AskPipeline initialized (upgraded): "
            f"candidates={num_candidates}, "
            f"pruning={enable_column_pruning}, "
            f"cot={enable_cot_reasoning}, "
            f"schema_link={enable_schema_linking}, "
            f"voting={enable_voting}, "
            f"glossary={enable_glossary} ({self._glossary.term_count} terms), "
            f"memory={enable_memory} ({self._memory.trace_count} traces)"
        )

    def ask(self, question: str, overrides: dict | None = None) -> AskResult:
        """
        Chạy full upgraded pipeline.

        Args:
            question: Câu hỏi user.
            overrides: Per-request feature toggles (override config defaults).
                Keys: enable_schema_linking, enable_column_pruning,
                      enable_cot_reasoning, enable_voting,
                      enable_glossary, enable_memory, num_candidates.
        """
        # Resolve effective flags: overrides > config defaults
        ov = overrides or {}
        use_schema_linking = ov.get("enable_schema_linking", self._enable_schema_linking)
        use_column_pruning = ov.get("enable_column_pruning", self._enable_column_pruning)
        use_cot_reasoning = ov.get("enable_cot_reasoning", self._enable_cot_reasoning)
        use_voting = ov.get("enable_voting", self._enable_voting)
        use_glossary = ov.get("enable_glossary", self._enable_glossary)
        use_memory = ov.get("enable_memory", self._enable_memory)
        num_candidates = ov.get("num_candidates", self._num_candidates)

        active_features = {
            "schema_linking": use_schema_linking,
            "column_pruning": use_column_pruning,
            "cot_reasoning": use_cot_reasoning,
            "voting": use_voting and num_candidates > 1,
            "glossary": use_glossary,
            "memory": use_memory,
            "num_candidates": num_candidates,
        }
        logger.info(f"Active features: {active_features}")

        model_names = [m.name for m in self._manifest.models]

        try:
            # ── Step 1: Intent Classification ──
            logger.info(f"[1/12] Classifying intent: {question}")
            intent_result = self._classifier.classify(question, model_names)

            if intent_result.intent == Intent.GENERAL:
                return AskResult(
                    question=question,
                    intent=intent_result.intent.value,
                    error="Câu hỏi không liên quan đến dữ liệu. Tôi chỉ hỗ trợ truy vấn dữ liệu.",
                    active_features=active_features,
                )

            if intent_result.intent == Intent.AMBIGUOUS:
                return AskResult(
                    question=question,
                    intent=intent_result.intent.value,
                    error=f"Câu hỏi chưa rõ ràng. {intent_result.reason}",
                    active_features=active_features,
                )

            # ── Step 2: Schema Retrieval ──
            logger.info("[2/12] Retrieving schema context...")
            retrieval = self._retriever.retrieve(question)

            # ── Step 3: Schema Linking (NEW) ──
            schema_hints = ""
            schema_links_info = {}
            if use_schema_linking:
                logger.info("[3/12] Schema linking...")
                # Build preliminary DDL for linking
                prelim_ddl = self._context_builder.build(
                    retrieval.db_schemas, retrieval.model_names
                )
                link_result = self._schema_linker.link(question, prelim_ddl)
                schema_hints = link_result.context_hints
                schema_links_info = {
                    "entity_links": [
                        {"mention": e.mention, "table": e.table, "column": e.column}
                        for e in link_result.entity_links
                    ],
                    "value_links": [
                        {"mention": v.mention, "table": v.table, "column": v.column}
                        for v in link_result.value_links
                    ],
                    "ambiguities": link_result.ambiguities,
                }
            else:
                logger.info("[3/12] Schema linking SKIPPED")

            # ── Step 4: Column Pruning (NEW) ──
            columns_pruned = 0
            if use_column_pruning:
                logger.info("[4/12] Column pruning...")
                total_before = sum(
                    len(s.get("columns", [])) for s in retrieval.db_schemas
                )
                pruned_schemas = self._column_pruner.prune(
                    question, retrieval.db_schemas
                )
                total_after = sum(
                    len(s.get("columns", [])) for s in pruned_schemas
                )
                columns_pruned = total_before - total_after
            else:
                logger.info("[4/12] Column pruning SKIPPED")
                pruned_schemas = retrieval.db_schemas

            # ── Step 5: Context Building ──
            logger.info("[5/12] Building DDL context...")
            ddl = self._context_builder.build(
                pruned_schemas, retrieval.model_names
            )

            # ── Step 6: Business Glossary Injection (NEW) ──
            glossary_context = ""
            glossary_match_count = 0
            if use_glossary:
                logger.info("[6/12] Glossary lookup...")
                matches = self._glossary.lookup(question)
                glossary_match_count = len(matches)
                glossary_context = self._glossary.build_context(matches)
            else:
                logger.info("[6/12] Glossary SKIPPED")

            # ── Step 7: Semantic Memory Lookup (NEW) ──
            memory_context = ""
            similar_trace_count = 0
            if use_memory:
                logger.info("[7/12] Semantic memory lookup...")
                similar = self._memory.find_similar(question)
                similar_trace_count = len(similar)
                memory_context = self._memory.build_context(similar)
            else:
                logger.info("[7/12] Semantic memory SKIPPED")

            # ── Step 8: CoT Reasoning (NEW) ──
            reasoning_plan = ""
            reasoning_steps = []
            if use_cot_reasoning:
                logger.info("[8/12] CoT reasoning...")
                reasoning = self._reasoner.reason(question, ddl)
                reasoning_plan = reasoning.reasoning_text
                reasoning_steps = reasoning.steps
            else:
                logger.info("[8/12] CoT reasoning SKIPPED")

            # Combine all context enrichments
            enriched_ddl = ddl
            if glossary_context:
                enriched_ddl = f"{glossary_context}\n\n{enriched_ddl}"
            if memory_context:
                enriched_ddl = f"{memory_context}\n\n{enriched_ddl}"

            # ── Step 9+10: Multi-Candidate Generation + Voting (NEW) ──
            if use_voting and num_candidates > 1:
                logger.info(
                    f"[9-10/12] Multi-candidate generation "
                    f"({num_candidates} candidates) + voting..."
                )
                # Update candidate generator count
                self._candidate_gen._num_candidates = num_candidates
                candidate_set = self._candidate_gen.generate(
                    question=question,
                    ddl_context=enriched_ddl,
                    reasoning_plan=reasoning_plan,
                    schema_hints=schema_hints,
                )

                candidates_generated = len(candidate_set.candidates)

                if candidates_generated > 0:
                    vote_result = self._voter.vote(candidate_set)

                    # Use voted result
                    best_sql = vote_result.best_candidate.sql
                    best_explanation = vote_result.best_candidate.explanation
                    voting_method = vote_result.voting_method

                    # Nếu voting result đã success → skip correction
                    if (vote_result.execution_result and
                            vote_result.execution_result.success):
                        logger.info("[11/12] Voting succeeded → skip correction")
                        exec_r = vote_result.execution_result
                        result = AskResult(
                            question=question,
                            intent=intent_result.intent.value,
                            sql=vote_result.best_sql_rewritten,
                            original_sql=best_sql,
                            explanation=best_explanation,
                            columns=exec_r.columns,
                            rows=exec_r.rows,
                            row_count=exec_r.row_count,
                            valid=True,
                            retries=0,
                            models_used=retrieval.model_names,
                            reasoning_steps=reasoning_steps,
                            schema_links=schema_links_info,
                            columns_pruned=columns_pruned,
                            candidates_generated=candidates_generated,
                            voting_method=voting_method,
                            glossary_matches=glossary_match_count,
                            similar_traces=similar_trace_count,
                            active_features=active_features,
                        )

                        # ── Step 12: Semantic Memory Save ──
                        self._save_memory(
                            question, best_sql, True,
                            exec_r.result_hash,
                            retrieval.model_names,
                        )

                        return result

                    # Voting chose a candidate but it failed → go to correction
                    logger.info("[11/12] Voting candidate failed → correction loop")
                else:
                    # No candidates → fallback to single generation
                    logger.warning("No candidates generated → fallback")
                    best_sql = ""
                    best_explanation = ""
                    voting_method = "fallback"
                    candidates_generated = 0
            else:
                # Single-pass generation (compatibility mode)
                logger.info("[9-10/12] Single-pass generation (voting disabled)...")
                gen_result = self._generator.generate(
                    question, enriched_ddl
                )
                best_sql = gen_result.sql
                best_explanation = gen_result.explanation
                voting_method = "single"
                candidates_generated = 1

            if not best_sql:
                return AskResult(
                    question=question,
                    intent=intent_result.intent.value,
                    error="Không thể sinh SQL cho câu hỏi này.",
                    models_used=retrieval.model_names,
                    active_features=active_features,
                )

            # ── Step 11: SQL Correction ──
            logger.info("[11/12] Validating and correcting SQL...")
            correction = self._corrector.validate_and_correct(
                sql=best_sql,
                ddl_context=enriched_ddl,
                question=question,
                explanation=best_explanation,
            )

            # ── Step 12: Semantic Memory Save ──
            result_hash = ""
            if correction.valid and correction.result:
                import hashlib, json
                content = json.dumps(correction.result, default=str)
                result_hash = hashlib.md5(content.encode()).hexdigest()

            self._save_memory(
                question, best_sql, correction.valid,
                result_hash, retrieval.model_names,
                correction.errors[0] if correction.errors else "",
                correction.retries,
            )

            # Build result
            result = AskResult(
                question=question,
                intent=intent_result.intent.value,
                sql=correction.sql,
                original_sql=best_sql,
                explanation=best_explanation,
                valid=correction.valid,
                retries=correction.retries,
                models_used=retrieval.model_names,
                reasoning_steps=reasoning_steps,
                schema_links=schema_links_info,
                columns_pruned=columns_pruned,
                candidates_generated=candidates_generated,
                voting_method=voting_method,
                glossary_matches=glossary_match_count,
                similar_traces=similar_trace_count,
                active_features=active_features,
            )

            if correction.valid and correction.result:
                result.columns = correction.result.get("columns", [])
                result.rows = correction.result.get("rows", [])
                result.row_count = correction.result.get("row_count", 0)
            elif not correction.valid:
                errors = "; ".join(correction.errors) if correction.errors else "Unknown"
                result.error = f"SQL validation failed after {correction.retries} retries: {errors}"

            return result

        except Exception as e:
            logger.error(f"Ask pipeline failed: {e}", exc_info=True)
            return AskResult(
                question=question,
                intent="ERROR",
                error=str(e),
                active_features=active_features if 'active_features' in dir() else {},
            )

    def _save_memory(
        self,
        question: str,
        sql: str,
        success: bool,
        result_hash: str = "",
        models_used: list[str] | None = None,
        error: str = "",
        retries: int = 0,
    ) -> None:
        """Save trace to semantic memory (if enabled)."""
        if not self._enable_memory:
            return
        try:
            self._memory.save_trace(
                question=question,
                sql=sql,
                success=success,
                result_hash=result_hash,
                models_used=models_used,
                error=error,
                retries=retries,
            )
        except Exception as e:
            logger.warning(f"Failed to save memory trace: {e}")
