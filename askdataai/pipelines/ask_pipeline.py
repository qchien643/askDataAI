"""
Ask Pipeline - Full pipeline từ câu hỏi → SQL → kết quả.

UPGRADED ARCHITECTURE (PIGuardrail + Multi-Stage Intent + Guardian):
  question
    → [Stage 0] PIGuardrail (leolee99/PIGuard — Prompt Injection detection)
    → [Stage 1] PreFilter (regex/keyword, NO LLM)
    → [Stage 2] InstructionMatcher (business rules, NO LLM)
    → [Stage 3] IntentClassifier (LLM)
    → [Stage 4] SubIntentDetector
    → [Stage 5–11] Schema retrieve → link → prune → context → glossary → memory → CoT
    → [Stage 12] Multi-candidate generate + Execution voting
    → [Stage 13] SQL Correction
    → [Stage 13.5] SQLGuardian (5-layer SQL security)
    → [Stage 14] Memory Save
    → result

Security Layers:
  - PIGuardrail (Stage 0): Prompt Injection detection (leolee99/PIGuard, ACL 2025)
  - PreFilter (Stage 1): Destructive/OOS/Greeting regex filter
  - SQLGuardian (Stage 13.5): SQL injection + read-only + table ACL + masking + RLS

New Components (Multi-Stage Intent + Security):
  - PIGuardrail: ML-based prompt injection guard (DeBERTa-v3-base fine-tuned)
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

from askdataai.config import settings
from askdataai.modeling.mdl_schema import Manifest
from askdataai.indexing.schema_indexer import SchemaIndexer
from askdataai.indexing.embedder import OpenAIEmbedder
from askdataai.indexing.vector_store import VectorStore
from askdataai.retrieval.schema_retriever import SchemaRetriever
from askdataai.retrieval.context_builder import ContextBuilder
from askdataai.retrieval.schema_linker import SchemaLinker
from askdataai.retrieval.column_pruner import ColumnPruner
from askdataai.retrieval.business_glossary import BusinessGlossary
from askdataai.retrieval.question_augmenter import QuestionAugmenter  # Sprint 4
from askdataai.generation.llm_client import LLMClient
from askdataai.generation.intent_classifier import IntentClassifier, Intent
from askdataai.generation.sql_generator import SQLGenerator
from askdataai.generation.sql_reasoner import SQLReasoner
from askdataai.generation.sql_rewriter import SQLRewriter
from askdataai.generation.sql_corrector import SQLCorrector
# Sprint 5 — taxonomy-guided correction
from askdataai.generation.correction_planner import CorrectionPlanner
from askdataai.generation.correction_fixer import CorrectionFixer
from askdataai.generation.candidate_generator import CandidateGenerator
from askdataai.generation.execution_voter import ExecutionVoter
from askdataai.generation.semantic_memory import SemanticMemory
from askdataai.generation.question_translator import QuestionTranslator
# NEW: Multi-Stage Intent + Guardian
from askdataai.generation.pre_filter import PreFilter, PreFilterResult
from askdataai.generation.instruction_matcher import InstructionMatcher
from askdataai.generation.sub_intent import SubIntentDetector, SubIntent
from askdataai.generation.schema_explorer import SchemaExplorer
from askdataai.security.guardian import SQLGuardian
# Stage 0: Prompt Injection Guardrail (leolee99/PIGuard — ACL 2025)
from askdataai.security.pi_guardrail import PIGuardrail, PIGuardResult
# Stage 0.5: Conversation Context Engine (Rolling Summary + 7 Recent Turns)
from askdataai.generation.conversation_context import ConversationContextEngine, EnrichResult

# Debug Tracer
from askdataai.pipelines.tracer import PipelineTracer

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
    # Stage 0: PIGuardrail metadata
    pi_guard_blocked: bool = False
    pi_guard_confidence: float = 0.0
    # Stage 0.5: Conversation Context metadata
    enriched_question: str = ""       # Câu hỏi sau khi LLM enrich (= question nếu không đổi)
    was_enriched: bool = False         # True nếu LLM thực sự thay đổi câu hỏi
    memories_used: list[str] = field(default_factory=list)
    session_id: str = ""
    # Stage 0.7: Question Translator metadata (VI → EN)
    original_question: str = ""        # Original input (Vietnamese or English)
    translated_question: str = ""      # English version used for downstream stages
    translation_skipped: bool = False  # True if input was already English

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
        memory_path: str = "data/semantic_memory.json",
        # Stage 0: PIGuardrail (Prompt Injection detection)
        enable_pi_guard: bool = True,
        pi_guard_threshold: float = 0.5,
        # Stage 0.5: Conversation Context (mem0 rolling memory)
        enable_conversation_context: bool = True,
        # Stage 0.7: Question Translator (VI → EN before downstream stages)
        enable_question_translator: bool = True,
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
        self._enable_question_translator = enable_question_translator
        self._num_candidates = num_candidates

        # Init all components
        self._llm = LLMClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        # Sprint 4: pass augmenter so SchemaRetriever can switch to bidirectional
        # when settings.enable_bidirectional_retrieval=True. Augmenter shares
        # the same LLMClient → no extra cost when toggle is OFF.
        self._augmenter = QuestionAugmenter(self._llm)
        self._retriever = SchemaRetriever(indexer, manifest, augmenter=self._augmenter)
        self._context_builder = ContextBuilder(manifest)
        self._classifier = IntentClassifier(self._llm)
        self._generator = SQLGenerator(self._llm)
        self._rewriter = SQLRewriter(manifest)
        # Sprint 5: instantiate planner+fixer; SQLCorrector picks them up only
        # when settings.correction_strategy="taxonomy_guided"
        self._correction_planner = CorrectionPlanner(self._llm)
        self._correction_fixer = CorrectionFixer(self._llm)
        self._corrector = SQLCorrector(
            self._llm, self._rewriter, engine,
            planner=self._correction_planner,
            fixer=self._correction_fixer,
        )

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

        # Stage 0: PIGuardrail — Prompt Injection detection (leolee99/PIGuard)
        self._pi_guard = PIGuardrail(
            enabled=enable_pi_guard,
            threshold=pi_guard_threshold,
        )

        # Stage 0.5: Conversation Context Engine (mem0)
        self._conv_ctx = ConversationContextEngine(
            llm_client=self._llm,
            enabled=enable_conversation_context,
        )

        # Stage 0.7: Question Translator (VI → EN)
        self._translator = QuestionTranslator(self._llm)

        logger.info(
            f"AskPipeline initialized (upgraded + guardian + PIGuardrail + ConvCtx): "
            f"candidates={num_candidates}, "
            f"pruning={enable_column_pruning}, "
            f"cot={enable_cot_reasoning}, "
            f"schema_link={enable_schema_linking}, "
            f"voting={enable_voting}, "
            f"glossary={enable_glossary} ({self._glossary.term_count} terms), "
            f"memory={enable_memory} ({self._memory.trace_count} traces), "
            f"pi_guard={enable_pi_guard} (threshold={pi_guard_threshold}), "
            f"conv_context={enable_conversation_context}"
        )

    def ask(
        self,
        question: str,
        overrides: dict | None = None,
        debug: bool = False,
        session_id: str = "",
        user_id: str = "default",
        on_progress: "Callable[[str, str], None] | None" = None,
        on_token: "Callable[[str, str], None] | None" = None,
    ) -> AskResult:
        """
        Chạy full upgraded pipeline.

        Args:
            question    : Câu hỏi user.
            overrides   : Per-request feature toggles (override config defaults).
            debug       : Bật debug trace để xem input/output từng stage.
            on_progress : Callback(stage_id, label) — gọi tại đầu mỗi stage để
                          SSE endpoint stream tiến độ về client.
            on_token    : Callback(stage, chunk) — gọi cho mỗi token stream từ
                          Stage 11 (CoT) và Stage 12 (SQL Generation).
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
        # Sprint 2-5 toggles — None means "fall back to settings singleton"
        use_mschema = ov.get("enable_mschema")
        use_bidirectional = ov.get("enable_bidirectional_retrieval")
        use_correction_strategy = ov.get("correction_strategy")

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
            # ── Stage 0: PIGuardrail — Prompt Injection Detection ──
            if on_progress: on_progress("0", "🛡 Kiểm tra bảo mật đầu vào...")
            tracer.start("Stage 0: PIGuardrail")
            tracer.log_input({"question": question[:100]})
            logger.info(f"[0/14] PIGuardrail checking for prompt injection...")
            pi_result = self._pi_guard.check(question)
            tracer.log_output({
                "result": pi_result.result.value,
                "confidence": pi_result.confidence,
                "label": pi_result.label,
                "model_loaded": pi_result.model_loaded,
            })
            tracer.end()
            if on_progress:
                detail = f"✅ An toàn (confidence={pi_result.confidence:.2f})" if pi_result.result.value != "injection" else f"⚠️ Tấn công bị chặn (confidence={pi_result.confidence:.2f})"
                on_progress("0", "🛡 Kiểm tra bảo mật đầu vào", detail)

            if pi_result.result == PIGuardResult.INJECTION_DETECTED:
                logger.warning(
                    f"[0/14] PIGuardrail: INJECTION BLOCKED "
                    f"(confidence={pi_result.confidence:.3f})"
                )
                return AskResult(
                    question=question,
                    intent="INJECTION",
                    error=pi_result.response,
                    pi_guard_blocked=True,
                    pi_guard_confidence=pi_result.confidence,
                    guardian_passed=False,
                    active_features=active_features,
                    debug_trace=tracer.to_dict(),
                )

            # ── Stage 0.5: Conversation Context Enrichment ──
            if on_progress: on_progress("0.5", "💬 Giải quyết ngữ cảnh hội thoại...")
            tracer.start("Stage 0.5: ConversationContext")
            tracer.log_input({"question": question, "session_id": session_id})
            logger.info(f"[0.5/14] ConversationContext enriching question (session={session_id or 'none'})...")
            ctx_result: EnrichResult = self._conv_ctx.enrich(
                question=question,
                session_id=session_id or "default_session",
                user_id=user_id,
            )
            working_question = ctx_result.enriched_question
            tracer.log_output({
                "enriched_question": working_question,
                "was_enriched": ctx_result.was_enriched,
                "memories_count": len(ctx_result.memories_used),
            })
            tracer.end()
            if on_progress:
                if ctx_result.was_enriched:
                    on_progress("0.5", "💬 Giải quyết ngữ cảnh hội thoại", f"✅ Làm giàu câu hỏi: “{working_question[:80]}”")
                else:
                    on_progress("0.5", "💬 Giải quyết ngữ cảnh hội thoại", "ℹ️ Câu hỏi độc lập, không cần làm giàu ngữ cảnh")

            # ── Stage 0.7: Question Translator (VI → EN) ──
            original_question_input = working_question
            translation_skipped = True
            if self._enable_question_translator:
                if on_progress: on_progress("0.7", "🌐 Dịch câu hỏi sang tiếng Anh...")
                tracer.start("Stage 0.7: QuestionTranslator")
                tracer.log_input({"question": working_question})
                logger.info(f"[0.7/14] Translating question (VI→EN if needed)...")
                tr_result = self._translator.translate(working_question)
                working_question = tr_result.translated
                translation_skipped = tr_result.skipped
                tracer.log_output({
                    "original": tr_result.original,
                    "translated": tr_result.translated,
                    "skipped": tr_result.skipped,
                    "error": tr_result.error,
                })
                tracer.end()
                if on_progress:
                    if tr_result.skipped:
                        on_progress("0.7", "🌐 Dịch câu hỏi", "ℹ️ Câu hỏi đã là tiếng Anh, bỏ qua")
                    else:
                        on_progress("0.7", "🌐 Dịch câu hỏi", f"✅ EN: “{working_question[:80]}”")

            # ── Stage 1: Pre-Filter (NO LLM — instant) ──
            if on_progress: on_progress("1", "🔍 Phân loại sơ bộ câu hỏi...")
            tracer.start("Stage 1: PreFilter")
            tracer.log_input({"question": working_question})
            logger.info(f"[1/14] Pre-filtering: {working_question}")
            pre_filter = self._pre_filter.filter(working_question)
            tracer.log_output({"result": pre_filter.result.value, "response": pre_filter.response})
            tracer.end()
            if on_progress: on_progress("1", "🔍 Phân loại sơ bộ câu hỏi", f"✅ Loại: {pre_filter.result.value.upper()}")

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
            if on_progress: on_progress("2", "📋 Tra cứu quy tắc nghiệp vụ...")
            tracer.start("Stage 2: InstructionMatch")
            logger.info("[2/14] Matching instructions...")
            instr_result = self._instruction_matcher.match(working_question)
            instructions_matched = len(instr_result.matched_instructions)
            tracer.log_output({"matched": instructions_matched, "context": instr_result.context_text[:200] if instr_result.context_text else ""})
            tracer.end()
            if on_progress:
                if instructions_matched > 0:
                    on_progress("2", "📋 Tra cứu quy tắc nghiệp vụ", f"✅ Tìm thấy {instructions_matched} quy tắc áp dụng")
                else:
                    on_progress("2", "📋 Tra cứu quy tắc nghiệp vụ", "ℹ️ Không có quy tắc nào khớp")

            # ── Stage 3: Intent Classification (LLM) ──
            if on_progress: on_progress("3", "🧠 Phân tích ý định câu hỏi...")
            tracer.start("Stage 3: IntentClassifier")
            tracer.log_input({"question": working_question, "models": model_names})
            logger.info(f"[3/14] Classifying intent: {working_question}")
            intent_result = self._classifier.classify(working_question, model_names)
            tracer.log_output({"intent": intent_result.intent.value, "reason": intent_result.reason})
            tracer.end()
            if on_progress: on_progress("3", "🧠 Phân tích ý định câu hỏi", f"✅ Intent: {intent_result.intent.value.upper()} — {intent_result.reason[:80]}")

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
            if on_progress: on_progress("4", "🎯 Xác định loại phân tích...")
            tracer.start("Stage 4: SubIntentDetect")
            logger.info("[4/16] Detecting sub-intent...")
            sub_intent_result = self._sub_intent_detector.detect(working_question)
            tracer.log_output({"sub_intent": sub_intent_result.sub_intent.value, "confidence": sub_intent_result.confidence, "sql_hints": sub_intent_result.sql_hints})
            tracer.end()
            if on_progress: on_progress("4", "🎯 Xác định loại phân tích", f"✅ Sub-intent: {sub_intent_result.sub_intent.value.upper()} (confidence={sub_intent_result.confidence:.2f})")

            # ── Step 5: Schema Retrieval ──
            if on_progress: on_progress("5", "📊 Tìm kiếm bảng dữ liệu liên quan...")
            tracer.start("Stage 5: SchemaRetrieval")
            tracer.log_input({"question": working_question})
            logger.info("[5/16] Retrieving schema context...")
            retrieval = self._retriever.retrieve(
                working_question, enable_bidirectional=use_bidirectional
            )
            tracer.log_output({
                "models_found": retrieval.model_names,
                "schemas_count": len(retrieval.db_schemas),
                "total_columns": sum(len(s.get("columns", [])) for s in retrieval.db_schemas),
            })
            tracer.end()
            total_cols = sum(len(s.get("columns", [])) for s in retrieval.db_schemas)
            if on_progress: on_progress("5", "📊 Tìm kiếm bảng dữ liệu liên quan", f"✅ Tìm thấy {len(retrieval.model_names)} bảng, {total_cols} cột: {', '.join(retrieval.model_names[:4])}")

            # ── Step 6: Schema Linking ──
            schema_hints = ""
            schema_links_info = {}
            if use_schema_linking:
                if on_progress: on_progress("6", "🔗 Liên kết thực thể với schema...")
                tracer.start("Stage 6: SchemaLinking")
                logger.info("[6/14] Schema linking...")
                prelim_ddl = self._context_builder.build_for_llm(
                    retrieval.db_schemas, retrieval.model_names,
                    enable_mschema=use_mschema,
                )
                link_result = self._schema_linker.link(working_question, prelim_ddl)
                schema_hints = link_result.context_hints
                schema_links_info = {
                    "entity_links": [{"mention": e.mention, "table": e.table, "column": e.column} for e in link_result.entity_links],
                    "value_links": [{"mention": v.mention, "table": v.table, "column": v.column} for v in link_result.value_links],
                    "ambiguities": link_result.ambiguities,
                }
                tracer.log_output({"entity_links": len(link_result.entity_links), "value_links": len(link_result.value_links), "hints": schema_hints[:150]})
                tracer.end()
                if on_progress:
                    el = len(link_result.entity_links); vl = len(link_result.value_links)
                    on_progress("6", "🔗 Liên kết thực thể với schema", f"✅ {el} entity links, {vl} value links" + (f" | {schema_hints[:60]}" if schema_hints else ""))
            else:
                tracer.skip("Stage 6: SchemaLinking", "disabled")
                logger.info("[6/14] Schema linking SKIPPED")

            # ── Step 7: Column Pruning ──
            columns_pruned = 0
            if use_column_pruning:
                if on_progress: on_progress("7", "✂️ Lọc cột không liên quan...")
                tracer.start("Stage 7: ColumnPruning")
                logger.info("[7/14] Column pruning...")
                total_before = sum(len(s.get("columns", [])) for s in retrieval.db_schemas)
                pruned_schemas = self._column_pruner.prune(working_question, retrieval.db_schemas)
                total_after = sum(len(s.get("columns", [])) for s in pruned_schemas)
                columns_pruned = total_before - total_after
                tracer.log_output({"before": total_before, "after": total_after, "pruned": columns_pruned})
                tracer.end()
                if on_progress: on_progress("7", "✂️ Lọc cột không liên quan", f"✅ Lược bỏ {columns_pruned} cột ({total_before} → {total_after} cột)")
            else:
                tracer.skip("Stage 7: ColumnPruning", "disabled")
                logger.info("[7/14] Column pruning SKIPPED")
                pruned_schemas = retrieval.db_schemas

            # ── Step 8: Context Building ──
            if on_progress: on_progress("8", "📝 Xây dựng ngữ cảnh DDL...")
            tracer.start("Stage 8: ContextBuilder")
            logger.info("[8/14] Building DDL context...")
            ddl = self._context_builder.build_for_llm(
                pruned_schemas, retrieval.model_names,
                enable_mschema=use_mschema,
            )
            tracer.log_output({"ddl_length": len(ddl)})
            tracer.end()
            if on_progress: on_progress("8", "📝 Xây dựng ngữ cảnh DDL", f"✅ DDL context: {len(ddl)} ký tự, {len(retrieval.model_names)} bảng")

            # ── Step 9: Business Glossary Injection ──
            glossary_context = ""
            glossary_match_count = 0
            if use_glossary:
                if on_progress: on_progress("9", "📖 Tra cứu từ điển nghiệp vụ...")
                tracer.start("Stage 9: GlossaryLookup")
                logger.info("[9/14] Glossary lookup...")
                matches = self._glossary.lookup(working_question)
                glossary_match_count = len(matches)
                glossary_context = self._glossary.build_context(matches)
                tracer.log_output({"matches": glossary_match_count, "context": glossary_context[:100]})
                tracer.end()
                if on_progress:
                    if glossary_match_count > 0:
                        terms = ", ".join(m.term.name for m in matches[:3])
                        on_progress("9", "📖 Tra cứu từ điển nghiệp vụ", f"✅ Tìm thấy {glossary_match_count} thuật ngữ: {terms}")
                    else:
                        on_progress("9", "📖 Tra cứu từ điển nghiệp vụ", "ℹ️ Không tìm thấy thuật ngữ phù hợp")
            else:
                tracer.skip("Stage 9: GlossaryLookup", "disabled")
                logger.info("[9/14] Glossary SKIPPED")

            # ── Step 10: Semantic Memory Lookup ──
            memory_context = ""
            similar_trace_count = 0
            if use_memory:
                if on_progress: on_progress("10", "🧩 Tìm kiếm SQL tương tự trong memory...")
                tracer.start("Stage 10: SemanticMemory")
                logger.info("[10/14] Semantic memory lookup...")
                similar = self._memory.find_similar(working_question)
                similar_trace_count = len(similar)
                memory_context = self._memory.build_context(similar)
                tracer.log_output({"similar_traces": similar_trace_count, "context": memory_context[:100]})
                tracer.end()
                if on_progress:
                    if similar_trace_count > 0:
                        on_progress("10", "🧩 Tìm kiếm SQL tương tự trong memory", f"✅ Tìm thấy {similar_trace_count} câu SQL tương tự trong lịch sử")
                    else:
                        on_progress("10", "🧩 Tìm kiếm SQL tương tự trong memory", "ℹ️ Không tìm thấy SQL nào tương tự")
            else:
                tracer.skip("Stage 10: SemanticMemory", "disabled")
                logger.info("[10/14] Semantic memory SKIPPED")

            # ── Step 11: CoT Reasoning ──
            reasoning_plan = ""
            reasoning_steps = []
            if use_cot_reasoning:
                if on_progress: on_progress("11", "🤔 Lập kế hoạch truy vấn CoT...")
                tracer.start("Stage 11: CoTReasoning")
                logger.info("[11/14] CoT reasoning (streaming)...")
                reasoning = self._reasoner.reason_stream(
                    question=working_question,
                    ddl_context=ddl,
                    on_token=(
                        lambda chunk: on_token("reasoning", chunk)
                        if on_token else None
                    ),
                )
                reasoning_plan = reasoning.reasoning_text
                reasoning_steps = reasoning.steps
                tracer.log_output({"steps": reasoning_steps, "plan_length": len(reasoning_plan)})
                tracer.end()
                if on_progress: on_progress("11", "🤔 Lập kế hoạch truy vấn CoT", f"✅ {len(reasoning_steps)} bước suy luận: {'; '.join(str(s)[:40] for s in reasoning_steps[:2])}")
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
            if on_progress: on_progress("12", "⚡ Sinh câu lệnh SQL...")
            tracer.start("Stage 12: SQLGeneration")
            if use_voting and num_candidates > 1:
                logger.info(f"[12/14] Multi-candidate generation ({num_candidates} candidates) + voting...")
                self._candidate_gen._num_candidates = num_candidates
                candidate_set = self._candidate_gen.generate(
                    question=working_question, ddl_context=enriched_ddl,
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
                        self._save_memory(working_question, best_sql, True, exec_r.result_hash, retrieval.model_names, question_vi=question)
                        return result

                    logger.info("[13/14] Voting candidate failed → correction loop")
                else:
                    logger.warning("No candidates generated → fallback")
                    best_sql = ""; best_explanation = ""; voting_method = "fallback"; candidates_generated = 0
                    tracer.log_output({"candidates": 0, "fallback": True})
                    tracer.end()
            else:
                logger.info("[12/14] Single-pass generation streaming (voting disabled)...")
                tracer.log_input({"mode": "single-pass-stream"})
                gen_result = self._generator.generate_stream(
                    question=working_question,
                    ddl_context=enriched_ddl,
                    on_token=(
                        lambda chunk: on_token("sql", chunk)
                        if on_token else None
                    ),
                )
                best_sql = gen_result.sql
                best_explanation = gen_result.explanation
                voting_method = "single"; candidates_generated = 1
                tracer.log_output({"sql": best_sql, "explanation": best_explanation})
                tracer.end()
                if on_progress:
                    sql_preview = best_sql[:80].replace('\n', ' ') if best_sql else "(trống)"
                    on_progress("12", "⚡ Sinh câu lệnh SQL", f"✅ SQL: {sql_preview}...")

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
            if on_progress: on_progress("13", "🔧 Kiểm tra và sửa lỗi SQL...")
            tracer.start("Stage 13: SQLCorrection")
            tracer.log_input({"input_sql": best_sql[:200], "explanation": best_explanation[:100]})
            logger.info("[13/14] Validating and correcting SQL...")
            correction = self._corrector.validate_and_correct(
                sql=best_sql, ddl_context=enriched_ddl,
                question=question, explanation=best_explanation,
                strategy=use_correction_strategy,
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
            if on_progress:
                if correction.valid:
                    row_count = correction.result.get("row_count", 0) if correction.result else 0
                    msg = f"✅ SQL hợp lệ ({correction.retries} lần thử lại), trả về {row_count} dòng"
                else:
                    err = correction.errors[0][:80] if correction.errors else "Lỗi không xác định"
                    msg = f"❌ Không hợp lệ sau {correction.retries} lần sửa: {err}"
                on_progress("13", "🔧 Kiểm tra và sửa lỗi SQL", msg)

            # ── Step 13.5: SQL Guardian Validation ──
            if on_progress: on_progress("13.5", "🛡 Kiểm duyệt bảo mật SQL...")
            tracer.start("Stage 13.5: Guardian")
            guardian_passed = True
            if correction.valid and correction.sql:
                logger.info("[13.5/14] SQL Guardian validating...")
                guardian_result = self._guardian.validate(correction.sql)
                guardian_passed = guardian_result.safe
                tracer.log_output({"safe": guardian_result.safe, "reason": guardian_result.reason, "blocked_by": guardian_result.blocked_by})
                tracer.end()
                if on_progress:
                    if guardian_result.safe:
                        on_progress("13.5", "🛡 Kiểm duyệt bảo mật SQL", "✅ SQL an toàn, được phép thực thi")
                    else:
                        on_progress("13.5", "🛡 Kiểm duyệt bảo mật SQL", f"🚫 Bị chặn: {guardian_result.reason[:80]}")
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

            # ── Step 14: Semantic Memory Save + Execute ──
            if on_progress: on_progress("14", "🗄 Thực thi truy vấn & lưu kết quả...")
            tracer.start("Stage 14: MemorySave")
            result_hash = ""
            if correction.valid and correction.result:
                import hashlib, json
                content = json.dumps(correction.result, default=str)
                result_hash = hashlib.md5(content.encode()).hexdigest()
            self._save_memory(
                working_question, best_sql, correction.valid,
                result_hash, retrieval.model_names,
                correction.errors[0] if correction.errors else "",
                correction.retries,
                question_vi=question,
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
                # Stage 0.5: Conversation context metadata
                enriched_question=ctx_result.enriched_question,
                was_enriched=ctx_result.was_enriched,
                memories_used=ctx_result.memories_used,
                session_id=session_id,
                # Stage 0.7: Translator metadata
                original_question=original_question_input,
                translated_question=working_question,
                translation_skipped=translation_skipped,
            )

            if correction.valid and correction.result:
                result.columns = correction.result.get("columns", [])
                result.rows = correction.result.get("rows", [])
                result.row_count = correction.result.get("row_count", 0)
            elif not correction.valid:
                errors = "; ".join(correction.errors) if correction.errors else "Unknown"
                result.error = f"SQL validation failed after {correction.retries} retries: {errors}"

            # ── Post-pipeline: save turn to mem0 (background, non-blocking) ──
            if session_id and correction.valid:
                row_count = result.row_count
                sample = str(result.rows[0])[:100] if result.rows else ""
                result_summary = f"{row_count} rows" + (f" — Sample: {sample}" if sample else "")
                self._conv_ctx.save_turn_background(
                    question=question,
                    enriched_question=ctx_result.enriched_question,
                    sql=correction.sql or "",
                    result_summary=result_summary,
                    session_id=session_id,
                    user_id=user_id,
                )

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
        question_vi: str = "",
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
                question_vi=question_vi,
            )
        except Exception as e:
            logger.warning(f"Failed to save memory trace: {e}")
