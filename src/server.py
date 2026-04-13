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

from src.config import settings
from src.connectors.connection import SQLServerConnector
from src.pipelines.deploy_pipeline import DeployPipeline
from src.pipelines.ask_pipeline import AskPipeline
from src.generation.chart_generator import ChartGenerator

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
    debug: bool = False  # Bật debug trace để xem pipeline stages


class SQLExecuteRequest(BaseModel):
    sql: str
    limit: int = 100


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


class ModelUpdateRequest(BaseModel):
    description: str | None = None
    columns: list[ColumnUpdateData] | None = None


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
    return PROJECT_ROOT / "glossary.yaml"


def _memory_path() -> Path:
    return PROJECT_ROOT / "semantic_memory.json"


def _chroma_dir() -> str:
    return str(PROJECT_ROOT / "chroma_data")


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

                result = _state["ask_pipeline"].ask(
                    request.question,
                    overrides=overrides,
                    debug=request.debug,
                    session_id=request.session_id or str(uuid.uuid4()),
                    on_progress=on_progress,
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
        from src.generation.llm_client import LLMClient
        from src.config import settings
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
    return PROJECT_ROOT / "models.yaml"


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
