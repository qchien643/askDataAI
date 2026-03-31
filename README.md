# Mini Wren AI

**Text-to-SQL Platform** — Hỏi câu hỏi bằng tiếng Việt, nhận SQL + kết quả + biểu đồ tự động.

Lấy cảm hứng từ [WrenAI](https://github.com/Canner/WrenAI), rút gọn và tối ưu cho **SQL Server** + **tiếng Việt**.

## ✨ Tính năng

- 🗣️ **Text-to-SQL**: Hỏi bằng ngôn ngữ tự nhiên → sinh SQL chính xác
- 📊 **Auto Chart**: Tạo biểu đồ Vega-Lite (bar, line, pie, area...) từ kết quả
- 🔒 **SQL Guardian**: Bảo vệ injection, read-only, column masking, RLS
- 🧠 **14-Stage Pipeline**: PreFilter → Intent → Schema → CoT → Generate → Correct → Guard
- 📖 **Business Glossary**: Ánh xạ thuật ngữ nghiệp vụ
- 🔍 **Semantic Memory**: Học từ queries thành công trước đó
- 🐛 **Debug Trace**: Xem chi tiết từng stage trong pipeline
- 🎨 **Next.js UI**: Chat interface với data table + ERD modeling

## 🏗 Kiến trúc

```
┌─────────────────┐     ┌─────────────────────────────────────┐
│   Next.js UI    │────▶│  FastAPI Backend (port 8000)         │
│   (port 3000)   │     │                                     │
│  ┌────────────┐ │     │  ┌──────────┐  ┌────────────────┐  │
│  │ Chat       │ │     │  │ Ask      │  │ Chart          │  │
│  │ Modeling   │ │     │  │ Pipeline │  │ Generator      │  │
│  │ Settings   │ │     │  │ (14 stg) │  │ (Vega-Lite)    │  │
│  └────────────┘ │     │  └──────┬───┘  └────────────────┘  │
└─────────────────┘     │         │                           │
                        │  ┌──────▼───┐  ┌────────────────┐  │
                        │  │ ChromaDB │  │ SQL Server     │  │
                        │  │ (Vector) │  │ (Data Source)  │  │
                        │  └──────────┘  └────────────────┘  │
                        └─────────────────────────────────────┘
```

## 🚀 Quick Start (Docker)

### Yêu cầu
- Docker & Docker Compose
- SQL Server (host hoặc remote)
- API key (OpenAI-compatible hoặc GitHub Models)

### 1. Clone & cấu hình

```bash
git clone <repo-url> mini-wren-ai
cd mini-wren-ai
cp .env.example .env
# Sửa .env với thông tin kết nối thật
```

### 2. Chạy

```bash
docker compose up -d
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### 3. Sử dụng

1. Mở http://localhost:3000 → trang Setup hiện ra
2. Nhập thông tin SQL Server → **Connect**
3. Chuyển sang trang **Home** → bắt đầu chat
4. Hỏi: _"Top 5 sản phẩm có doanh thu cao nhất"_
5. Click **📊 Tạo biểu đồ** để xem visualization

## 💻 Manual Setup (Development)

### Backend

```bash
# Yêu cầu: Python 3.10+, ODBC Driver 17 for SQL Server
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

pip install -r requirements.txt
pip install fastapi uvicorn openai httpx

cp .env.example .env
# Sửa .env

python -m uvicorn src.server:app --reload --port 8000
```

### Frontend

```bash
cd web
npm install
npm run dev
```

Mở http://localhost:3000

## 📋 Pipeline Architecture (14 Stages)

```
question → PreFilter → InstructionMatch → IntentClassify → SubIntentDetect
  → SchemaRetrieval → SchemaLinking → ColumnPruning → ContextBuild
  → GlossaryInject → MemoryLookup → CoTReason
  → SQLGeneration → SQLCorrection → Guardian → MemorySave → Result
```

| # | Stage | LLM | Ý nghĩa |
|---|-------|-----|---------|
| 1 | PreFilter | ❌ | Lọc greeting, destructive, out-of-scope |
| 2 | InstructionMatch | ❌ | Inject business rules |
| 3 | IntentClassifier | ✅ | TEXT_TO_SQL / GENERAL / SCHEMA_EXPLORE |
| 4 | SubIntentDetect | ❌ | RETRIEVAL / AGGREGATION / RANKING... |
| 5 | SchemaRetrieval | ❌ | Vector search tìm tables liên quan |
| 6 | SchemaLinking | ✅ | Map entities → tables/columns |
| 7 | ColumnPruning | ✅ | Loại columns không liên quan |
| 8 | ContextBuilder | ❌ | Build DDL text |
| 9 | GlossaryLookup | ❌ | Tra cứu thuật ngữ nghiệp vụ |
| 10 | SemanticMemory | ❌ | Tra cứu queries tương tự |
| 11 | CoTReasoning | ✅ | Chain-of-thought plan |
| 12 | SQLGeneration | ✅ | Sinh SQL (1 candidate, voting=off) |
| 13 | SQLCorrection | ✅ | Auto-fix lỗi (max 3 retries) |
| 13.5 | Guardian | ❌ | Security validation |
| 14 | MemorySave | ❌ | Lưu trace thành công |

**LLM Budget**: 4-6 calls/query (full pipeline)

## 📊 Chart Generation

Sau khi có kết quả SQL, click **"Tạo biểu đồ"** → LLM sinh Vega-Lite schema:

| Chart Type | Khi nào |
|------------|---------|
| `bar` | So sánh categories |
| `grouped_bar` | Sub-categories |
| `stacked_bar` | Composition |
| `line` | Trend theo thời gian |
| `multi_line` | Nhiều metrics |
| `area` | Volume theo thời gian |
| `pie` | Tỷ lệ phần trăm |

## 🔌 API Reference

### Core Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/health` | Health check |
| `POST` | `/v1/connections/connect` | Kết nối SQL Server |
| `GET` | `/v1/connections/status` | Trạng thái kết nối |
| `POST` | `/v1/ask` | Hỏi câu hỏi → SQL |
| `POST` | `/v1/sql/execute` | Chạy SQL trực tiếp |
| `POST` | `/v1/charts/generate` | Sinh biểu đồ |
| `GET` | `/v1/models` | Xem models |
| `PATCH` | `/v1/models/{name}` | Cập nhật metadata |

### Knowledge Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/v1/knowledge/glossary` | Xem glossary |
| `POST` | `/v1/knowledge/glossary` | Thêm term |
| `PUT` | `/v1/knowledge/glossary/{id}` | Sửa term |
| `DELETE` | `/v1/knowledge/glossary/{id}` | Xóa term |
| `GET` | `/v1/knowledge/sql-pairs` | Xem SQL pairs |
| `POST` | `/v1/knowledge/sql-pairs` | Thêm SQL pair |

### Settings

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/v1/settings` | Xem settings |
| `PUT` | `/v1/settings` | Cập nhật settings |
| `POST` | `/v1/deploy` | Re-deploy |

### Ví dụ `/v1/ask`

```bash
curl -X POST http://localhost:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Top 5 sản phẩm có doanh thu cao nhất", "debug": true}'
```

Response:
```json
{
  "question": "Top 5 sản phẩm có doanh thu cao nhất",
  "intent": "TEXT_TO_SQL",
  "sql": "SELECT TOP 5 ...",
  "explanation": "Truy vấn lấy 5 sản phẩm...",
  "columns": ["ProductName", "Revenue"],
  "rows": [...],
  "valid": true,
  "pipeline_info": { ... },
  "debug_trace": { ... }
}
```

## ⚙️ Environment Variables

| Variable | Required | Default | Mô tả |
|----------|----------|---------|-------|
| `SQL_SERVER_HOST` | ✅ | `localhost` | SQL Server host |
| `SQL_SERVER_PORT` | ❌ | `1433` | SQL Server port |
| `SQL_SERVER_DB` | ✅ | - | Database name |
| `SQL_SERVER_USER` | ✅ | `sa` | Username |
| `SQL_SERVER_PASS` | ✅ | - | Password |
| `OPENAI_API_KEY` | ✅ | - | LLM API key |
| `OPENAI_BASE_URL` | ❌ | `https://api.openai.com/v1` | LLM endpoint |
| `HUGGINGFACE_API_KEY` | ✅ | - | Embedding model key |
| `CHROMA_PERSIST_DIR` | ❌ | `./chroma_data` | ChromaDB storage |
| `GLOSSARY_PATH` | ❌ | `./glossary.yaml` | Business glossary |
| `MEMORY_PATH` | ❌ | `./semantic_memory.json` | Query memory |

## 🐳 Docker Commands

```bash
# Build & chạy
docker compose up -d

# Xem logs
docker compose logs -f backend
docker compose logs -f frontend

# Rebuild sau khi sửa code
docker compose up -d --build

# Dừng
docker compose down

# Xóa toàn bộ data (ChromaDB)
docker compose down -v
```

## 📁 Project Structure

```
mini-wren-ai/
├── src/
│   ├── server.py              # FastAPI entry point
│   ├── config.py              # Environment settings
│   ├── connectors/            # SQL Server connector
│   ├── generation/            # LLM-powered stages
│   │   ├── intent_classifier.py
│   │   ├── sub_intent.py
│   │   ├── sql_reasoner.py
│   │   ├── candidate_generator.py
│   │   ├── execution_voter.py
│   │   ├── sql_corrector.py
│   │   ├── pre_filter.py
│   │   ├── instruction_matcher.py
│   │   ├── semantic_memory.py
│   │   ├── chart_generator.py # Vega-Lite chart gen
│   │   └── llm_client.py
│   ├── retrieval/             # Schema retrieval & linking
│   │   ├── schema_retriever.py
│   │   ├── schema_linker.py
│   │   ├── column_pruner.py
│   │   ├── context_builder.py
│   │   └── business_glossary.py
│   ├── security/
│   │   └── guardian.py        # SQL security guards
│   └── pipelines/
│       ├── ask_pipeline.py    # Main 14-stage pipeline
│       └── deploy_pipeline.py # Model indexing
├── web/                       # Next.js frontend
│   ├── src/pages/             # Home, Modeling, Settings
│   ├── src/components/        # VegaChart, DebugTrace, ERD
│   └── src/contexts/          # ConnectionContext, ChatContext
├── Dockerfile                 # Backend Docker
├── web/Dockerfile             # Frontend Docker
├── docker-compose.yml         # Orchestration
├── .env.example               # Environment template
├── glossary.yaml              # Business glossary
├── models.yaml                # Model definitions
└── requirements.txt           # Python deps
```

## 📝 License

Private project — KhoAI Team.
