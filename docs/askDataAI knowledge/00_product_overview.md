# askDataAI — Tổng quan sản phẩm

## 1. Giới thiệu

**askDataAI** là nền tảng Text-to-SQL full-stack, cho phép người dùng hỏi câu hỏi bằng tiếng Việt và nhận lại SQL, kết quả truy vấn, và biểu đồ tự động. Sản phẩm được thiết kế cho doanh nghiệp Việt Nam sử dụng SQL Server.

Lấy cảm hứng từ WrenAI (open-source, 4k+ stars), askDataAI được thiết kế lại với trọng tâm:
- **Vietnamese-first**: Prompt, glossary, mô tả schema, UI đều bằng tiếng Việt
- **SQL Server**: Dialect phổ biến nhất trong doanh nghiệp Việt Nam
- **OpenAI API**: Sử dụng duy nhất OpenAI cho cả chat (GPT-4o) và embedding
- **Lightweight**: Chỉ 2 Docker containers, chạy trên 1 máy dev
- **SOTA Pipeline**: Tích hợp 6+ kỹ thuật mới nhất (Schema Linking, CoT, Multi-candidate Voting...)

## 2. Kiến trúc

```
┌───────────────────┐       ┌──────────────────────────────────┐
│  Next.js Frontend │──API─▶│  FastAPI Backend (Python)         │
│  (port 3000)      │       │                                  │
│                   │       │  ┌────────────────────────────┐  │
│  - Chat           │       │  │  Ask Pipeline (14 stages)  │  │
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
models.yaml → SchemaIntrospector → ManifestBuilder → SchemaIndexer (ChromaDB)
```

- **SchemaIntrospector**: Đọc metadata từ SQL Server (INFORMATION_SCHEMA)
- **ManifestBuilder**: Kết hợp YAML config + metadata → tạo Manifest (semantic layer)
- **SchemaIndexer**: Embed descriptions bằng OpenAI Embedding → index vào ChromaDB

### 3.2 Ask Pipeline — Xử lý câu hỏi

Chạy **mỗi câu hỏi**. Pipeline chính với **14 stages**, chia thành 3 giai đoạn:

```
question
  │
  ▼  ── Giai đoạn 1: Pre-Processing (không LLM, instant) ──
  [1] PreFilter ──▶ [2] InstructionMatch
  │
  ▼  ── Giai đoạn 2: Understanding (LLM + Vector Search) ──
  [3] IntentClassify ──▶ [4] SubIntentDetect
  [5] SchemaRetrieval ──▶ [6] SchemaLinking ──▶ [7] ColumnPruning
  [8] ContextBuild ──▶ [9] GlossaryInject ──▶ [10] MemoryLookup
  [11] CoT Reasoning
  │
  ▼  ── Giai đoạn 3: Generation & Validation (LLM + DB) ──
  [12] SQL Generation (multi-candidate + vote)
  [13] SQL Correction (execute + retry loop)
  [13.5] Guardian (5-layer security)
  [14] MemorySave
  │
  ▼
  Result (SQL + data + chart)
```

#### Bảng tổng hợp pipeline

| # | Stage | LLM? | Vai trò |
|---|---|:---:|---|
| 1 | **PreFilter** | Không | Lọc nhanh: greeting, destructive, schema-explore (regex) |
| 2 | **InstructionMatch** | Không | Inject business rules đã cấu hình (keyword matching) |
| 3 | **IntentClassifier** | Co | Phân loại: TEXT_TO_SQL / GENERAL / AMBIGUOUS / SCHEMA_EXPLORE |
| 4 | **SubIntentDetect** | Co | Phân loại chi tiết: RETRIEVAL / AGGREGATION / RANKING / TREND / COMPARISON |
| 5 | **SchemaRetrieval** | Không | Vector search (OpenAI Embedding + ChromaDB) → tìm bảng liên quan + FK expansion |
| 6 | **SchemaLinking** | Co | Map entity trong câu hỏi → table.column cụ thể ("khách hàng" → customers) |
| 7 | **ColumnPruning** | Co | Loại cột không liên quan, giữ PK/FK (auto-skip nếu ≤ 15 cột) |
| 8 | **ContextBuilder** | Không | Build DDL text với descriptions tiếng Việt cho LLM đọc |
| 9 | **GlossaryLookup** | Không | Tra cứu thuật ngữ nghiệp vụ: "doanh thu" → `SUM(SalesAmount)` |
| 10 | **SemanticMemory** | Không | Tìm câu hỏi tương tự đã thành công, inject SQL mẫu (few-shot) |
| 11 | **CoTReasoning** | Co | Chain-of-Thought: lập kế hoạch truy vấn trước khi viết SQL |
| 12 | **SQLGeneration** | Co | Sinh N SQL candidates (3 strategies) + execution-based majority voting |
| 13 | **SQLCorrection** | Co | Chạy SQL thật trên DB, nếu lỗi → LLM sửa (max 3 retries) |
| 13.5 | **Guardian** | Không | 5-layer security: injection, read-only, whitelist, RLS, column masking |
| 14 | **MemorySave** | Không | Lưu kết quả thành công → self-learning cho lần sau |

#### LLM Budget

| Scenario | LLM calls | Mô tả |
|---|:---:|---|
| Tối thiểu | 2 | Intent(1) + SQLGenerator(1) — tất cả optional stages tắt |
| Typical | 7 | Intent + SchemaLink + Prune + CoT + 3 Candidates |
| Tối đa | 12 | Tất cả bật + 5 candidates + 3 correction retries |

#### Luồng dữ liệu qua pipeline

1. **PreFilter + InstructionMatch**: Lọc bỏ câu hỏi không cần xử lý, inject business rules
2. **IntentClassifier**: Nếu không phải TEXT_TO_SQL → dừng ngay (tiết kiệm 5–10 LLM calls)
3. **SchemaRetrieval → SchemaLinking → ColumnPruning**: Tìm bảng liên quan, map entity, loại cột dư → tạo schema context gọn nhất cho LLM
4. **ContextBuilder + Glossary + Memory**: Enriched DDL = DDL + business glossary + SQL mẫu từ quá khứ
5. **CoT Reasoning**: LLM lập kế hoạch truy vấn chi tiết (tables, joins, aggregations, filters)
6. **SQL Generation + Voting**: Sinh 3 SQL với strategies khác nhau → chạy thật trên DB → majority vote chọn SQL tốt nhất
7. **SQL Correction**: Nếu SQL lỗi → LLM nhận error message và tự sửa (max 3 retries)
8. **Guardian**: Kiểm tra bảo mật 5 lớp trước khi trả kết quả
9. **MemorySave**: Lưu trace để hệ thống tự học

Chi tiết từng stage xem trong các file riêng (`02_stage1_prefilter.md` → `16_stage14_memory_save.md`).

## 4. Tính năng chính

| Tính năng | Mô tả |
|---|---|
| **Text-to-SQL** | Hỏi tiếng Việt → sinh SQL chính xác |
| **Auto Chart** | Tạo biểu đồ Vega-Lite (bar, line, pie...) từ kết quả |
| **SQL Guardian** | 5-layer security: injection, read-only, whitelist, RLS, masking |
| **Business Glossary** | Ánh xạ thuật ngữ nghiệp vụ → SQL |
| **Semantic Memory** | Học từ queries thành công trước đó (self-learning) |
| **Debug Trace** | Xem chi tiết input/output từng stage |
| **Data Modeling** | ERD visualization + metadata editor |
| **Multi-Hop** | Xử lý câu hỏi cần JOIN nhiều bảng |

## 5. Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Backend | Python 3.10+, FastAPI, SQLAlchemy |
| Frontend | Next.js 14, React, Ant Design |
| LLM (Chat) | OpenAI API (GPT-4o / GPT-4o-mini) |
| Embedding | OpenAI API (text-embedding-3-small) |
| Vector DB | ChromaDB (embedded) |
| Database | SQL Server (ODBC Driver 17) |
| Charts | Vega-Lite |
| Deployment | Docker Compose |

## 6. Cấu trúc thư mục

```
askDataAI/
├── src/
│   ├── server.py              # FastAPI entry point
│   ├── config.py              # Environment config
│   ├── connectors/            # SQL Server connector
│   ├── modeling/              # Manifest, Schema introspection
│   ├── indexing/              # Embedder, Vector store, Schema indexer
│   ├── retrieval/             # Schema retrieval, linking, pruning, glossary
│   ├── generation/            # LLM stages: intent, SQL gen, correction, memory
│   ├── security/              # SQL Guardian
│   └── pipelines/             # Ask pipeline, Deploy pipeline, Tracer
├── web/                       # Next.js frontend
├── models.yaml                # Semantic model definitions
├── glossary.yaml              # Business glossary
├── semantic_memory.json       # Query memory store
├── docker-compose.yml         # Orchestration
└── requirements.txt           # Python dependencies
```
