"""
Ask Pipeline - Full pipeline từ câu hỏi → SQL → kết quả.

UPGRADED ARCHITECTURE (Multi-Stage Intent + Guardian):
  question → pre-filter → instruction match → intent classify
    → sub-intent → retrieve → schema link → column prune
    → context build → glossary inject → CoT reason
    → multi-candidate generate → execution vote → correct
    → guardian validate → memory save → result

New Components (Multi-Stage Intent + Security):
  - PreFilter: regex/keyword pre-filter (NO LLM, instant)
  - InstructionMatcher: business rules injection (NO LLM)
  - SubIntentDetector: RETRIEVAL/AGGREGATION/TREND/RANKING/etc.
  - SchemaExplorer: answer schema questions from manifest (NO SQL)
  - SQLGuardian: 5-layer SQL security validation

Existing Components:
  - IntentClassifier, SchemaRetriever, SchemaLinker, ColumnPruner
  - ContextBuilder, BusinessGlossary, SQLReasoner
  - CandidateGenerator, ExecutionVoter, SQLCorrector, SemanticMemory
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
# NEW: Multi-Stage Intent + Guardian
from src.generation.pre_filter import PreFilter, PreFilterResult
from src.generation.instruction_matcher import InstructionMatcher
from src.generation.sub_intent import SubIntentDetector, SubIntent
from src.generation.schema_explorer import SchemaExplorer
from src.security.guardian import SQLGuardian

# Debug Tracer
from src.pipelines.tracer import PipelineTracer

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
    # NEW: Multi-stage intent metadata
    sub_intent: str = ""
    sub_intent_hints: str = ""
    instructions_matched: int = 0
    guardian_passed: bool = True
    pre_filter_result: str = ""

    # Debug trace
    debug_trace: dict = field(default_factory=dict)


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

        # Multi-Stage Intent + Guardian
        self._pre_filter = PreFilter()
        self._instruction_matcher = InstructionMatcher()
        self._sub_intent_detector = SubIntentDetector(self._llm)
        self._schema_explorer = SchemaExplorer(manifest)
        self._guardian = SQLGuardian.from_config("src/security/guardian.yaml")
        self._guardian.config.set_allowed_tables_from_manifest(manifest)



        logger.info(
            f"AskPipeline initialized (upgraded + guardian): "
            f"candidates={num_candidates}, "
            f"pruning={enable_column_pruning}, "
            f"cot={enable_cot_reasoning}, "
            f"schema_link={enable_schema_linking}, "
            f"voting={enable_voting}, "
            f"glossary={enable_glossary} ({self._glossary.term_count} terms), "
            f"memory={enable_memory} ({self._memory.trace_count} traces)"
        )

    def ask(self, question: str, overrides: dict | None = None, debug: bool = False) -> AskResult:
        """
        Chạy full upgraded pipeline.

        Args:
            question: Câu hỏi user.
            overrides: Per-request feature toggles (override config defaults).
            debug: Bật debug trace để xem input/output từng stage.
        """
        # Debug tracer
        tracer = PipelineTracer(enabled=debug)

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
            # ── Stage 1: Pre-Filter (NO LLM — instant) ──
            tracer.start("Stage 1: PreFilter")
            tracer.log_input({"question": question})
            logger.info(f"[1/14] Pre-filtering: {question}")
            pre_filter = self._pre_filter.filter(question)
            tracer.log_output({"result": pre_filter.result.value, "response": pre_filter.response})
            tracer.end()

            if pre_filter.result == PreFilterResult.GREETING:
                r = AskResult(question=question, intent="GREETING", explanation=pre_filter.response, valid=True, pre_filter_result="GREETING", active_features=active_features, debug_trace=tracer.to_dict())
                return r

            if pre_filter.result == PreFilterResult.OUT_OF_SCOPE:
                r = AskResult(question=question, intent="GENERAL", error=pre_filter.response, pre_filter_result="OUT_OF_SCOPE", active_features=active_features, debug_trace=tracer.to_dict())
                return r

            if pre_filter.result == PreFilterResult.DESTRUCTIVE:
                logger.info("[1/14] Pre-filter → DESTRUCTIVE (blocked, 0 LLM calls)")
                r = AskResult(question=question, intent="DESTRUCTIVE", error=pre_filter.response, pre_filter_result="DESTRUCTIVE", guardian_passed=False, active_features=active_features, debug_trace=tracer.to_dict())
                return r

            if pre_filter.result == PreFilterResult.SCHEMA_EXPLORE:
                logger.info("[1/14] Pre-filter → SCHEMA_EXPLORE (skipping LLM)")
                schema_answer = self._schema_explorer.explore(question)
                r = AskResult(question=question, intent="SCHEMA_EXPLORE", explanation=schema_answer.answer, models_used=schema_answer.tables_mentioned, valid=True, pre_filter_result="SCHEMA_EXPLORE", active_features=active_features, debug_trace=tracer.to_dict())
                return r

            # ── Stage 2: Instruction Match (NO LLM) ──
            tracer.start("Stage 2: InstructionMatch")
            logger.info("[2/14] Matching instructions...")
            instr_result = self._instruction_matcher.match(question)
            instructions_matched = len(instr_result.matched_instructions)
            tracer.log_output({"matched": instructions_matched, "context": instr_result.context_text[:200] if instr_result.context_text else ""})
            tracer.end()

            # ── Stage 3: Intent Classification (LLM) ──
            tracer.start("Stage 3: IntentClassifier")
            tracer.log_input({"question": question, "models": model_names})
            logger.info(f"[3/14] Classifying intent: {question}")
            intent_result = self._classifier.classify(question, model_names)
            tracer.log_output({"intent": intent_result.intent.value, "reason": intent_result.reason})
            tracer.end()

            if intent_result.intent == Intent.SCHEMA_EXPLORE:
                schema_answer = self._schema_explorer.explore(question)
                r = AskResult(question=question, intent="SCHEMA_EXPLORE", explanation=schema_answer.answer, models_used=schema_answer.tables_mentioned, valid=True, instructions_matched=instructions_matched, active_features=active_features, debug_trace=tracer.to_dict())
                return r

            if intent_result.intent == Intent.GENERAL:
                r = AskResult(question=question, intent=intent_result.intent.value, error="Câu hỏi không liên quan đến dữ liệu. Tôi chỉ hỗ trợ truy vấn dữ liệu.", active_features=active_features, debug_trace=tracer.to_dict())
                return r

            if intent_result.intent == Intent.AMBIGUOUS:
                r = AskResult(question=question, intent=intent_result.intent.value, error=f"Câu hỏi chưa rõ ràng. {intent_result.reason}", active_features=active_features, debug_trace=tracer.to_dict())
                return r

            # ── Stage 4: Sub-Intent Detection ──
            tracer.start("Stage 4: SubIntentDetect")
            logger.info("[4/16] Detecting sub-intent...")
            sub_intent_result = self._sub_intent_detector.detect(question)
            tracer.log_output({"sub_intent": sub_intent_result.sub_intent.value, "confidence": sub_intent_result.confidence, "sql_hints": sub_intent_result.sql_hints})
            tracer.end()

            # ── Step 5: Schema Retrieval ──
            tracer.start("Stage 5: SchemaRetrieval")
            tracer.log_input({"question": question})
            logger.info("[5/16] Retrieving schema context...")
            retrieval = self._retriever.retrieve(question)
            tracer.log_output({
                "models_found": retrieval.model_names,
                "schemas_count": len(retrieval.db_schemas),
                "total_columns": sum(len(s.get("columns", [])) for s in retrieval.db_schemas),
            })
            tracer.end()

            # ── Step 6: Schema Linking ──
            schema_hints = ""
            schema_links_info = {}
            if use_schema_linking:
                tracer.start("Stage 6: SchemaLinking")
                logger.info("[6/14] Schema linking...")
                prelim_ddl = self._context_builder.build(
                    retrieval.db_schemas, retrieval.model_names
                )
                link_result = self._schema_linker.link(question, prelim_ddl)
                schema_hints = link_result.context_hints
                schema_links_info = {
                    "entity_links": [{"mention": e.mention, "table": e.table, "column": e.column} for e in link_result.entity_links],
                    "value_links": [{"mention": v.mention, "table": v.table, "column": v.column} for v in link_result.value_links],
                    "ambiguities": link_result.ambiguities,
                }
                tracer.log_output({"entity_links": len(link_result.entity_links), "value_links": len(link_result.value_links), "hints": schema_hints[:150]})
                tracer.end()
            else:
                tracer.skip("Stage 6: SchemaLinking", "disabled")
                logger.info("[6/14] Schema linking SKIPPED")

            # ── Step 7: Column Pruning ──
            columns_pruned = 0
            if use_column_pruning:
                tracer.start("Stage 7: ColumnPruning")
                logger.info("[7/14] Column pruning...")
                total_before = sum(len(s.get("columns", [])) for s in retrieval.db_schemas)
                pruned_schemas = self._column_pruner.prune(question, retrieval.db_schemas)
                total_after = sum(len(s.get("columns", [])) for s in pruned_schemas)
                columns_pruned = total_before - total_after
                tracer.log_output({"before": total_before, "after": total_after, "pruned": columns_pruned})
                tracer.end()
            else:
                tracer.skip("Stage 7: ColumnPruning", "disabled")
                logger.info("[7/14] Column pruning SKIPPED")
                pruned_schemas = retrieval.db_schemas

            # ── Step 8: Context Building ──
            tracer.start("Stage 8: ContextBuilder")
            logger.info("[8/14] Building DDL context...")
            ddl = self._context_builder.build(pruned_schemas, retrieval.model_names)
            tracer.log_output({"ddl_length": len(ddl)})
            tracer.end()

            # ── Step 9: Business Glossary Injection ──
            glossary_context = ""
            glossary_match_count = 0
            if use_glossary:
                tracer.start("Stage 9: GlossaryLookup")
                logger.info("[9/14] Glossary lookup...")
                matches = self._glossary.lookup(question)
                glossary_match_count = len(matches)
                glossary_context = self._glossary.build_context(matches)
                tracer.log_output({"matches": glossary_match_count, "context": glossary_context[:100]})
                tracer.end()
            else:
                tracer.skip("Stage 9: GlossaryLookup", "disabled")
                logger.info("[9/14] Glossary SKIPPED")

            # ── Step 10: Semantic Memory Lookup ──
            memory_context = ""
            similar_trace_count = 0
            if use_memory:
                tracer.start("Stage 10: SemanticMemory")
                logger.info("[10/14] Semantic memory lookup...")
                similar = self._memory.find_similar(question)
                similar_trace_count = len(similar)
                memory_context = self._memory.build_context(similar)
                tracer.log_output({"similar_traces": similar_trace_count, "context": memory_context[:100]})
                tracer.end()
            else:
                tracer.skip("Stage 10: SemanticMemory", "disabled")
                logger.info("[10/14] Semantic memory SKIPPED")

            # ── Step 11: CoT Reasoning ──
            reasoning_plan = ""
            reasoning_steps = []
            if use_cot_reasoning:
                tracer.start("Stage 11: CoTReasoning")
                logger.info("[11/14] CoT reasoning...")
                reasoning = self._reasoner.reason(question, ddl)
                reasoning_plan = reasoning.reasoning_text
                reasoning_steps = reasoning.steps
                tracer.log_output({"steps": reasoning_steps, "plan_length": len(reasoning_plan)})
                tracer.end()
            else:
                tracer.skip("Stage 11: CoTReasoning", "disabled")
                logger.info("[11/14] CoT reasoning SKIPPED")

            # Combine all context enrichments (incl. instructions + sub-intent)
            enriched_ddl = ddl
            if instr_result.context_text:
                enriched_ddl = f"{instr_result.context_text}\n\n{enriched_ddl}"
            if sub_intent_result.sql_hints:
                enriched_ddl = f"## SQL Hints\n{sub_intent_result.sql_hints}\n\n{enriched_ddl}"
            if glossary_context:
                enriched_ddl = f"{glossary_context}\n\n{enriched_ddl}"
            if memory_context:
                enriched_ddl = f"{memory_context}\n\n{enriched_ddl}"

            # ── Step 12: Multi-Candidate Generation + Voting ──
            tracer.start("Stage 12: SQLGeneration")
            if use_voting and num_candidates > 1:
                logger.info(f"[12/14] Multi-candidate generation ({num_candidates} candidates) + voting...")
                self._candidate_gen._num_candidates = num_candidates
                candidate_set = self._candidate_gen.generate(
                    question=question, ddl_context=enriched_ddl,
                    reasoning_plan=reasoning_plan, schema_hints=schema_hints,
                )
                candidates_generated = len(candidate_set.candidates)
                tracer.log_input({"mode": "multi-candidate", "num_candidates": num_candidates})

                if candidates_generated > 0:
                    # Log per-candidate details
                    candidate_details = [
                        {"strategy": c.strategy, "temperature": c.temperature, "sql": c.sql[:120]}
                        for c in candidate_set.candidates
                    ]

                    vote_result = self._voter.vote(candidate_set)
                    best_sql = vote_result.best_candidate.sql
                    best_explanation = vote_result.best_candidate.explanation
                    voting_method = vote_result.voting_method
                    tracer.log_output({
                        "candidates": candidates_generated,
                        "candidate_details": candidate_details,
                        "voting_method": voting_method,
                        "successful_executions": vote_result.successful_candidates,
                        "vote_distribution": vote_result.vote_distribution,
                        "best_strategy": vote_result.best_candidate.strategy,
                        "best_sql": best_sql,
                    })
                    tracer.end()

                    if (vote_result.execution_result and vote_result.execution_result.success):
                        logger.info("[13/14] Voting succeeded → skip correction")
                        exec_r = vote_result.execution_result
                        result = AskResult(
                            question=question, intent=intent_result.intent.value,
                            sql=vote_result.best_sql_rewritten, original_sql=best_sql,
                            explanation=best_explanation, columns=exec_r.columns,
                            rows=exec_r.rows, row_count=exec_r.row_count,
                            valid=True, retries=0, models_used=retrieval.model_names,
                            reasoning_steps=reasoning_steps, schema_links=schema_links_info,
                            columns_pruned=columns_pruned, candidates_generated=candidates_generated,
                            voting_method=voting_method, glossary_matches=glossary_match_count,
                            similar_traces=similar_trace_count, active_features=active_features,
                            debug_trace=tracer.to_dict(),
                        )
                        self._save_memory(question, best_sql, True, exec_r.result_hash, retrieval.model_names)
                        return result

                    logger.info("[13/14] Voting candidate failed → correction loop")
                else:
                    logger.warning("No candidates generated → fallback")
                    best_sql = ""; best_explanation = ""; voting_method = "fallback"; candidates_generated = 0
                    tracer.log_output({"candidates": 0, "fallback": True})
                    tracer.end()
            else:
                logger.info("[12/14] Single-pass generation (voting disabled)...")
                tracer.log_input({"mode": "single-pass"})
                gen_result = self._generator.generate(question, enriched_ddl)
                best_sql = gen_result.sql
                best_explanation = gen_result.explanation
                voting_method = "single"; candidates_generated = 1
                tracer.log_output({"sql": best_sql, "explanation": best_explanation})
                tracer.end()

            if not best_sql:
                return AskResult(
                    question=question,
                    intent=intent_result.intent.value,
                    error="Không thể sinh SQL cho câu hỏi này.",
                    models_used=retrieval.model_names,
                    active_features=active_features,
                    debug_trace=tracer.to_dict(),
                )

            # ── Step 13: SQL Correction ──
            tracer.start("Stage 13: SQLCorrection")
            tracer.log_input({"input_sql": best_sql[:200], "explanation": best_explanation[:100]})
            logger.info("[13/14] Validating and correcting SQL...")
            correction = self._corrector.validate_and_correct(
                sql=best_sql, ddl_context=enriched_ddl,
                question=question, explanation=best_explanation,
            )
            tracer.log_output({
                "valid": correction.valid,
                "retries": correction.retries,
                "final_sql": correction.sql,
                "original_sql": correction.original_sql[:120] if correction.original_sql else "",
                "sql_changed": correction.sql != self._rewriter.rewrite(best_sql),
                "error_details": [e[:150] for e in correction.errors] if correction.errors else [],
                "has_result": correction.result is not None,
                "row_count": correction.result.get("row_count", 0) if correction.result else 0,
            })
            tracer.end()

            # ── Step 13.5: SQL Guardian Validation ──
            tracer.start("Stage 13.5: Guardian")
            guardian_passed = True
            if correction.valid and correction.sql:
                logger.info("[13.5/14] SQL Guardian validating...")
                guardian_result = self._guardian.validate(correction.sql)
                guardian_passed = guardian_result.safe
                tracer.log_output({"safe": guardian_result.safe, "reason": guardian_result.reason, "blocked_by": guardian_result.blocked_by})
                tracer.end()
                if not guardian_result.safe:
                    logger.warning(f"Guardian BLOCKED: {guardian_result.reason} (blocked_by={guardian_result.blocked_by})")
                    r = AskResult(question=question, intent=intent_result.intent.value, error=f"SQL blocked by security guardian: {guardian_result.reason}", sql=correction.sql, original_sql=best_sql, models_used=retrieval.model_names, guardian_passed=False, active_features=active_features, debug_trace=tracer.to_dict())
                    return r
                if guardian_result.sql != correction.sql:
                    logger.info("Guardian modified SQL (masking/RLS applied)")
                    correction.sql = guardian_result.sql
            else:
                tracer.log_output({"skipped": True, "reason": "correction invalid"})
                tracer.end()

            # ── Step 14: Semantic Memory Save ──
            tracer.start("Stage 14: MemorySave")
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
            tracer.log_output({"saved": True, "result_hash": result_hash})
            tracer.end()

            # Build result
            result = AskResult(
                question=question, intent=intent_result.intent.value,
                sql=correction.sql, original_sql=best_sql,
                explanation=best_explanation, valid=correction.valid,
                retries=correction.retries, models_used=retrieval.model_names,
                reasoning_steps=reasoning_steps, schema_links=schema_links_info,
                columns_pruned=columns_pruned, candidates_generated=candidates_generated,
                voting_method=voting_method, glossary_matches=glossary_match_count,
                similar_traces=similar_trace_count, active_features=active_features,
                sub_intent=sub_intent_result.sub_intent.value,
                sub_intent_hints=sub_intent_result.sql_hints,
                instructions_matched=instructions_matched,
                guardian_passed=guardian_passed,
                debug_trace=tracer.to_dict(),
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
                debug_trace=tracer.to_dict() if 'tracer' in dir() else {},
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
