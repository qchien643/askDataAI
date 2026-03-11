"""
Mini Wren AI - FastAPI Server.

Tương đương wren-ai-service trong WrenAI gốc, nhưng đơn giản hơn:
- Synchronous (không async polling)
- 4 endpoints: deploy, ask, sql/execute, models

Chạy:
    cd mini-wren-ai
    .\\venv\\Scripts\\activate
    python -m uvicorn src.server:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from decimal import Decimal
from datetime import date, datetime
from typing import Any

import sqlalchemy
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import settings
from src.pipelines.deploy_pipeline import DeployPipeline
from src.pipelines.ask_pipeline import AskPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mini-wren-ai")


# ── Global state ──
_state: dict[str, Any] = {
    "deployed": False,
    "deploy_pipeline": None,
    "ask_pipeline": None,
}


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: auto-deploy nếu models.yaml tồn tại."""
    logger.info("Mini Wren AI starting...")
    try:
        deploy = DeployPipeline()
        result = deploy.run()
        if result.success:
            _state["deployed"] = True
            _state["deploy_pipeline"] = deploy
            _state["ask_pipeline"] = AskPipeline(
                manifest=deploy.manifest,
                indexer=deploy.indexer,
                engine=deploy.connector.engine,
            )
            logger.info(
                f"Auto-deployed: {result.models_count} models, "
                f"{result.relationships_count} relationships"
            )
        else:
            logger.warning(f"Auto-deploy failed: {result.message}")
    except Exception as e:
        logger.warning(f"Auto-deploy skipped: {e}")

    yield

    # Shutdown
    if _state.get("deploy_pipeline") and _state["deploy_pipeline"].connector:
        _state["deploy_pipeline"].connector.close()
    logger.info("Mini Wren AI stopped.")


# ── App ──
app = FastAPI(
    title="Mini Wren AI",
    description="Text-to-SQL với SQL Server, tương đương phiên bản đơn giản của WrenAI",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ──
class AskRequest(BaseModel):
    question: str


class SQLExecuteRequest(BaseModel):
    sql: str
    limit: int = 100


# ── Helpers ──
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
            detail="Server chưa deploy. Gọi POST /v1/deploy trước.",
        )


# ── Endpoints ──

@app.post("/v1/deploy")
def deploy():
    """
    Deploy manifest: đọc models.yaml → build → index ChromaDB.

    Tương đương POST /v1/semantics-preparations trong WrenAI gốc.
    """
    try:
        # Close old connections
        if _state.get("deploy_pipeline") and _state["deploy_pipeline"].connector:
            try:
                _state["deploy_pipeline"].connector.close()
            except Exception:
                pass

        deploy = DeployPipeline()
        result = deploy.run()

        if result.success:
            _state["deployed"] = True
            _state["deploy_pipeline"] = deploy
            _state["ask_pipeline"] = AskPipeline(
                manifest=deploy.manifest,
                indexer=deploy.indexer,
                engine=deploy.connector.engine,
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


@app.post("/v1/ask")
def ask(request: AskRequest):
    """
    Hỏi câu hỏi → chạy full pipeline → trả SQL + data.

    Tương đương POST /v1/asks + GET /v1/asks/{id}/result trong WrenAI gốc,
    nhưng synchronous (trả luôn trong 1 response).
    """
    _ensure_deployed()

    try:
        result = _state["ask_pipeline"].ask(request.question)

        return _serialize({
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
        })

    except Exception as e:
        logger.error(f"Ask error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/sql/execute")
def execute_sql(request: SQLExecuteRequest):
    """
    Chạy SQL trực tiếp trên DB.

    Tương đương POST /v2/connector/query trong ibis-server.
    """
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


@app.get("/v1/models")
def get_models():
    """
    Xem models đang có.

    Trả về danh sách models với columns và relationships.
    """
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


@app.get("/health")
def health():
    """Health check."""
    return {
        "status": "ok",
        "deployed": _state["deployed"],
    }
