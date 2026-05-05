# askDataAI — Agent guide

Vietnamese-first Text-to-SQL platform: hỏi tiếng Việt → SQL Server → kết quả + biểu đồ.
Backend FastAPI + Python, frontend Next.js, OpenAI duy nhất (chat + embedding), ChromaDB embedded.

## Top-level layout

```
mini-wren-ai/
├── askdataai/        # Python package (backend) — entry: askdataai/server.py
├── web/              # Next.js frontend
├── configs/          # User-edited YAML (models.yaml, glossary.yaml) — TRACKED
├── data/             # Runtime-generated (chroma_data/, manifests/, semantic_memory.json) — GITIGNORED
├── docs/             # Documentation
│   ├── PROJECT_OVERVIEW.md
│   ├── PROPOSAL.md
│   └── pipeline/     # Per-stage deep dives (00..16)
├── tests/            # pytest suite (uses conftest.py for sys.path)
├── Dockerfile        # Backend container
├── docker-compose.yml
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Entry points

| Component | Command |
|---|---|
| Backend (dev) | `python -m uvicorn askdataai.server:app --reload --port 8000` |
| Frontend (dev) | `cd web && npm run dev` (port 3000) |
| Full stack (Docker) | `docker compose up --build` (backend 8000, frontend 3001) |
| Tests | `pytest tests/ -x` (cần `pip install pytest`) |

## Two pipelines

1. **Deploy pipeline** (1 lần khi connect DB): `askdataai/pipelines/deploy_pipeline.py`. Đọc `configs/models.yaml` → introspect SQL Server → build Manifest → embed vào ChromaDB (3 collections: `table_descriptions`, `db_schema`, `column_descriptions` — collection cuối chỉ tạo khi `ENABLE_BIDIRECTIONAL_RETRIEVAL=true`).
2. **Ask pipeline** (mỗi câu hỏi, 16 stages): `askdataai/pipelines/ask_pipeline.py`. PIGuard → ConvCtx → VI→EN Translator → PreFilter → InstructionMatch → Intent → SubIntent → SchemaRetrieval → SchemaLinking → ColumnPruning → ContextBuild → Glossary → Memory → CoT → SQLGen+Vote → Correction → Guardian → MemorySave.

Chi tiết từng stage: `docs/pipeline/00_product_overview.md` … `16_stage14_memory_save.md`.

## Sprint feature toggles (env vars hoặc per-request override)

| Toggle | Sprint | Mặc định | File |
|---|---|---|---|
| `ENABLE_MSCHEMA` | 2 | false | `retrieval/context_builder.py` — DDL vs M-Schema |
| `ENABLE_BIDIRECTIONAL_RETRIEVAL` | 4 | false | `retrieval/schema_retriever.py` — cần re-deploy ChromaDB |
| `CORRECTION_STRATEGY` | 5 | execution_only | `generation/sql_corrector.py` — execution_only / taxonomy_guided |
| `EXEC_ROW_LIMIT` | 5.6 | 10000 | `config.py` — pipeline cắt rows khi execute final SQL |
| `ENABLE_VOTING` | — | true | `pipelines/ask_pipeline.py` |

Per-request override qua `POST /v1/ask` body field cùng tên (None = dùng settings singleton).

## Conventions

- **Imports**: tuyệt đối, `from askdataai.X import Y`. Không relative.
- **Paths**: tất cả file path resolve qua helpers ở `askdataai/server.py` (`_models_yaml_path`, `_glossary_path`, `_memory_path`, `_chroma_dir`). Khi thêm config/data file mới → thêm helper ở đó.
- **Configs vs data**: file user edit → `configs/`. File runtime ghi → `data/` (gitignored).
- **Pipeline god module**: `pipelines/ask_pipeline.py` chỉ orchestrate; logic phải nằm trong sub-package tương ứng.
- **Late-binding settings**: stages không capture `settings` ở `__init__`; đọc lazy qua `from askdataai.config import settings` để per-request override hoạt động.

## Benchmark suite (Sprint 1+)

- Dataset: `tests/eval/benchmark_dataset.yaml` — 100 mẫu Vietnamese hand-crafted trên AdventureWorks DW.
- Runner: `tests/eval/benchmark_runner.py` (HTTP → /v1/ask → exec gold → canonical_hash → fallback LLM judge).
- Output: `benchmarks/run_<sha>_<ts>_<tag>.json`.
- Run: `.\scripts\run-benchmark.ps1 -Tag <name>`.
- Latest result: EX 48% (Sprint 5.6, post-fixes). Baseline: 41%.

## Sub-package guides

- `askdataai/CLAUDE.md` — backend internals, sub-package map.
- `askdataai/generation/CLAUDE.md` — 14-stage generators + auto_describe feature.
- `askdataai/retrieval/CLAUDE.md` — context assembly pipeline.
- `web/CLAUDE.md` — Next.js conventions.

## Quick verification after changes

```bash
# 1. Syntax sanity (no deps needed)
python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('askdataai').rglob('*.py')]"

# 2. Import audit (must return 0 hits)
grep -rn "from src\." askdataai tests

# 3. Smoke
python -m uvicorn askdataai.server:app --port 8000
curl http://localhost:8000/health
```
