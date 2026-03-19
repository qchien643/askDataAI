# 🧠 Mini Wren AI — Text-to-SQL

Phiên bản đơn giản của [WrenAI](https://github.com/Canner/WrenAI) — hỏi câu hỏi bằng tiếng Việt, sinh SQL, trả kết quả từ SQL Server.

## Kiến trúc tổng quan

Hệ thống gồm **2 pipeline**: Deploy (chạy 1 lần khi khởi động) và Ask (chạy mỗi câu hỏi).

```
                    ┌─────── DEPLOY PIPELINE (1 lần) ───────┐
                    │                                        │
  models.yaml ──→ ManifestBuilder ──→ SchemaIndexer ──→ ChromaDB
                                                          │
                    ┌─────── ASK PIPELINE (mỗi câu hỏi) ──┘
                    │
  User Question ──→ [1] Intent Classifier (LLM)
                    │   ↓ TEXT_TO_SQL
                    [2] Schema Retriever (ChromaDB vector search)
                    │
                    [3] Schema Linker (LLM, toggleable)
                    [4] Column Pruner (LLM, toggleable)
                    [5] Context Builder (DDL formatting)
                    [6] Glossary Injection (keyword match, toggleable)
                    [7] Memory Lookup (Jaccard similarity, toggleable)
                    [8] CoT Reasoning (LLM, toggleable)
                    │
              ┌─────┴─────┐
              │ voting=on  │ voting=off
              ▼            ▼
  [9] Multi-Candidate   [9] SQL Generator
      Generator (N×LLM)     (1 LLM call)
  [10] Execution Voter       │
       (DB execution)        │
              │               │
              └───────┬───────┘
                      ▼
              [11] SQL Corrector (execute + LLM retry)
              [12] Memory Save
                      ▼
                   Result (SQL + data)
```

### Các tính năng bật/tắt (qua API hoặc Gradio UI)

| Tính năng | Toggle | Mô tả | LLM? |
|-----------|--------|-------|------|
| Schema Linking | `enable_schema_linking` | Map entity → table.column | ✅ |
| Column Pruning | `enable_column_pruning` | Loại bỏ cột không liên quan | ✅ |
| CoT Reasoning | `enable_cot_reasoning` | Suy luận từng bước trước khi sinh SQL | ✅ |
| Voting | `enable_voting` | Sinh N SQL candidates + majority vote | ✅×N |
| Glossary | `enable_glossary` | Inject thuật ngữ nghiệp vụ | ❌ |
| Memory | `enable_memory` | Few-shot từ lịch sử thành công | ❌ |
| Candidates | `num_candidates` | Số SQL candidates (1-5) | — |

> 📄 Phân tích chi tiết từng node: xem [PIPELINE_ANALYSIS.md](PIPELINE_ANALYSIS.md)

## Cấu trúc project

```
mini-wren-ai/
├── src/
│   ├── connectors/          # Kết nối DB + đọc metadata
│   │   ├── connection.py          # SQLServerConnector (SQLAlchemy)
│   │   └── schema_introspector.py # Đọc tables, columns, FKs từ DB
│   ├── modeling/             # Data model layer
│   │   ├── mdl_schema.py          # Manifest, Model, Column, Relationship
│   │   ├── manifest_builder.py    # Build manifest từ models.yaml
│   │   └── deploy.py              # Lưu manifest, tính hash
│   ├── indexing/             # Vector indexing (ChromaDB)
│   │   ├── embedder.py            # HuggingFace embedding API
│   │   ├── vector_store.py        # ChromaDB wrapper
│   │   └── schema_indexer.py      # Index manifest → 2 collections
│   ├── retrieval/            # Tìm schema liên quan
│   │   ├── schema_retriever.py    # Vector search + relationship expansion
│   │   ├── schema_linker.py       # LLM: entity → table.column mapping
│   │   ├── column_pruner.py       # LLM: loại bỏ cột không liên quan
│   │   ├── context_builder.py     # Build DDL context cho LLM
│   │   └── business_glossary.py   # Keyword-based glossary lookup
│   ├── generation/           # Sinh SQL + xử lý
│   │   ├── llm_client.py          # OpenAI-compatible wrapper
│   │   ├── intent_classifier.py   # Phân loại câu hỏi (LLM)
│   │   ├── sql_generator.py       # Sinh SQL (LLM)
│   │   ├── sql_reasoner.py        # Chain-of-Thought reasoning (LLM)
│   │   ├── candidate_generator.py # Multi-candidate generation (N×LLM)
│   │   ├── execution_voter.py     # Execution-based voting (DB)
│   │   ├── sql_rewriter.py        # Model names → DB table names
│   │   ├── sql_corrector.py       # Validate + auto-correct (LLM retry)
│   │   └── semantic_memory.py     # Lưu/truy xuất execution traces
│   ├── pipelines/
│   │   ├── ask_pipeline.py        # Pipeline chính (12 bước)
│   │   └── deploy_pipeline.py     # Pipeline deploy
│   ├── server.py             # FastAPI server
│   └── config.py             # Settings (.env)
├── models.yaml               # Định nghĩa business models
├── glossary.yaml             # Bảng thuật ngữ nghiệp vụ
├── semantic_memory.json      # Lịch sử execution traces
├── gradio_app.py             # Gradio Chat UI
├── PIPELINE_ANALYSIS.md      # Phân tích chi tiết pipeline
├── API_DOCS.md               # API documentation
├── .env.example              # Template cấu hình
└── requirements.txt
```

## Cài đặt & Khởi động

### Yêu cầu

- Python 3.11+
- SQL Server (với database AdventureWorksDW2025)
- ODBC Driver 17 for SQL Server

### Bước 1: Clone & cài đặt

```bash
git clone https://github.com/duongvan17/text_to_sql.git
cd text_to_sql/mini-wren-ai

# Tạo virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # Linux/Mac

# Cài dependencies
pip install -r requirements.txt
```

### Bước 2: Cấu hình `.env`

```bash
copy .env.example .env
# Mở .env và sửa các giá trị:
```

```env
# SQL Server
SQL_SERVER_HOST=localhost
SQL_SERVER_PORT=1433
SQL_SERVER_DB=AdventureWorksDW2025
SQL_SERVER_USER=sa
SQL_SERVER_PASS=your_password

# LLM (OpenAI-compatible — dùng GitHub Models, OpenAI, hoặc bất kỳ API compatible)
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://models.github.ai/inference

# HuggingFace Embeddings
HUGGINGFACE_API_KEY=your_key
```

### Bước 3: Khởi động FastAPI server

```bash
.\venv\Scripts\activate
python -m uvicorn src.server:app --reload --port 8000
```

Server tự động deploy manifest + index ChromaDB khi khởi động.

- 🔗 Swagger UI: http://localhost:8000/docs
- 🔗 Health check: http://localhost:8000/health

### Bước 4: Khởi động Gradio Chat UI (tuỳ chọn)

```bash
# Mở terminal thứ 2
.\venv\Scripts\activate
python gradio_app.py
```

- 🔗 Chat UI: http://localhost:7860

## API Endpoints

| Method | Endpoint | Chức năng |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/v1/deploy` | Deploy manifest + index ChromaDB |
| POST | `/v1/ask` | Hỏi câu hỏi → SQL + data |
| POST | `/v1/sql/execute` | Chạy SQL trực tiếp |
| GET | `/v1/models` | Xem models + relationships |

### Ví dụ: Ask

```bash
curl -X POST http://localhost:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Top 5 khách hàng mua nhiều hàng nhất",
    "enable_schema_linking": true,
    "enable_column_pruning": true,
    "enable_cot_reasoning": true,
    "enable_voting": true,
    "enable_glossary": true,
    "enable_memory": true,
    "num_candidates": 3
  }'
```

Chi tiết đầy đủ: xem [API_DOCS.md](API_DOCS.md)

## Tech Stack

| Thành phần | Công nghệ |
|------------|-----------|
| Database | SQL Server (AdventureWorksDW2025) |
| LLM | OpenAI-compatible API (GitHub Models / `gpt-4.1-mini`) |
| Embeddings | HuggingFace `multilingual-e5-large` |
| Vector Store | ChromaDB |
| API Server | FastAPI + Uvicorn |
| Chat UI | Gradio |
