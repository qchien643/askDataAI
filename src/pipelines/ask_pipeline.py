"""
Ask Pipeline - Full pipeline từ câu hỏi → SQL → kết quả.

Tương đương AskService._ask_task() trong WrenAI gốc
(wren-ai-service/src/web/v1/services/ask.py), nhưng synchronous.

Luồng:
  question → intent → retrieve → generate → rewrite → correct → result
"""

import logging
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
from src.generation.llm_client import LLMClient
from src.generation.intent_classifier import IntentClassifier, Intent
from src.generation.sql_generator import SQLGenerator
from src.generation.sql_rewriter import SQLRewriter
from src.generation.sql_corrector import SQLCorrector

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


class AskPipeline:
    """
    Full pipeline: question → SQL → data.

    Cần được khởi tạo sau khi deploy (manifest + indexer phải sẵn sàng).
    """

    def __init__(
        self,
        manifest: Manifest,
        indexer: SchemaIndexer,
        engine: sqlalchemy.Engine,
    ):
        self._manifest = manifest
        self._indexer = indexer
        self._engine = engine

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

    def ask(self, question: str) -> AskResult:
        """
        Chạy full pipeline.

        Args:
            question: Câu hỏi user.

        Returns:
            AskResult.
        """
        model_names = [m.name for m in self._manifest.models]

        try:
            # 1. Intent classification
            logger.info(f"Classifying intent: {question}")
            intent_result = self._classifier.classify(question, model_names)

            if intent_result.intent == Intent.GENERAL:
                return AskResult(
                    question=question,
                    intent=intent_result.intent.value,
                    error="Câu hỏi không liên quan đến dữ liệu. Tôi chỉ hỗ trợ truy vấn dữ liệu.",
                )

            if intent_result.intent == Intent.AMBIGUOUS:
                return AskResult(
                    question=question,
                    intent=intent_result.intent.value,
                    error=f"Câu hỏi chưa rõ ràng. {intent_result.reason}",
                )

            # 2. Retrieve schema context
            logger.info("Retrieving schema context...")
            retrieval = self._retriever.retrieve(question)
            ddl = self._context_builder.build(
                retrieval.db_schemas, retrieval.model_names
            )

            # 3. Generate SQL
            logger.info("Generating SQL...")
            gen_result = self._generator.generate(question, ddl)

            if not gen_result.sql:
                return AskResult(
                    question=question,
                    intent=intent_result.intent.value,
                    error="Không thể sinh SQL cho câu hỏi này.",
                    models_used=retrieval.model_names,
                )

            # 4. Validate + correct (includes rewrite)
            logger.info("Validating and correcting SQL...")
            correction = self._corrector.validate_and_correct(
                sql=gen_result.sql,
                ddl_context=ddl,
                question=question,
                explanation=gen_result.explanation,
            )

            # 5. Build result
            result = AskResult(
                question=question,
                intent=intent_result.intent.value,
                sql=correction.sql,
                original_sql=gen_result.sql,
                explanation=gen_result.explanation,
                valid=correction.valid,
                retries=correction.retries,
                models_used=retrieval.model_names,
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
            )
