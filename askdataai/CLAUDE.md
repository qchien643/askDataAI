# askdataai/ — backend internals

Python package chứa toàn bộ logic backend. Entry: `server.py` (FastAPI).

## Sub-package map

| Folder | Vai trò |
|---|---|
| `connectors/` | SQL Server connection + INFORMATION_SCHEMA introspection |
| `indexing/` | OpenAI embedding + ChromaDB vector store |
| `modeling/` | Manifest builder (semantic layer từ YAML + DB metadata), manifest deployer |
| `retrieval/` | Schema retrieval, linking, pruning, context building, glossary lookup → xem `retrieval/CLAUDE.md` |
| `generation/` | 14-stage LLM stages (intent, sub-intent, CoT, SQL gen, correction, ...) + `auto_describe/` sub-feature → xem `generation/CLAUDE.md` |
| `pipelines/` | Orchestrators: `ask_pipeline.py` (god module, 14 stages) + `deploy_pipeline.py` (3 stages) + `tracer.py` |
| `security/` | Prompt injection guard (`pi_guardrail.py`), SQL Guardian (5-layer), policies |

## Key files

- **`server.py`** — FastAPI app. Đường dẫn file resolve qua các helpers `_models_yaml_path()`, `_glossary_path()`, `_memory_path()`, `_chroma_dir()` (tất cả nằm gần đầu file ~L259). Khi thêm config/data file mới → thêm helper tại đây, dùng `PROJECT_ROOT` constant.
- **`config.py`** — Pydantic `Settings` singleton. Đọc `.env` ở repo root. Mọi env var khai báo ở đây.

## Import convention

Tuyệt đối, luôn `from askdataai.X import Y`:

```python
from askdataai.config import settings
from askdataai.modeling.mdl_schema import Manifest
from askdataai.generation.llm_client import LLMClient
```

Không dùng relative imports (`from .foo import bar`).

## Coupling map (high level)

- **God module**: `pipelines/ask_pipeline.py` — 27 imports, orchestrate cả 14 stages. KHÔNG đặt logic mới vào đây; đẩy vào sub-package phù hợp.
- **Shared utilities** (imported by many):
  - `generation/llm_client.py` — wrapper OpenAI chat (15 importers)
  - `modeling/mdl_schema.py` — Pydantic data models (9 importers)
  - `indexing/embedder.py` + `indexing/vector_store.py` — vector layer
  - `connectors/connection.py` — SQL Server connector
- **Leaf modules** (data structures, không import siblings): `mdl_schema.py`, `connectors/exceptions.py`.

## Khi thêm stage/feature mới

1. Tạo file trong sub-package phù hợp (`generation/` cho LLM stage, `retrieval/` cho schema work, `security/` cho guard).
2. Inject `LLMClient` qua DI (đừng tạo client mới).
3. Wire vào `pipelines/ask_pipeline.py` — orchestrate, không inline logic.
4. Có toggle: thêm flag vào `config.py` Settings, expose qua `/v1/settings` endpoint.
