"""
Mini Wren AI - FastAPI Server.

Luồng user-driven:
- Khởi động: KHÔNG auto-deploy, chờ user kết nối qua /v1/connections/connect
- Connect: Test DB → Build manifest → Index ChromaDB (embedding)
- Disconnect: Giải phóng connection + xóa ChromaDB index

Endpoints:
  Connection:  test, connect, status, disconnect
  Ask:         ask, sql/execute, models
  Knowledge:   glossary CRUD, sql-pairs CRUD
  Settings:    get/update pipeline settings
  Deploy:      re-deploy (chỉ khi đã connected)
"""

import asyncio
import logging
import queue
import shutil
import threading
import uuid
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path
from typing import Any, AsyncGenerator
from urllib.parse import quote_plus

import yaml
import sqlalchemy
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from askdataai.config import settings
from askdataai.connectors.connection import SQLServerConnector
from askdataai.pipelines.deploy_pipeline import DeployPipeline
from askdataai.pipelines.ask_pipeline import AskPipeline
from askdataai.generation.chart_generator import ChartGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mini-wren-ai")

# ── Project root ──
PROJECT_ROOT = Path(__file__).parent.parent


# ── Global state ──
_state: dict[str, Any] = {
    "connected": False,
    "deployed": False,
    "deploy_pipeline": None,
    "ask_pipeline": None,
    "connection_info": None,
    "settings": {
        "features": {
            "enable_schema_linking": True,
            "enable_column_pruning": True,
            "enable_cot_reasoning": True,
            "enable_voting": False,
            "enable_glossary": True,
            "enable_memory": False,
            "enable_question_translator": True,
            # Sprint 2-5 improvements
            "enable_mschema": True,
            "enable_bidirectional_retrieval": True,
            "correction_strategy": "taxonomy_guided",  # str: execution_only | taxonomy_guided
        },
        "generation": {
            "num_candidates": 3,
            "temperature": 0.1,
        },
    },
}


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: KHÔNG auto-deploy — chờ user connect."""
    logger.info("Mini Wren AI started. Waiting for database connection...")
    yield
    # Shutdown: cleanup
    _cleanup()
    logger.info("Mini Wren AI stopped.")


def _cleanup():
    """Giải phóng tài nguyên."""
    if _state.get("deploy_pipeline") and _state["deploy_pipeline"].connector:
        try:
            _state["deploy_pipeline"].connector.close()
        except Exception:
            pass
    _state["connected"] = False
    _state["deployed"] = False
    _state["deploy_pipeline"] = None
    _state["ask_pipeline"] = None
    _state["connection_info"] = None


# ── App ──
app = FastAPI(
    title="Mini Wren AI",
    description="Text-to-SQL với SQL Server — user-driven deployment",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════
# ── Request/Response Models ──
# ═══════════════════════════════════════════════

class ConnectionRequest(BaseModel):
    host: str = "localhost"
    port: int = 1433
    database: str = "AdventureWorksDW2025"
    username: str = "sa"
    password: str = ""


class AskRequest(BaseModel):
    question: str
    session_id: str = ""   # Multi-turn context: client giữ session_id qua các turns
    enable_schema_linking: bool | None = None
    enable_column_pruning: bool | None = None
    enable_cot_reasoning: bool | None = None
    enable_voting: bool | None = None
    enable_glossary: bool | None = None
    enable_memory: bool | None = None
    num_candidates: int | None = None
    # Sprint 2-5 improvements (per-request override; None = use settings default)
    enable_mschema: bool | None = None
    enable_bidirectional_retrieval: bool | None = None
    correction_strategy: str | None = None  # "execution_only" | "taxonomy_guided"
    debug: bool = False  # Bật debug trace để xem pipeline stages


class SQLExecuteRequest(BaseModel):
    sql: str
    limit: int = 10000


class ChartRequest(BaseModel):
    question: str
    sql: str


class GlossaryTermRequest(BaseModel):
    term: str
    aliases: list[str] = []
    sql_expression: str = ""
    description: str = ""


class SqlPairRequest(BaseModel):
    question: str
    sql: str


class SettingsRequest(BaseModel):
    features: dict[str, bool] | None = None
    generation: dict[str, Any] | None = None


class ColumnUpdateData(BaseModel):
    name: str
    description: str | None = None
    display_name: str | None = None
    enum_values: list[str] | None = None   # ← Tập giá trị categorical


class ModelUpdateRequest(BaseModel):
    description: str | None = None
    columns: list[ColumnUpdateData] | None = None


class AddColumnData(BaseModel):
    name: str
    type: str = "string"
    display_name: str = ""
    description: str = ""


class AddModelRequest(BaseModel):
    name: str                           # e.g. "employees"
    table_reference: str                # e.g. "dbo.DimEmployee"
    description: str = ""
    primary_key: str | None = None
    columns: list[AddColumnData] = []


class AddRelationshipRequest(BaseModel):
    name: str                           # e.g. "employees_to_geography"
    model_from: str
    model_to: str
    join_type: str = "MANY_TO_ONE"
    condition: str


# ═══════════════════════════════════════════════
# ── Helpers ──
# ═══════════════════════════════════════════════

def _serialize(obj: Any) -> Any:
    """Serialize cho JSON (handle Decimal, date, etc.)."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _ensure_deployed():
    """Check pipeline đã deploy chưa."""
    if not _state["deployed"] or not _state["ask_pipeline"]:
        raise HTTPException(
            status_code=503,
            detail="Chưa kết nối database. Vào /setup để kết nối.",
        )


def _is_docker() -> bool:
    """Detect if running inside a Docker container."""
    return Path("/.dockerenv").exists()


def _resolve_host(host: str) -> str:
    """Translate localhost to host.docker.internal when running in Docker."""
    if _is_docker() and host in ("localhost", "127.0.0.1"):
        return "host.docker.internal"
    return host


def _build_connection_string(req: ConnectionRequest) -> str:
    """Build SQLAlchemy connection string từ ConnectionRequest."""
    password = quote_plus(req.password)
    host = _resolve_host(req.host)
    return (
        f"mssql+pyodbc://{req.username}:{password}"
        f"@{host},{req.port}"
        f"/{req.database}"
        f"?driver=ODBC+Driver+17+for+SQL+Server"
        f"&TrustServerCertificate=yes"
    )


def _glossary_path() -> Path:
    return PROJECT_ROOT / "configs" / "glossary.yaml"


def _memory_path() -> Path:
    return PROJECT_ROOT / "data" / "semantic_memory.json"


def _chroma_dir() -> str:
    return str(PROJECT_ROOT / "data" / "chroma_data")


# ═══════════════════════════════════════════════
# ── 1. Connection Management ──
# ═══════════════════════════════════════════════

@app.post("/v1/connections/test")
def test_connection(req: ConnectionRequest):
    """
    Test kết nối DB mà KHÔNG deploy/embedding.
    Dùng ở Setup page khi user click "Test Connection".
    """
    try:
        conn_str = _build_connection_string(req)
        connector = SQLServerConnector(conn_str)
        result = connector.test_connection()
        connector.close()
        return result
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.post("/v1/connections/connect")
def connect_and_deploy(req: ConnectionRequest):
    """
    Kết nối DB + Build manifest + Index ChromaDB (embedding).
    Đây là bước duy nhất chạy embedding.

    Luồng:
    1. Tạo connector mới (close cái cũ nếu có)
    2. Cập nhật settings config với connection info mới
    3. Chạy DeployPipeline (build manifest + index)
    4. Tạo AskPipeline
    """
    try:
        # Cleanup old connection nếu có
        _cleanup()

        # Cập nhật settings tạm thời
        settings.sql_server_host = req.host
        settings.sql_server_port = req.port
        settings.sql_server_db = req.database
        settings.sql_server_user = req.username
        settings.sql_server_pass = req.password

        # Chạy deploy pipeline
        deploy = DeployPipeline(chroma_dir=_chroma_dir())
        result = deploy.run()

        if result.success:
            _state["connected"] = True
            _state["deployed"] = True
            _state["deploy_pipeline"] = deploy
            _state["connection_info"] = {
                "host": req.host,
                "port": req.port,
                "database": req.database,
                "username": req.username,
            }

            # Build AskPipeline với current settings
            feat = _state["settings"]["features"]
            gen = _state["settings"]["generation"]
            _state["ask_pipeline"] = AskPipeline(
                manifest=deploy.manifest,
                indexer=deploy.indexer,
                engine=deploy.connector.engine,
                num_candidates=gen.get("num_candidates", 3),
                enable_column_pruning=feat.get("enable_column_pruning", True),
                enable_cot_reasoning=feat.get("enable_cot_reasoning", True),
                enable_schema_linking=feat.get("enable_schema_linking", True),
                enable_voting=feat.get("enable_voting", True),
                enable_glossary=feat.get("enable_glossary", True),
                enable_memory=feat.get("enable_memory", False),
                enable_question_translator=feat.get("enable_question_translator", True),
                glossary_path=str(_glossary_path()),
                memory_path=str(_memory_path()),
            )

            logger.info(
                f"Connected: {req.database} — "
                f"{result.models_count} models, "
                f"{result.relationships_count} relationships"
            )

            return {
                "success": True,
                "message": "Connected and deployed",
                "models_count": result.models_count,
                "relationships_count": result.relationships_count,
                "manifest_hash": result.manifest_hash,
                "indexed": result.indexed,
            }
        else:
            return {
                "success": False,
                "message": result.message,
            }

    except Exception as e:
        logger.error(f"Connect error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/connections/status")
def connection_status():
    """Xem trạng thái kết nối hiện tại."""
    info = _state.get("connection_info") or {}
    models_count = 0
    if _state.get("deploy_pipeline") and _state["deploy_pipeline"].manifest:
        models_count = len(_state["deploy_pipeline"].manifest.models)

    return {
        "connected": _state["connected"],
        "deployed": _state["deployed"],
        "host": info.get("host", ""),
        "port": info.get("port", 0),
        "database": info.get("database", ""),
        "models_count": models_count,
    }


@app.post("/v1/connections/disconnect")
def disconnect():
    """
    Ngắt kết nối + xóa ChromaDB index.
    Mỗi lần disconnect là reset hoàn toàn.
    """
    try:
        _cleanup()

        # Xóa ChromaDB data
        chroma_path = Path(_chroma_dir())
        if chroma_path.exists():
            shutil.rmtree(chroma_path)
            logger.info(f"ChromaDB data deleted: {chroma_path}")

        return {"success": True, "message": "Disconnected and ChromaDB index cleared"}

    except Exception as e:
        logger.error(f"Disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════
# ── 2. Ask & Execute (giữ nguyên logic) ──
# ═══════════════════════════════════════════════

@app.post("/v1/ask")
def ask(request: AskRequest):
    """Hỏi câu hỏi → chạy pipeline → trả SQL + data."""
    _ensure_deployed()

    try:
        overrides = {}
        if request.enable_schema_linking is not None:
            overrides["enable_schema_linking"] = request.enable_schema_linking
        if request.enable_column_pruning is not None:
            overrides["enable_column_pruning"] = request.enable_column_pruning
        if request.enable_cot_reasoning is not None:
            overrides["enable_cot_reasoning"] = request.enable_cot_reasoning
        if request.enable_voting is not None:
            overrides["enable_voting"] = False  # Voting is permanently disabled
        if request.enable_glossary is not None:
            overrides["enable_glossary"] = request.enable_glossary
        if request.enable_memory is not None:
            overrides["enable_memory"] = request.enable_memory
        if request.num_candidates is not None:
            overrides["num_candidates"] = request.num_candidates
        if request.enable_mschema is not None:
            overrides["enable_mschema"] = request.enable_mschema
        if request.enable_bidirectional_retrieval is not None:
            overrides["enable_bidirectional_retrieval"] = request.enable_bidirectional_retrieval
        if request.correction_strategy is not None:
            overrides["correction_strategy"] = request.correction_strategy

        result = _state["ask_pipeline"].ask(
            request.question,
            overrides=overrides,
            debug=request.debug,
            session_id=request.session_id or str(uuid.uuid4()),
        )

        response = {
            "question": result.question,
            "intent": result.intent,
            "sql": result.sql,
            "original_sql": result.original_sql,
            "explanation": result.explanation,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "valid": result.valid,
            "retries": result.retries,
            "error": result.error,
            "models_used": result.models_used,
            "pipeline_info": {
                "reasoning_steps": result.reasoning_steps,
                "schema_links": result.schema_links,
                "columns_pruned": result.columns_pruned,
                "candidates_generated": result.candidates_generated,
                "voting_method": result.voting_method,
                "glossary_matches": result.glossary_matches,
                "similar_traces": result.similar_traces,
                "active_features": result.active_features,
                # Multi-stage intent + Guardian metadata
                "sub_intent": result.sub_intent,
                "sub_intent_hints": result.sub_intent_hints,
                "instructions_matched": result.instructions_matched,
                "guardian_passed": result.guardian_passed,
                "pre_filter_result": result.pre_filter_result,
                # Stage 0: PIGuardrail metadata
                "pi_guard_blocked": result.pi_guard_blocked,
                "pi_guard_confidence": result.pi_guard_confidence,
                # Stage 0.5: Conversation Context metadata
                "session_id": result.session_id,
                "enriched_question": result.enriched_question,
                "was_enriched": result.was_enriched,
                # Stage 0.7: Question Translator metadata
                "original_question": result.original_question,
                "translated_question": result.translated_question,
                "translation_skipped": result.translation_skipped,
            },
        }

        # Include debug trace when debug mode is active
        if request.debug and result.debug_trace:
            response["debug_trace"] = result.debug_trace

        return _serialize(response)

    except Exception as e:
        logger.error(f"Ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# ── 2b. Ask Stream (SSE) ──
# ─────────────────────────────────────────────

def _sse(event: str, data: Any) -> str:
    """Format một Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.post("/v1/ask/stream")
async def ask_stream(request: AskRequest):
    """
    Streaming version của /v1/ask — dùng Server-Sent Events.

    Client nhận từng event:
      event: progress  \u2192  {"stage": "3", "label": "🧠 Phân tích ý định..."}
      event: result    \u2192  {full AskResponse JSON}
      event: error     \u2192  {"message": "..."}
    """
    _ensure_deployed()

    async def generator() -> AsyncGenerator[str, None]:
        # Yield initial ack ngay lập tức — tránh timeout trênconnect
        yield _sse("progress", {"stage": "start", "label": "⏳ Đang khởi động pipeline..."})

        # Thread-safe queue: pipeline thread push, async generator pull
        q: queue.Queue = queue.Queue()
        DONE = object()  # sentinel

        def on_progress(stage: str, label: str, detail: str = "") -> None:
            q.put_nowait(("progress", {"stage": stage, "label": label, "detail": detail}))

        def on_token(stage: str, chunk: str) -> None:
            """Push individual token chunk to SSE queue (Stage 11 CoT + Stage 12 SQL)."""
            q.put_nowait(("token", {"text": chunk, "stage": stage}))

        def run_pipeline() -> None:
            try:
                overrides = {}
                if request.enable_schema_linking is not None:
                    overrides["enable_schema_linking"] = request.enable_schema_linking
                if request.enable_column_pruning is not None:
                    overrides["enable_column_pruning"] = request.enable_column_pruning
                if request.enable_cot_reasoning is not None:
                    overrides["enable_cot_reasoning"] = request.enable_cot_reasoning
                if request.enable_voting is not None:
                    overrides["enable_voting"] = False  # voting permanently disabled
                if request.enable_glossary is not None:
                    overrides["enable_glossary"] = request.enable_glossary
                if request.enable_memory is not None:
                    overrides["enable_memory"] = request.enable_memory
                if request.num_candidates is not None:
                    overrides["num_candidates"] = request.num_candidates
                if request.enable_mschema is not None:
                    overrides["enable_mschema"] = request.enable_mschema
                if request.enable_bidirectional_retrieval is not None:
                    overrides["enable_bidirectional_retrieval"] = request.enable_bidirectional_retrieval
                if request.correction_strategy is not None:
                    overrides["correction_strategy"] = request.correction_strategy

                result = _state["ask_pipeline"].ask(
                    request.question,
                    overrides=overrides,
                    debug=request.debug,
                    session_id=request.session_id or str(uuid.uuid4()),
                    on_progress=on_progress,
                    on_token=on_token,
                )

                # Build response dict (giống /v1/ask)
                response = {
                    "question": result.question,
                    "intent": result.intent,
                    "sql": result.sql,
                    "original_sql": result.original_sql,
                    "explanation": result.explanation,
                    "columns": result.columns,
                    "rows": result.rows,
                    "row_count": result.row_count,
                    "valid": result.valid,
                    "retries": result.retries,
                    "error": result.error,
                    "models_used": result.models_used,
                    "pipeline_info": {
                        "reasoning_steps": result.reasoning_steps,
                        "schema_links": result.schema_links,
                        "columns_pruned": result.columns_pruned,
                        "candidates_generated": result.candidates_generated,
                        "voting_method": result.voting_method,
                        "glossary_matches": result.glossary_matches,
                        "similar_traces": result.similar_traces,
                        "active_features": result.active_features,
                        "sub_intent": result.sub_intent,
                        "sub_intent_hints": result.sub_intent_hints,
                        "instructions_matched": result.instructions_matched,
                        "guardian_passed": result.guardian_passed,
                        "pre_filter_result": result.pre_filter_result,
                        "pi_guard_blocked": result.pi_guard_blocked,
                        "pi_guard_confidence": result.pi_guard_confidence,
                        "session_id": result.session_id,
                        "enriched_question": result.enriched_question,
                        "was_enriched": result.was_enriched,
                    },
                }
                if request.debug and result.debug_trace:
                    response["debug_trace"] = result.debug_trace

                q.put_nowait(("result", _serialize(response)))
            except Exception as exc:
                logger.error(f"ask_stream pipeline error: {exc}", exc_info=True)
                q.put_nowait(("error", {"message": str(exc)}))
            finally:
                q.put_nowait(DONE)

        # Start pipeline in background thread (pipeline is sync/blocking)
        t = threading.Thread(target=run_pipeline, daemon=True)
        t.start()

        loop = asyncio.get_event_loop()

        # Pull events from queue and yield as SSE
        while True:
            try:
                item = await loop.run_in_executor(None, lambda: q.get(timeout=120))
            except Exception:
                yield _sse("error", {"message": "Pipeline timeout"})
                break

            if item is DONE:
                break

            event_type, data = item
            yield _sse(event_type, data)

            if event_type in ("result", "error"):
                break

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@app.post("/v1/sql/execute")
def execute_sql(request: SQLExecuteRequest):
    """Chạy SQL trực tiếp trên DB."""
    _ensure_deployed()

    try:
        engine = _state["deploy_pipeline"].connector.engine
        with engine.connect() as conn:
            result = conn.execute(sqlalchemy.text(request.sql))
            columns = list(result.keys())
            rows = [
                dict(zip(columns, row))
                for row in result.fetchmany(request.limit)
            ]

        return _serialize({
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        })

    except Exception as e:
        logger.error(f"SQL execute error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/v1/charts/generate")
def generate_chart(request: ChartRequest):
    """Sinh Vega-Lite chart từ question + SQL."""
    _ensure_deployed()

    try:
        # Execute SQL to get data
        engine = _state["deploy_pipeline"].connector.engine
        with engine.connect() as conn:
            result = conn.execute(sqlalchemy.text(request.sql))
            columns = list(result.keys())
            rows = [
                dict(zip(columns, row))
                for row in result.fetchmany(500)
            ]

        if not rows:
            return _serialize({
                "reasoning": "Không có dữ liệu để tạo biểu đồ.",
                "chart_type": "",
                "chart_schema": {},
                "data": {"columns": columns, "rows": [], "row_count": 0},
            })

        # Generate chart via LLM
        from askdataai.generation.llm_client import LLMClient
        from askdataai.config import settings
        llm = LLMClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        chart_gen = ChartGenerator(llm)
        chart_result = chart_gen.generate(
            question=request.question,
            sql=request.sql,
            columns=columns,
            rows=rows,
        )

        return _serialize({
            "reasoning": chart_result.reasoning,
            "chart_type": chart_result.chart_type,
            "chart_schema": chart_result.chart_schema,
            "error": chart_result.error,
            "data": {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            },
        })

    except Exception as e:
        logger.error(f"Chart generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/models")
def get_models():
    """Xem danh sách models + relationships."""
    _ensure_deployed()

    manifest = _state["deploy_pipeline"].manifest
    models = []
    for m in manifest.models:
        models.append({
            "name": m.name,
            "table_reference": m.table_reference,
            "description": m.description,
            "primary_key": m.primary_key,
            "columns": [
                {
                    "name": c.name,
                    "display_name": c.display_name,
                    "type": c.type,
                    "description": c.description,
                    "enum_values": c.enum_values,
                }
                for c in m.columns
            ],
        })

    relationships = [
        {
            "name": r.name,
            "model_from": r.model_from,
            "model_to": r.model_to,
            "join_type": r.join_type.value,
            "condition": r.condition,
        }
        for r in manifest.relationships
    ]

    return {
        "models_count": len(models),
        "relationships_count": len(relationships),
        "models": models,
        "relationships": relationships,
    }


def _models_yaml_path() -> Path:
    return PROJECT_ROOT / "configs" / "models.yaml"


@app.patch("/v1/models/{model_name}")
def update_model_metadata(model_name: str, req: ModelUpdateRequest):
    """
    Cập nhật metadata của model (description, column descriptions).
    Chỉ cho phép sửa mô tả — KHÔNG sửa name, table, type.
    Thay đổi được lưu vào models.yaml.
    """
    yaml_path = _models_yaml_path()
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail="models.yaml not found")

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        models_list = data.get("models", [])
        target = None
        for m in models_list:
            if m["name"] == model_name:
                target = m
                break

        if not target:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

        # Update model description
        if req.description is not None:
            target["description"] = req.description

        # Update column metadata
        if req.columns:
            col_map = {c["name"]: c for c in target.get("columns", [])}
            for col_update in req.columns:
                if col_update.name in col_map:
                    if col_update.description is not None:
                        col_map[col_update.name]["description"] = col_update.description
                    if col_update.display_name is not None:
                        col_map[col_update.name]["display_name"] = col_update.display_name
                    if col_update.enum_values is not None:
                        col_map[col_update.name]["enum_values"] = col_update.enum_values

        # Save back to YAML
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                width=120,
            )

        logger.info(f"Model metadata updated: {model_name}")

        return {
            "success": True,
            "model": model_name,
            "message": "Metadata updated. Deploy to apply changes.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update model metadata error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _load_models_yaml() -> dict:
    """Load and parse models.yaml."""
    yaml_path = _models_yaml_path()
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail="models.yaml not found")
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_models_yaml(data: dict):
    """Save data back to models.yaml."""
    yaml_path = _models_yaml_path()
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        )


# ─── SQL type mapping ───
_SQL_TYPE_MAP = {
    "int": "integer", "bigint": "integer", "smallint": "integer", "tinyint": "integer",
    "decimal": "decimal", "numeric": "decimal", "money": "decimal", "smallmoney": "decimal",
    "float": "float", "real": "float",
    "bit": "boolean",
    "date": "date", "datetime": "datetime", "datetime2": "datetime",
    "smalldatetime": "datetime", "time": "time",
    "nvarchar": "string", "varchar": "string", "char": "string", "nchar": "string",
    "text": "string", "ntext": "string",
    "uniqueidentifier": "string", "varbinary": "binary", "image": "binary",
}


def _map_sql_type(sql_type: str) -> str:
    """Map SQL Server data type to simplified type."""
    return _SQL_TYPE_MAP.get(sql_type.lower(), "string")


@app.post("/v1/models")
def add_model(req: AddModelRequest):
    """
    Add a new model (table) to models.yaml.
    Only modifies the semantic layer — does NOT create anything in the real database.
    """
    try:
        data = _load_models_yaml()
        models_list = data.get("models", [])

        # Check duplicate name
        for m in models_list:
            if m["name"] == req.name:
                raise HTTPException(status_code=409, detail=f"Model '{req.name}' already exists")

        new_model = {
            "name": req.name,
            "table": req.table_reference,
            "description": req.description,
            "primary_key": req.primary_key or "",
            "columns": [
                {
                    "name": c.name,
                    "display_name": c.display_name,
                    "type": c.type,
                    "description": c.description,
                }
                for c in req.columns
            ],
        }

        models_list.append(new_model)
        data["models"] = models_list
        _save_models_yaml(data)

        logger.info(f"Model added: {req.name} → {req.table_reference}")
        return {
            "success": True,
            "model": req.name,
            "message": "Model added. Deploy to apply changes.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add model error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/models/{model_name}")
def delete_model(model_name: str):
    """
    Delete a model from models.yaml + auto-remove related relationships.
    Only modifies the semantic layer — does NOT drop anything from the real database.
    """
    try:
        data = _load_models_yaml()
        models_list = data.get("models", [])
        original_len = len(models_list)

        data["models"] = [m for m in models_list if m["name"] != model_name]
        if len(data["models"]) == original_len:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

        # Auto-remove relationships referencing this model
        rels = data.get("relationships", [])
        data["relationships"] = [
            r for r in rels
            if r.get("from") != model_name and r.get("to") != model_name
        ]
        removed_rels = len(rels) - len(data["relationships"])

        _save_models_yaml(data)

        logger.info(f"Model deleted: {model_name} (+ {removed_rels} relationships)")
        return {
            "success": True,
            "model": model_name,
            "relationships_removed": removed_rels,
            "message": "Model deleted. Deploy to apply changes.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete model error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/models/{model_name}/columns/{column_name}")
def delete_column(model_name: str, column_name: str):
    """
    Delete a column from a model in models.yaml.
    Only modifies the semantic layer.
    """
    try:
        data = _load_models_yaml()
        models_list = data.get("models", [])

        target = None
        for m in models_list:
            if m["name"] == model_name:
                target = m
                break

        if not target:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

        cols = target.get("columns", [])
        original_len = len(cols)
        target["columns"] = [c for c in cols if c["name"] != column_name]

        if len(target["columns"]) == original_len:
            raise HTTPException(status_code=404, detail=f"Column '{column_name}' not found in '{model_name}'")

        _save_models_yaml(data)

        logger.info(f"Column deleted: {model_name}.{column_name}")
        return {
            "success": True,
            "model": model_name,
            "column": column_name,
            "message": "Column deleted. Deploy to apply changes.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete column error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/relationships")
def add_relationship(req: AddRelationshipRequest):
    """Add a new relationship to models.yaml."""
    try:
        data = _load_models_yaml()
        rels = data.get("relationships", [])

        # Check duplicate
        for r in rels:
            if r["name"] == req.name:
                raise HTTPException(status_code=409, detail=f"Relationship '{req.name}' already exists")

        # Validate model references exist
        model_names = {m["name"] for m in data.get("models", [])}
        if req.model_from not in model_names:
            raise HTTPException(status_code=400, detail=f"Model '{req.model_from}' not found")
        if req.model_to not in model_names:
            raise HTTPException(status_code=400, detail=f"Model '{req.model_to}' not found")

        rels.append({
            "name": req.name,
            "from": req.model_from,
            "to": req.model_to,
            "type": req.join_type,
            "condition": req.condition,
        })
        data["relationships"] = rels
        _save_models_yaml(data)

        logger.info(f"Relationship added: {req.name}")
        return {"success": True, "name": req.name, "message": "Relationship added. Deploy to apply changes."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add relationship error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/v1/relationships/{rel_name}")
def delete_relationship(rel_name: str):
    """Delete a relationship from models.yaml."""
    try:
        data = _load_models_yaml()
        rels = data.get("relationships", [])
        original_len = len(rels)

        data["relationships"] = [r for r in rels if r["name"] != rel_name]
        if len(data["relationships"]) == original_len:
            raise HTTPException(status_code=404, detail=f"Relationship '{rel_name}' not found")

        _save_models_yaml(data)

        logger.info(f"Relationship deleted: {rel_name}")
        return {"success": True, "name": rel_name, "message": "Relationship deleted. Deploy to apply changes."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete relationship error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/models/test-generate")
def test_generate():
    """
    Generate 2 VIRTUAL test tables for AdventureWorksDW2025 business context.

    Creates:
    - budget_targets: Sales budget/target by territory & time period
    - customer_feedback: Customer product reviews & satisfaction scores

    These tables do NOT exist in the real database — they are purely semantic
    layer additions to test modeling, description generation, and relationship
    capabilities. Descriptions are intentionally left EMPTY for AI to fill.

    Only modifies models.yaml — does NOT touch the real database.
    """
    if not _state["connected"]:
        raise HTTPException(status_code=400, detail="Not connected. Call /v1/connections/connect first.")

    # ── Virtual test table definitions ──
    # These are hardcoded schemas relevant to AdventureWorks retail analytics
    VIRTUAL_TEST_TABLES = [
        {
            "name": "budget_targets",
            "table": "virtual.BudgetTargets",
            "description": "",              # Empty — for AI to fill
            "primary_key": "BudgetTargetKey",
            "_test": True,
            "columns": [
                {"name": "BudgetTargetKey",     "display_name": "", "type": "integer",  "description": ""},
                {"name": "SalesTerritoryKey",   "display_name": "", "type": "integer",  "description": ""},
                {"name": "DateKey",             "display_name": "", "type": "integer",  "description": ""},
                {"name": "ProductCategoryKey",  "display_name": "", "type": "integer",  "description": ""},
                {"name": "BudgetAmount",        "display_name": "", "type": "decimal",  "description": ""},
                {"name": "TargetQuantity",      "display_name": "", "type": "integer",  "description": ""},
                {"name": "FiscalYear",          "display_name": "", "type": "integer",  "description": ""},
                {"name": "FiscalQuarter",       "display_name": "", "type": "string",   "description": ""},
                {"name": "BudgetType",          "display_name": "", "type": "string",   "description": ""},
                {"name": "ApprovalStatus",      "display_name": "", "type": "string",   "description": ""},
                {"name": "Notes",               "display_name": "", "type": "string",   "description": ""},
            ],
        },
        {
            "name": "customer_feedback",
            "table": "virtual.CustomerFeedback",
            "description": "",              # Empty — for AI to fill
            "primary_key": "FeedbackKey",
            "_test": True,
            "columns": [
                {"name": "FeedbackKey",         "display_name": "", "type": "integer",  "description": ""},
                {"name": "CustomerKey",         "display_name": "", "type": "integer",  "description": ""},
                {"name": "ProductKey",          "display_name": "", "type": "integer",  "description": ""},
                {"name": "OrderDateKey",        "display_name": "", "type": "integer",  "description": ""},
                {"name": "Rating",              "display_name": "", "type": "integer",  "description": ""},
                {"name": "SatisfactionScore",   "display_name": "", "type": "decimal",  "description": ""},
                {"name": "ReviewTitle",         "display_name": "", "type": "string",   "description": ""},
                {"name": "ReviewText",          "display_name": "", "type": "string",   "description": ""},
                {"name": "FeedbackChannel",     "display_name": "", "type": "string",   "description": ""},
                {"name": "IsVerifiedPurchase",  "display_name": "", "type": "boolean",  "description": ""},
                {"name": "FeedbackDate",        "display_name": "", "type": "date",     "description": ""},
            ],
        },
    ]

    # ── Relationships between test tables and existing models ──
    VIRTUAL_TEST_RELS = [
        {
            "name": "budget_targets_to_sales_territory",
            "from": "budget_targets",
            "to": "sales_territory",
            "type": "MANY_TO_ONE",
            "condition": "budget_targets.SalesTerritoryKey = sales_territory.SalesTerritoryKey",
        },
        {
            "name": "budget_targets_to_dates",
            "from": "budget_targets",
            "to": "dates",
            "type": "MANY_TO_ONE",
            "condition": "budget_targets.DateKey = dates.DateKey",
        },
        {
            "name": "budget_targets_to_product_subcategories",
            "from": "budget_targets",
            "to": "product_subcategories",
            "type": "MANY_TO_ONE",
            "condition": "budget_targets.ProductCategoryKey = product_subcategories.ProductCategoryKey",
        },
        {
            "name": "customer_feedback_to_customers",
            "from": "customer_feedback",
            "to": "customers",
            "type": "MANY_TO_ONE",
            "condition": "customer_feedback.CustomerKey = customers.CustomerKey",
        },
        {
            "name": "customer_feedback_to_products",
            "from": "customer_feedback",
            "to": "products",
            "type": "MANY_TO_ONE",
            "condition": "customer_feedback.ProductKey = products.ProductKey",
        },
        {
            "name": "customer_feedback_to_dates",
            "from": "customer_feedback",
            "to": "dates",
            "type": "MANY_TO_ONE",
            "condition": "customer_feedback.OrderDateKey = dates.DateKey",
        },
    ]

    try:
        data = _load_models_yaml()
        models_list = data.get("models", [])
        rels = data.get("relationships", [])
        existing_names = {m["name"] for m in models_list}
        existing_rel_names = {r["name"] for r in rels}

        new_models = []
        new_rels = []

        # Add virtual tables (skip if already exist)
        for table_def in VIRTUAL_TEST_TABLES:
            if table_def["name"] in existing_names:
                logger.info(f"Test table '{table_def['name']}' already exists, skipping")
                continue
            models_list.append(table_def)
            new_models.append(table_def)

        # Add relationships (only for newly added tables)
        new_model_names = {m["name"] for m in new_models}
        for rel_def in VIRTUAL_TEST_RELS:
            if rel_def["from"] not in new_model_names:
                continue
            if rel_def["name"] in existing_rel_names:
                continue
            # Verify the target model exists
            if rel_def["to"] not in existing_names and rel_def["to"] not in new_model_names:
                logger.warning(f"Skipping rel '{rel_def['name']}': target '{rel_def['to']}' not found")
                continue
            rels.append(rel_def)
            new_rels.append(rel_def)

        data["models"] = models_list
        data["relationships"] = rels
        _save_models_yaml(data)

        logger.info(f"Virtual test tables generated: {len(new_models)} models, {len(new_rels)} relationships")
        return {
            "success": True,
            "models_added": len(new_models),
            "relationships_added": len(new_rels),
            "models": [{"name": m["name"], "table": m["table"], "columns_count": len(m["columns"])} for m in new_models],
            "relationships": [{"name": r["name"], "from": r["from"], "to": r["to"]} for r in new_rels],
            "message": "Virtual test tables added to semantic layer. Use 'AI Desc' to auto-generate descriptions.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test generate error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════
# ── 3. Knowledge Management ──
# ═══════════════════════════════════════════════

# ─── Glossary ───

def _load_glossary() -> list[dict]:
    """Đọc glossary.yaml → list of term dicts."""
    path = _glossary_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and "terms" in data:
            return data["terms"]
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _save_glossary(terms: list[dict]):
    """Lưu glossary vào file."""
    path = _glossary_path()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"terms": terms},
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )


@app.get("/v1/knowledge/glossary")
def get_glossary():
    """Đọc glossary từ file."""
    terms = _load_glossary()
    # Ensure mỗi term có id
    for i, t in enumerate(terms):
        if "id" not in t:
            t["id"] = t.get("term", f"term_{i}").replace(" ", "_")
    return {"terms": terms}


@app.post("/v1/knowledge/glossary")
def add_glossary_term(req: GlossaryTermRequest):
    """Thêm term mới."""
    terms = _load_glossary()
    new_term = {
        "id": req.term.replace(" ", "_").lower(),
        "term": req.term,
        "aliases": req.aliases,
        "sql_expression": req.sql_expression,
        "description": req.description,
    }
    terms.append(new_term)
    _save_glossary(terms)
    return {"success": True, "term": new_term}


@app.put("/v1/knowledge/glossary/{term_id}")
def update_glossary_term(term_id: str, req: GlossaryTermRequest):
    """Sửa term."""
    terms = _load_glossary()
    for t in terms:
        tid = t.get("id", t.get("term", "").replace(" ", "_"))
        if tid == term_id:
            t["term"] = req.term
            t["aliases"] = req.aliases
            t["sql_expression"] = req.sql_expression
            t["description"] = req.description
            _save_glossary(terms)
            return {"success": True, "term": t}
    raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")


@app.delete("/v1/knowledge/glossary/{term_id}")
def delete_glossary_term(term_id: str):
    """Xóa term."""
    terms = _load_glossary()
    original_len = len(terms)
    terms = [
        t for t in terms
        if t.get("id", t.get("term", "").replace(" ", "_")) != term_id
    ]
    if len(terms) == original_len:
        raise HTTPException(status_code=404, detail=f"Term '{term_id}' not found")
    _save_glossary(terms)
    return {"success": True}


# ─── SQL Pairs ───

def _load_sql_pairs() -> list[dict]:
    """Đọc semantic_memory.json → list of pairs."""
    path = _memory_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "pairs" in data:
            return data["pairs"]
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _save_sql_pairs(pairs: list[dict]):
    """Lưu SQL pairs vào file."""
    path = _memory_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs}, f, ensure_ascii=False, indent=2)


@app.get("/v1/knowledge/sql-pairs")
def get_sql_pairs():
    """Đọc SQL pairs từ file."""
    pairs = _load_sql_pairs()
    for i, p in enumerate(pairs):
        if "id" not in p:
            p["id"] = str(i + 1)
    return {"pairs": pairs}


@app.post("/v1/knowledge/sql-pairs")
def add_sql_pair(req: SqlPairRequest):
    """Thêm SQL pair mới."""
    pairs = _load_sql_pairs()
    new_pair = {
        "id": str(uuid.uuid4())[:8],
        "question": req.question,
        "sql": req.sql,
        "created_at": datetime.now().isoformat()[:10],
    }
    pairs.append(new_pair)
    _save_sql_pairs(pairs)
    return {"success": True, "pair": new_pair}


@app.put("/v1/knowledge/sql-pairs/{pair_id}")
def update_sql_pair(pair_id: str, req: SqlPairRequest):
    """Sửa SQL pair."""
    pairs = _load_sql_pairs()
    for p in pairs:
        if p.get("id") == pair_id:
            p["question"] = req.question
            p["sql"] = req.sql
            _save_sql_pairs(pairs)
            return {"success": True, "pair": p}
    raise HTTPException(status_code=404, detail=f"Pair '{pair_id}' not found")


@app.delete("/v1/knowledge/sql-pairs/{pair_id}")
def delete_sql_pair(pair_id: str):
    """Xóa SQL pair."""
    pairs = _load_sql_pairs()
    original_len = len(pairs)
    pairs = [p for p in pairs if p.get("id") != pair_id]
    if len(pairs) == original_len:
        raise HTTPException(status_code=404, detail=f"Pair '{pair_id}' not found")
    _save_sql_pairs(pairs)
    return {"success": True}


# ═══════════════════════════════════════════════
# ── 4. Settings ──
# ═══════════════════════════════════════════════

@app.get("/v1/settings")
def get_settings():
    """Đọc pipeline settings hiện tại."""
    return _state["settings"]


@app.put("/v1/settings")
def update_settings(req: SettingsRequest):
    """
    Cập nhật pipeline settings.
    Áp dụng runtime — không cần re-deploy.
    """
    if req.features:
        _state["settings"]["features"].update(req.features)
    if req.generation:
        _state["settings"]["generation"].update(req.generation)

    # Rebuild AskPipeline nếu đang deployed
    if _state["deployed"] and _state["deploy_pipeline"]:
        deploy = _state["deploy_pipeline"]
        feat = _state["settings"]["features"]
        gen = _state["settings"]["generation"]
        _state["ask_pipeline"] = AskPipeline(
            manifest=deploy.manifest,
            indexer=deploy.indexer,
            engine=deploy.connector.engine,
            num_candidates=gen.get("num_candidates", 3),
            enable_column_pruning=feat.get("enable_column_pruning", True),
            enable_cot_reasoning=feat.get("enable_cot_reasoning", True),
            enable_schema_linking=feat.get("enable_schema_linking", True),
            enable_voting=feat.get("enable_voting", True),
            enable_glossary=feat.get("enable_glossary", True),
            enable_memory=feat.get("enable_memory", False),
            enable_question_translator=feat.get("enable_question_translator", True),
            glossary_path=str(_glossary_path()),
            memory_path=str(_memory_path()),
        )
        logger.info("AskPipeline rebuilt with new settings")

    return {"success": True, "settings": _state["settings"]}


# ═══════════════════════════════════════════════
# ── 5. Deploy (re-deploy, chỉ khi đã connected) ──
# ═══════════════════════════════════════════════

@app.post("/v1/deploy")
def deploy():
    """
    Re-deploy: rebuild manifest + re-index.
    Chỉ hoạt động khi đã connected.
    """
    if not _state["connected"]:
        raise HTTPException(
            status_code=503,
            detail="Chưa kết nối database. Vào /setup để kết nối.",
        )

    try:
        # Close old
        if _state.get("deploy_pipeline") and _state["deploy_pipeline"].connector:
            try:
                _state["deploy_pipeline"].connector.close()
            except Exception:
                pass

        deploy_pipeline = DeployPipeline(chroma_dir=_chroma_dir())
        result = deploy_pipeline.run()

        if result.success:
            _state["deployed"] = True
            _state["deploy_pipeline"] = deploy_pipeline

            feat = _state["settings"]["features"]
            gen = _state["settings"]["generation"]
            _state["ask_pipeline"] = AskPipeline(
                manifest=deploy_pipeline.manifest,
                indexer=deploy_pipeline.indexer,
                engine=deploy_pipeline.connector.engine,
                num_candidates=gen.get("num_candidates", 3),
                enable_column_pruning=feat.get("enable_column_pruning", True),
                enable_cot_reasoning=feat.get("enable_cot_reasoning", True),
                enable_schema_linking=feat.get("enable_schema_linking", True),
                enable_voting=feat.get("enable_voting", True),
                enable_question_translator=feat.get("enable_question_translator", True),
                glossary_path=str(_glossary_path()),
                memory_path=str(_memory_path()),
            )

        return {
            "success": result.success,
            "message": result.message,
            "models_count": result.models_count,
            "relationships_count": result.relationships_count,
            "manifest_hash": result.manifest_hash,
            "indexed": result.indexed,
        }

    except Exception as e:
        logger.error(f"Deploy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════
# ── Auto-Describe (XiYan Pipeline) ──
# ═══════════════════════════════════════════════

class AutoDescribeRequest(BaseModel):
    mode: str = "merge"                    # merge | overwrite
    tables: list[str] | None = None        # None = all tables with empty descriptions
    n_examples: int = 3                    # ChromaDB results per search
    max_tool_calls: int = 4                # Max agent tool calls per table
    model: str = "gpt-4.1-mini"


@app.post("/v1/models/auto-describe")
async def auto_describe(request: AutoDescribeRequest):
    """
    AI-assisted schema documentation generation (SSE streaming).

    Uses an agentic XiYan pipeline with LangChain ReAct agent to:
    1. Index existing descriptions into ChromaDB for few-shot retrieval
    2. Extract writing style guide from existing descriptions
    3. Batch SQL profiling for evidence-based descriptions
    4. Classify column types (ENUM, MEASURE, CODE, etc.)
    5. Generate descriptions using table-level ReAct agent
    6. Persist results into models.yaml

    Returns Server-Sent Events (SSE) for real-time progress tracking.
    """
    if not _state["connected"]:
        raise HTTPException(status_code=400, detail="Not connected. Call /v1/connections/connect first.")

    from askdataai.generation.auto_describe.pipeline import DescriptionPipeline, PipelineConfig

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            pipeline = DescriptionPipeline(settings)
            config = PipelineConfig(
                mode=request.mode,
                tables=request.tables,
                n_examples=request.n_examples,
                max_tool_calls=request.max_tool_calls,
                model=request.model,
            )

            async for event in pipeline.run_stream(config):
                yield event.to_sse()

        except Exception as e:
            logger.error(f"Auto-describe pipeline error: {e}")
            import json as _json
            yield f"data: {_json.dumps({'phase': 'error', 'status': 'error', 'progress': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════
# ── Health ──
# ═══════════════════════════════════════════════

@app.get("/health")
def health():
    """Health check."""
    return {
        "status": "ok",
        "connected": _state["connected"],
        "deployed": _state["deployed"],
    }
