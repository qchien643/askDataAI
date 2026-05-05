# askDataAI — Tổng quan sản phẩm

## 1. Giới thiệu

**askDataAI** là nền tảng Text-to-SQL full-stack, cho phép người dùng hỏi câu hỏi bằng tiếng Việt và nhận lại SQL, kết quả truy vấn, và biểu đồ tự động. Sản phẩm được thiết kế cho doanh nghiệp Việt Nam sử dụng SQL Server.

Lấy cảm hứng từ WrenAI (open-source, 4k+ stars), askDataAI được thiết kế lại với trọng tâm:
- **Vietnamese-first**: UI, glossary, mô tả schema, business rules đều bằng tiếng Việt; câu hỏi được dịch tiếng Anh nội bộ trước khi vào pipeline LLM (Stage 0.7 Translator)
- **SQL Server**: Dialect phổ biến nhất trong doanh nghiệp Việt Nam
- **OpenAI API**: Sử dụng duy nhất OpenAI cho cả chat (GPT-4o-mini) và embedding (text-embedding-3-small)
- **Lightweight**: Chỉ 2 Docker containers, chạy trên 1 máy dev
- **SOTA Pipeline**: Tích hợp các kỹ thuật mới nhất — M-Schema (XiYan-SQL), Bidirectional Retrieval, Taxonomy-Guided Correction (SQL-of-Thought), CoT Reasoning, Multi-Candidate Voting

## 2. Kiến trúc

```
┌───────────────────┐       ┌──────────────────────────────────┐
│  Next.js Frontend │──API─▶│  FastAPI Backend (Python)         │
│  (port 3000)      │       │                                  │
│                   │       │  ┌────────────────────────────┐  │
│  - Chat (SSE)     │       │  │  Ask Pipeline (16 stages)  │  │
│  - Modeling (ERD) │       │  └─────────┬──────────────────┘  │
│  - Glossary       │       │            │                     │
│  - Settings       │       │  ┌─────────▼───┐  ┌──────────┐  │
│  - Debug Trace    │       │  │  ChromaDB    │  │SQL Server│  │
└───────────────────┘       │  │  (Vectors)   │  │(Data)    │  │
                             │  └─────────────┘  └──────────┘  │
                             │            │                     │
                             │  ┌─────────▼─────────────────┐  │
                             │  │       OpenAI API           │  │
                             │  │  Chat + Embedding          │  │
                             │  └───────────────────────────┘  │
                             └──────────────────────────────────┘
```

## 3. Hai Pipeline chính

### 3.1 Deploy Pipeline
Chạy **1 lần** khi kết nối database. Không gọi LLM.

```
configs/models.yaml → SchemaIntrospector → ManifestBuilder → SchemaIndexer (ChromaDB)
```

- **SchemaIntrospector**: Đọc metadata từ SQL Server (INFORMATION_SCHEMA)
- **ManifestBuilder**: Kết hợp YAML config + metadata → tạo Manifest (semantic layer)
- **SchemaIndexer**: Embed descriptions bằng OpenAI Embedding → index vào 3 ChromaDB collections:
  - `table_descriptions` — 1 vector per table
  - `db_schema` — TABLE + TABLE_COLUMNS docs
  - `column_descriptions` — 1 vector per column (chỉ khi `ENABLE_BIDIRECTIONAL_RETRIEVAL=true`, Sprint 4)

### 3.2 Ask Pipeline — Xử lý câu hỏi

Chạy **mỗi câu hỏi**. 16 stages, chia thành 4 giai đoạn:

```
question
  │
  ▼  ── Giai đoạn 0: Security & Context (LLM tối thiểu) ──
  [0] PIGuardrail (offline, local model)
  [0.5] ConversationContextEngine (mem0)
  [0.7] QuestionTranslator (VI → EN, Co)
  │
  ▼  ── Giai đoạn 1: Pre-Processing (instant, không LLM) ──
  [1] PreFilter ──▶ [2] InstructionMatch
  │
  ▼  ── Giai đoạn 2: Understanding (LLM + Vector Search) ──
  [3] IntentClassify ──▶ [4] SubIntentDetect
  [5] SchemaRetrieval (legacy hoặc bidirectional, Sprint 4)
  [6] SchemaLinking ──▶ [7] ColumnPruning
  [8] ContextBuild (DDL hoặc M-Schema, Sprint 2)
  [9] GlossaryInject ──▶ [10] MemoryLookup
  [11] CoT Reasoning
  │
  ▼  ── Giai đoạn 3: Generation & Validation (LLM + DB) ──
  [12] SQL Generation (multi-candidate + vote, hoặc single-pass nếu voting OFF)
  [13] SQL Correction (execution_only hoặc taxonomy_guided, Sprint 5)
  [13.5] Guardian (5-layer security)
  [14] MemorySave
  │
  ▼
  Result (SQL + data + chart)
```

### Bảng tổng hợp pipeline

| # | Stage | LLM? | Vai trò |
|---|---|:---:|---|
| 0 | **PIGuardrail** | × | Offline local model phát hiện prompt injection |
| 0.5 | **ConversationContextEngine** | × | mem0 inject context từ session trước |
| 0.7 | **QuestionTranslator** | ✓ | Dịch VI → EN cho pipeline (skip nếu đã EN) |
| 1 | **PreFilter** | × | Lọc nhanh: greeting, destructive, schema-explore (regex) |
| 2 | **InstructionMatch** | × | Inject business rules đã cấu hình (keyword matching) |
| 3 | **IntentClassifier** | ✓ | Phân loại: TEXT_TO_SQL / GENERAL / AMBIGUOUS / SCHEMA_EXPLORE |
| 4 | **SubIntentDetect** | ✓ | Phân loại chi tiết: RETRIEVAL / AGGREGATION / RANKING / TREND / COMPARISON |
| 5 | **SchemaRetrieval** | × hoặc ✓¹ | Vector search → tìm bảng + FK 1-hop. Bidirectional thêm column-first path (1 LLM call augmenter) |
| 6 | **SchemaLinking** | ✓ | Map entity trong câu hỏi → table.column |
| 7 | **ColumnPruning** | ✓ | Loại cột không liên quan, giữ PK/FK (auto-skip nếu ≤ 15 cột) |
| 8 | **ContextBuilder** | × | Build DDL hoặc M-Schema² text cho LLM đọc |
| 9 | **GlossaryLookup** | × | Tra cứu thuật ngữ nghiệp vụ: "doanh thu" → `SUM(SalesAmount)` |
| 10 | **SemanticMemory** | × | Tìm câu hỏi tương tự đã thành công, inject SQL mẫu (few-shot) |
| 11 | **CoTReasoning** | ✓ | Chain-of-Thought: lập kế hoạch truy vấn trước khi viết SQL |
| 12 | **SQLGeneration** | ✓ | Sinh N SQL candidates + execution-based majority voting (skip nếu voting OFF) |
| 13 | **SQLCorrection** | ✓ | Chạy SQL thật trên DB, retry max 2-3 lần. 2 strategies: execution_only / taxonomy_guided³ |
| 13.5 | **Guardian** | × | 5-layer security: injection, read-only, whitelist, RLS, column masking |
| 14 | **MemorySave** | × | Lưu kết quả thành công → self-learning cho lần sau |

¹ `ENABLE_BIDIRECTIONAL_RETRIEVAL=true` — xem [stage 5 doc](06_stage5_schema_retrieval.md)
² `ENABLE_MSCHEMA=true` — xem [stage 8 doc](09_stage8_context_builder.md)
³ `CORRECTION_STRATEGY=taxonomy_guided` — xem [stage 13 doc](14_stage13_sql_correction.md)

### LLM Budget

| Scenario | LLM calls | Mô tả |
|---|:---:|---|
| Tối thiểu | 3 | Translator + Intent + SQLGenerator (tất cả optional stages tắt) |
| Typical | 8-9 | Translator + Intent + SchemaLink + Prune + CoT + 3 Candidates |
| Tối đa | 14 | Tất cả bật: Translator + Intent + SubIntent + Augmenter + SchemaLink + Prune + CoT + 5 Candidates + 2 taxonomy retries (Plan+Fix) |

### Per-request override

`POST /v1/ask` body có thể chứa toggles để override settings cho 1 request:
```json
{
  "question": "...",
  "enable_mschema": false,
  "enable_bidirectional_retrieval": true,
  "correction_strategy": "execution_only",
  "enable_glossary": true,
  "enable_memory": false
}
```

Hữu ích cho ablation studies. Per-request > settings singleton > .env defaults.

## 4. Tính năng chính

| Tính năng | Mô tả |
|---|---|
| **Text-to-SQL** | Hỏi tiếng Việt → sinh SQL chính xác |
| **Auto Chart** | Tạo biểu đồ Vega-Lite (bar, line, pie...) từ kết quả |
| **SQL Guardian** | 5-layer security: injection, read-only, whitelist, RLS, masking |
| **Business Glossary** | Ánh xạ thuật ngữ nghiệp vụ → SQL hint |
| **Semantic Memory** | Học từ queries thành công trước đó (self-learning) |
| **Debug Trace** | Xem chi tiết input/output từng stage |
| **Data Modeling** | ERD visualization + metadata editor |
| **Multi-Hop** | Xử lý câu hỏi cần JOIN nhiều bảng |
| **PI Guardrail** | Local model offline (downloaded 1 lần) chống prompt injection |
| **Multi-turn Conversation** | mem0-based context, session_id duy trì qua turns |

## 5. Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Backend | Python 3.10+, FastAPI, SQLAlchemy, Pydantic v2 |
| Frontend | Next.js 14, React, Ant Design |
| LLM (Chat) | OpenAI API (GPT-4o-mini default; configurable) |
| Embedding | OpenAI API (text-embedding-3-small) |
| Vector DB | ChromaDB (embedded, persisted ở `data/chroma_data/`) |
| Database | SQL Server (ODBC Driver 17) |
| Charts | Vega-Lite |
| PI Guard | Local Hugging Face model (downloaded qua `scripts/download_models.ps1`) |
| Deployment | Docker Compose |
| Tests | pytest + benchmark runner (canonical_hash + LLM judge) |

## 6. Cấu trúc thư mục

```
mini-wren-ai/
├── askdataai/                # Python package (backend) — entry: askdataai/server.py
│   ├── config.py             # Pydantic Settings singleton (.env loader)
│   ├── server.py             # FastAPI app
│   ├── connectors/           # SQL Server connector + introspection
│   ├── modeling/             # Manifest, MDL Pydantic schema
│   ├── indexing/             # Embedder + ChromaDB store + 3 chunkers
│   ├── retrieval/            # Schema retrieval (legacy + bidirectional), context builder, glossary
│   ├── generation/           # 14-stage LLM stages + auto_describe (forbidden) + correction_planner/fixer
│   ├── security/             # PI Guard + SQL Guardian
│   └── pipelines/            # ask_pipeline.py (god module) + deploy_pipeline.py + tracer.py
├── web/                      # Next.js frontend
├── configs/                  # User-edited YAML — TRACKED
│   ├── models.yaml           # Semantic models (enriched với examples + range + foreign_key — Sprint 3)
│   └── glossary.yaml         # Business glossary
├── data/                     # Runtime — GITIGNORED
│   ├── chroma_data/          # Vector store
│   ├── manifests/            # Compiled manifest cache
│   └── semantic_memory.json  # Memory store
├── tests/eval/               # Benchmark suite (Sprint 1+)
│   ├── benchmark_dataset.yaml  # 100 hand-crafted Vietnamese samples
│   ├── benchmark_runner.py     # HTTP runner + canonical_hash + LLM judge
│   ├── canonical_hash.py
│   ├── llm_judge.py            # Fallback judge khi exact mismatch
│   └── analyze_failures.py     # Categorize failure patterns
├── benchmarks/               # JSON output (gitignored)
├── docs/                     # Tài liệu
│   ├── PROJECT_OVERVIEW.md
│   ├── PROPOSAL.md
│   └── pipeline/             # Per-stage deep dives (file này nằm trong)
├── scripts/                  # PowerShell helpers (start, clean, run-benchmark, ...)
├── docker-compose.yml
├── requirements.txt
└── .env                      # Local config (gitignored)
```

## 7. Sprint history (cải tiến từ baseline WrenAI-style)

| Sprint | Nội dung | Toggle |
|---|---|---|
| 1 | Hand-craft 100-sample benchmark (Vietnamese), canonical_hash + LLM judge | — |
| 2 | M-Schema format (Pydantic Column extended với examples/range/foreign_key) | `ENABLE_MSCHEMA` |
| 3 | Claude rewrites configs/models.yaml với data sampled từ DB (descriptions, examples, ranges, FK inline) | — |
| 4 | Bidirectional retrieval (QuestionAugmenter + column_descriptions ChromaDB collection) | `ENABLE_BIDIRECTIONAL_RETRIEVAL` |
| 5 | Taxonomy-guided correction (CorrectionPlanner + CorrectionFixer + 25 sub-categories error_taxonomy.yaml) | `CORRECTION_STRATEGY` |
| 5.5 | Audit Sprint 2-5 — verify legacy paths preserved | — |
| 5.6 | Bug fixes: LIMIT 100 cutoff, taxonomy retry cap, toggle late-binding, enable_glossary/memory wiring | `EXEC_ROW_LIMIT` |

Benchmark trên 100 mẫu (AdventureWorks DW):
- Baseline (Sprint 1): EX 41%
- Sprint 2-5 ON: EX 41% (plateau do bug LIMIT 100)
- Sprint 5.6 fixes: **EX 48%** (+7%, easy +16.6%)
