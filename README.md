# askDataAI — Text-to-SQL Platform

> Hỏi dữ liệu bằng tiếng Việt, nhận câu SQL chính xác và biểu đồ trực quan.

**askDataAI** là nền tảng Text-to-SQL thông minh được xây dựng trên pipeline 14 bước, hỗ trợ SQL Server, tích hợp OpenAI LLM và giao diện Memphis Design hiện đại với real-time reasoning trace.

---

## ✨ Tính năng nổi bật

| Tính năng | Mô tả |
|---|---|
| 🧠 **14-stage pipeline** | Phân tích ý định → Schema linking → CoT reasoning → SQL generation |
| 💬 **Multi-turn context** | Rolling summary + 7 lượt gần nhất để giữ ngữ cảnh hội thoại |
| 📡 **Real-time pipeline trace** | SSE stream từng bước xử lý hiện ra trực tiếp trên UI |
| 🗂️ **Thought Drawer** | Xem lại toàn bộ reasoning trace sau khi có kết quả |
| 📊 **Auto visualization** | Tự động sinh biểu đồ Vega-Lite cho câu hỏi phân tích |
| 🛡️ **PI Guardrail** | Bảo vệ chống prompt injection và câu hỏi không liên quan |
| 📖 **Glossary & Memory** | Từ điển thuật ngữ nghiệp vụ + SQL memory theo ngữ nghĩa |
| 🎨 **Memphis Design** | Giao diện geometric bold, custom SVG icons, cursor effects |

---

## 🏗️ Kiến trúc

```
┌─────────────────────────────────────┐
│          Frontend (Next.js)          │
│  Memphis UI · SSE Client · Drawer   │
└────────────────┬────────────────────┘
                 │ HTTP / SSE
┌────────────────▼────────────────────┐
│          Backend (FastAPI)           │
│  /v1/ask/stream · /v1/sql/execute   │
└────────────────┬────────────────────┘
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
  OpenAI      ChromaDB     SQL Server
  (LLM)    (Vector Store)   (Data)
```

### Pipeline 14 bước

| Stage | Tên | Loại |
|---|---|---|
| 0 | PI Guardrail | Rule-based |
| 0.5 | Conversation Context | LLM |
| 1 | Pre-filter | Rule-based |
| 2 | Instruction Matcher | Rule-based |
| 3 | Intent Classifier | LLM |
| 4 | Sub-intent Detector | LLM |
| 5 | Schema Retrieval | Embedding |
| 6 | Schema Linking | LLM |
| 7 | Column Pruning | LLM |
| 8 | DDL Context Builder | Template |
| 9 | Glossary Lookup | Vector Search |
| 10 | Memory Search | Vector Search |
| 11 | CoT Reasoner | LLM |
| 12 | SQL Generator | LLM |
| 13 | SQL Executor & Corrector | Rule + LLM |

---

## 📋 Yêu cầu hệ thống

| Thành phần | Phiên bản tối thiểu |
|---|---|
| Python | 3.11+ |
| Node.js | 20+ |
| SQL Server | 2019+ (bao gồm Express) |
| ODBC Driver | 17 for SQL Server |
| OpenAI API Key | Tài khoản OpenAI |

---

## 🚀 Cài đặt thủ công (không dùng Docker)

### Bước 1 — Clone repository

```bash
git clone https://github.com/qchien643/askDataAI.git
cd askDataAI
```

---

### Bước 2 — Cài đặt ODBC Driver 17 for SQL Server

**Windows:**

Tải và cài đặt từ Microsoft:
> https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

Chọn **ODBC Driver 17 for SQL Server** → **Windows x64**.

Sau khi cài xong, kiểm tra trong **Control Panel → ODBC Data Sources**.

**Ubuntu / Debian (Linux):**

```bash
sudo apt-get update
sudo apt-get install -y curl gnupg2

curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -

curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list \
  | sudo tee /etc/apt/sources.list.d/mssql-release.list

sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev
```

**macOS (Homebrew):**

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew update
ACCEPT_EULA=Y brew install msodbcsql17
```

---

### Bước 3 — Tạo Python virtual environment

```bash
# Windows (PowerShell)
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

> ⚠️ Luôn activate venv trước khi chạy bất kỳ lệnh nào. Dấu `(venv)` phải xuất hiện ở đầu terminal.

---

### Bước 4 — Cài đặt Python dependencies

```bash
pip install -r requirements.txt
```

Kiểm tra cài đặt thành công:

```bash
python -c "import fastapi, openai, chromadb, pyodbc; print('OK')"
```

---

### Bước 5 — Cấu hình environment variables

Tạo file `.env` từ template:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Mở `.env` và điền đầy đủ thông tin:

```env
# ── SQL Server ──────────────────────────────────────────
SQL_SERVER_HOST=localhost         # IP hoặc hostname của SQL Server
SQL_SERVER_PORT=1433              # Port mặc định
SQL_SERVER_DB=AdventureWorksDW2025  # Tên database của bạn
SQL_SERVER_USER=sa                # SQL Server username
SQL_SERVER_PASS=your_password     # SQL Server password

# ── OpenAI ──────────────────────────────────────────────
OPENAI_API_KEY=sk-proj-...        # API key từ platform.openai.com
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini          # Hoặc gpt-4o, gpt-3.5-turbo

# ── ChromaDB ────────────────────────────────────────────
CHROMA_PERSIST_DIR=./chroma_data

# ── Knowledge files ─────────────────────────────────────
GLOSSARY_PATH=./glossary.yaml
MEMORY_PATH=./semantic_memory.json
```

> 🔑 **Lấy OpenAI API Key:** Đăng nhập tại [platform.openai.com](https://platform.openai.com) → API Keys → Create new secret key.

---

### Bước 6 — Khởi động Backend

```bash
# Đảm bảo venv đang active, sau đó chạy từ thư mục gốc project
python -m uvicorn src.server:app --reload --port 8000
```

Kết quả thành công:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Kiểm tra tại:
- **API:** http://localhost:8000/health
- **Swagger UI:** http://localhost:8000/docs

---

### Bước 7 — Cài đặt và khởi động Frontend

Mở **terminal mới** (giữ terminal backend chạy ngầm):

```bash
cd web
npm install
npm run dev
```

Kết quả thành công:

```
▲ Next.js 14.x.x
- Local:        http://localhost:3000
- Ready in 2.3s
```

Mở trình duyệt: **http://localhost:3000**

---

### Bước 8 — Kết nối database lần đầu

1. Vào trang **Setup** (tự động redirect khi lần đầu truy cập)
2. Điền thông tin SQL Server connection
3. Nhấn **"Test Connection"** để kiểm tra kết nối
4. Nhấn **"Connect & Deploy"** — hệ thống sẽ:
   - Đọc schema từ database
   - Build vector index cho ChromaDB
   - Sẵn sàng nhận câu hỏi

> ⏳ Lần deploy đầu tiên mất 1-3 phút tùy kích thước database.

---

### Khởi động lại sau lần đầu

Từ lần thứ hai, chỉ cần chạy:

```bash
# Terminal 1 — Backend
cd askDataAI
venv\Scripts\activate        # Windows
# hoặc: source venv/bin/activate   # Linux/macOS
python -m uvicorn src.server:app --reload --port 8000

# Terminal 2 — Frontend
cd askDataAI/web
npm run dev
```

Vào app → nhấn **"Connect"** để kết nối lại database (không cần deploy lại từ đầu).

---

## 🐳 Cài đặt bằng Docker Compose

> Phù hợp cho production hoặc khi không muốn cài Python/Node thủ công.

### Yêu cầu

- Docker Desktop (Windows/macOS) hoặc Docker Engine (Linux)
- SQL Server đang chạy trên **máy host**

### Các bước

```bash
# 1. Clone và cấu hình
git clone https://github.com/qchien643/askDataAI.git
cd askDataAI
cp .env.example .env     # Điền thông tin vào .env

# 2. Build và khởi động
docker compose up --build

# App chạy tại:
# - Frontend: http://localhost:3000
# - Backend:  http://localhost:8000
```

**Chạy ngầm (detached):**

```bash
docker compose up --build -d

# Xem logs
docker compose logs -f

# Dừng
docker compose down
```

**Lưu ý SQL Server với Docker:**

Khi chạy trong Docker, backend không thể dùng `localhost` để reach SQL Server trên máy host.  
Docker Compose đã cấu hình sẵn `host.docker.internal` — bạn chỉ cần đặt trong `.env`:

```env
SQL_SERVER_HOST=host.docker.internal
```

---

## 📁 Cấu trúc thư mục

```
askDataAI/
├── src/
│   ├── server.py                    # FastAPI app, SSE endpoints
│   ├── config.py                    # Settings từ .env
│   ├── pipelines/
│   │   └── ask_pipeline.py          # Pipeline 14 bước chính
│   ├── generation/
│   │   ├── llm_client.py            # OpenAI client wrapper
│   │   ├── sql_generator.py         # Sinh SQL
│   │   ├── sql_corrector.py         # Sửa SQL lỗi
│   │   ├── intent_classifier.py     # Phân loại ý định
│   │   ├── schema_linker.py         # Liên kết schema
│   │   └── conversation_context.py  # Multi-turn context
│   ├── retrieval/
│   │   ├── schema_retriever.py      # Tìm bảng liên quan
│   │   └── memory_retriever.py      # Tìm SQL tương tự
│   └── security/
│       └── pi_guardrail.py          # Prompt injection guard
├── web/                             # Next.js frontend
│   ├── src/pages/home.tsx           # Trang chính + pipeline UI
│   ├── src/styles/globals.css       # Memphis design system
│   └── Dockerfile
├── Dockerfile                       # Backend Docker image
├── docker-compose.yml               # Multi-service orchestration
├── .env.example                     # Template biến môi trường
├── glossary.yaml                    # Từ điển thuật ngữ nghiệp vụ
├── models.yaml                      # Schema models
└── requirements.txt                 # Python dependencies
```

---

## 🛠️ Tuỳ chỉnh

### Thêm thuật ngữ nghiệp vụ

Chỉnh sửa `glossary.yaml`:

```yaml
terms:
  - name: "Doanh thu"
    description: "Tổng giá trị bán hàng Internet và Reseller"
    aliases: ["revenue", "oanh thu", "doanh so"]
  - name: "Khách hàng VIP"
    description: "Khách hàng có tổng mua hàng > 10.000 USD"
```

Sau khi sửa, **re-deploy** trong UI (Settings → Re-deploy) để áp dụng.

### Chỉnh pipeline settings

Vào trang **Settings** trong UI để bật/tắt:
- Schema Linking
- Column Pruning
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
rm -rf chroma_data/
```

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

*Built with FastAPI · Next.js · OpenAI · ChromaDB · Memphis Design*
