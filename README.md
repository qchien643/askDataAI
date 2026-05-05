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

> Chi tiết đầy đủ + troubleshooting: **[docs/SETUP.md](docs/SETUP.md)**.
> PowerShell scripts: **[scripts/README.md](scripts/README.md)**.

### Cách nhanh (Windows + PowerShell)

```powershell
.\scripts\setup.ps1          # cài venv + npm install + tạo .env
# Sửa .env với SQL Server + OpenAI key
.\scripts\start-all.ps1      # mở 2 cửa sổ: backend 8000 + frontend 3000
```

### Backend (manual)

```bash
# Yêu cầu: Python 3.10+, ODBC Driver 17 for SQL Server
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

pip install -r requirements.txt

cp .env.example .env
# Sửa .env

python -m uvicorn askdataai.server:app --reload --port 8000
```

### Frontend (manual)

```bash
cd web
echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
npm install --legacy-peer-deps
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
| `CHROMA_PERSIST_DIR` | ❌ | `./data/chroma_data` | ChromaDB storage |
| `GLOSSARY_PATH` | ❌ | `./configs/glossary.yaml` | Business glossary |
| `MEMORY_PATH` | ❌ | `./data/semantic_memory.json` | Query memory |

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
├── CLAUDE.md                  # Agent navigation guide
├── askdataai/                 # Python package (backend)
│   ├── server.py              # FastAPI entry — askdataai.server:app
│   ├── config.py              # Pydantic settings
│   ├── connectors/            # SQL Server connector + introspection
│   ├── indexing/              # OpenAI embedder + ChromaDB store
│   ├── modeling/              # Manifest builder, deployer
│   ├── retrieval/             # Schema retrieve/link/prune + glossary
│   ├── generation/            # 14-stage LLM stages
│   │   └── auto_describe/     # Auto schema description sub-feature
│   ├── pipelines/             # ask_pipeline.py (god module), deploy_pipeline.py
│   └── security/              # PIGuardrail + SQL Guardian (5-layer)
├── web/                       # Next.js frontend
├── configs/                   # User-edited YAML (TRACKED)
│   ├── models.yaml            # Semantic model definitions
│   └── glossary.yaml          # Business glossary
├── data/                      # Runtime-generated (GITIGNORED)
│   ├── chroma_data/           # Vector DB
│   ├── manifests/             # Manifest snapshots
│   └── semantic_memory.json   # Query memory
├── docs/
│   ├── SETUP.md               # Detailed setup guide
│   ├── PROJECT_OVERVIEW.md
│   ├── PROPOSAL.md
│   └── pipeline/              # Per-stage deep dives (00..16)
├── scripts/                   # PowerShell automation
│   ├── setup.ps1
│   ├── start-backend.ps1
│   ├── start-frontend.ps1
│   ├── start-all.ps1
│   ├── stop-all.ps1
│   ├── clean.ps1
│   └── docker-up.ps1
├── tests/                     # pytest suite
├── Dockerfile                 # Backend image
├── docker-compose.yml         # Orchestration
├── pytest.ini
├── .env.example
└── requirements.txt
```


- CoT Reasoning
- Glossary Matching

---

## 📡 API Reference (tóm tắt)

| Endpoint | Method | Mô tả |
|---|---|---|
| `/health` | GET | Kiểm tra trạng thái |
| `/v1/connections/connect` | POST | Kết nối database |
| `/v1/connections/status` | GET | Trạng thái kết nối |
| `/v1/ask/stream` | POST | Query với SSE stream |
| `/v1/sql/execute` | POST | Chạy SQL trực tiếp |
| `/v1/knowledge/glossary` | GET/POST | Quản lý glossary |

Xem đầy đủ tại: **http://localhost:8000/docs**

---

## ❓ Troubleshooting

### `pyodbc.Error: ODBC Driver not found`
→ Cài ODBC Driver 17 theo hướng dẫn Bước 2 phía trên.  
→ Windows: Kiểm tra trong **Control Panel → ODBC Data Sources → Drivers**.

### `Login failed for user 'sa'`
→ Kiểm tra SQL Server đã bật **SQL Server Authentication** (không chỉ Windows Auth).  
→ Vào SQL Server Management Studio → Server Properties → Security → **SQL Server and Windows Authentication mode**.

### `Connection refused` khi kết nối SQL Server
→ Kiểm tra SQL Server đã bật **TCP/IP protocol**:  
SQL Server Configuration Manager → SQL Server Network Configuration → TCP/IP → Enable.  
→ Kiểm tra firewall cho phép port **1433**.

### Frontend báo `Failed to fetch` hoặc không kết nối API
→ Kiểm tra backend đang chạy tại `http://localhost:8000`.  
→ Kiểm tra file `web/.env.local` có:
```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```
Nếu không có file này, tạo mới.

### `ModuleNotFoundError` khi chạy backend
→ Kiểm tra venv đang active (có `(venv)` ở đầu terminal).  
→ Chạy lại: `pip install -r requirements.txt`.

### ChromaDB lỗi khi deploy
→ Xóa thư mục cũ và deploy lại:
```bash
rm -rf data/chroma_data/
# hoặc Windows:
.\scripts\clean.ps1
```

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

*Built with FastAPI · Next.js · OpenAI · ChromaDB · Memphis Design*
