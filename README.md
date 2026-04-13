# askDataAI — Text-to-SQL Platform

> Hỏi dữ liệu bằng tiếng Việt, nhận câu SQL chính xác và biểu đồ trực quan.

**askDataAI** là nền tảng Text-to-SQL thông minh được xây dựng trên pipeline 14 bước, hỗ trợ SQL Server, tích hợp OpenAI-compatible LLM và giao diện Memphis Design hiện đại với real-time reasoning trace.

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
 (LLM)    (Vector Store)  (Data)
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

## 🚀 Cài đặt & Chạy

### Yêu cầu hệ thống

- **Python** 3.11+
- **Node.js** 20+
- **SQL Server** (2019 hoặc mới hơn, có thể là SQL Server Express)
- **ODBC Driver 17 for SQL Server**
- **OpenAI API key** hoặc compatible provider (GitHub Models, Groq, v.v.)

---

### Phương án 1: Chạy thủ công (Source Mode) — Khuyến nghị cho development

#### 1. Clone repository

```bash
git clone https://github.com/qchien643/askDataAI.git
cd askDataAI
```

#### 2. Tạo và kích hoạt Python virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

#### 3. Cài đặt Python dependencies

```bash
pip install -r requirements.txt
```

#### 4. Cấu hình environment variables

```bash
cp .env.example .env
```

Mở `.env` và điền thông tin:

```env
# SQL Server
SQL_SERVER_HOST=localhost       # hoặc IP của SQL Server
SQL_SERVER_PORT=1433
SQL_SERVER_DB=YourDatabase
SQL_SERVER_USER=sa
SQL_SERVER_PASS=your_password

# LLM (chọn 1 trong 3 options bên dưới)
OPENAI_API_KEY=your_key_here
OPENAI_BASE_URL=https://models.github.ai/inference
OPENAI_MODEL=gpt-4.1-mini
```

#### 5. Cài đặt ODBC Driver 17 (nếu chưa có)

**Windows:** Tải từ [Microsoft ODBC Driver](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)

**Ubuntu/Debian:**
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list \
  | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17
```

**macOS (Homebrew):**
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew install msodbcsql17
```

#### 6. Khởi động Backend

```bash
python -m uvicorn src.server:app --reload --port 8000
```

API sẽ chạy tại: `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`

#### 7. Khởi động Frontend

```bash
cd web
npm install
npm run dev
```

Mở trình duyệt: `http://localhost:3000`

---

### Phương án 2: Docker Compose — Khuyến nghị cho production

#### Yêu cầu

- Docker Desktop (Windows/macOS) hoặc Docker Engine (Linux)
- SQL Server đang chạy trên **máy host** (không phải trong Docker)

#### 1. Clone và cấu hình

```bash
git clone https://github.com/qchien643/askDataAI.git
cd askDataAI
cp .env.example .env
```

Mở `.env` và điền thông tin. Lưu ý:
- Với Docker, `SQL_SERVER_HOST` sẽ được tự động override thành `host.docker.internal`
- Đây là địa chỉ đặc biệt để container kết nối về máy host

#### 2. Build và khởi động

```bash
docker compose up --build
```

- **Backend API:** `http://localhost:8000`
- **Frontend:** `http://localhost:3000`

#### 3. Chạy ngầm (detached mode)

```bash
docker compose up --build -d
docker compose logs -f        # theo dõi logs
docker compose down           # dừng tất cả
```

#### 4. Ghi chú quan trọng với Docker

**SQL Server trên Windows host:**
```env
SQL_SERVER_HOST=host.docker.internal
```

**SQL Server trên Linux host** (cần thêm vào docker-compose nếu chưa có):
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```
*(Đã được thêm sẵn trong `docker-compose.yml`)*

**Nếu SQL Server yêu cầu Windows Auth:** Dùng SQL Auth (username/password) thay thế.

---

## 🔑 Cấu hình LLM Providers

### OpenAI (Trả phí)
```env
OPENAI_API_KEY=sk-proj-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

### GitHub Models (Miễn phí với GitHub account)
```env
OPENAI_API_KEY=ghp_your_github_personal_access_token
OPENAI_BASE_URL=https://models.github.ai/inference
OPENAI_MODEL=gpt-4.1-mini
```
> Tạo PAT tại: Settings → Developer settings → Personal access tokens

### Groq (Nhanh, miễn phí tier)
```env
OPENAI_API_KEY=gsk_...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```

---

## 📁 Cấu trúc thư mục

```
askDataAI/
├── src/
│   ├── server.py                   # FastAPI app, SSE endpoints
│   ├── config.py                   # Settings từ .env
│   ├── pipelines/
│   │   └── ask_pipeline.py         # Pipeline 14 bước chính
│   ├── generation/
│   │   ├── llm_client.py           # OpenAI-compatible client
│   │   ├── sql_generator.py        # Sinh SQL
│   │   ├── sql_corrector.py        # Sửa SQL lỗi
│   │   ├── intent_classifier.py    # Phân loại ý định
│   │   ├── schema_linker.py        # Liên kết schema
│   │   └── conversation_context.py # Multi-turn context
│   ├── retrieval/
│   │   ├── schema_retriever.py     # Tìm bảng liên quan
│   │   └── memory_retriever.py     # Tìm SQL tương tự
│   └── security/
│       └── pi_guardrail.py         # Prompt injection guard
├── web/                            # Next.js frontend
│   ├── src/pages/home.tsx          # Trang chính + pipeline UI
│   ├── src/styles/globals.css      # Memphis design system
│   └── Dockerfile
├── Dockerfile                      # Backend Docker image
├── docker-compose.yml              # Multi-service orchestration
├── .env.example                    # Template biến môi trường
├── glossary.yaml                   # Từ điển thuật ngữ nghiệp vụ
├── models.yaml                     # Schema models
└── requirements.txt                # Python dependencies
```

---

## 🛠️ Phát triển & Mở rộng

### Thêm thuật ngữ nghiệp vụ

Chỉnh sửa `glossary.yaml`:
```yaml
terms:
  - name: "Doanh thu"
    description: "Tổng giá trị bán hàng, bao gồm cả Internet và Reseller"
    aliases: ["revenue", "oanh thu"]
  - name: "Khách hàng VIP"
    description: "Khách hàng có tổng mua hàng > 10,000 USD"
```

### Thêm SQL memory

Sau khi chạy query thành công, hệ thống tự động lưu vào `semantic_memory.json`.  
Hoặc thêm thủ công qua trang **Knowledge** trong UI.

### Chỉnh sửa pipeline settings

Bật/tắt từng tính năng qua trang **Settings** hoặc qua API:
- Schema linking
- Column pruning  
- CoT reasoning
- Glossary matching

---

## 📡 API Reference

### POST `/v1/ask/stream`
Stream pipeline execution qua Server-Sent Events.

**Request:**
```json
{
  "question": "Doanh thu từng tháng năm 2013 là bao nhiêu?",
  "session_id": "uuid-string",
  "debug": false
}
```

**SSE Events:**
```
event: progress
data: {"stage": "5", "label": "Tìm kiếm bảng dữ liệu...", "detail": ""}

event: result
data: {"sql": "SELECT ...", "rows": [...], "columns": [...]}

event: error
data: {"message": "..."}
```

### POST `/v1/connections/connect`
Kết nối database và deploy schema index.

### GET `/health`
Kiểm tra trạng thái backend.

Xem đầy đủ tại Swagger UI: `http://localhost:8000/docs`

---

## ❓ Troubleshooting

### Lỗi: `[Microsoft][ODBC Driver 17]` hoặc `ODBC Driver not found`
→ Cài ODBC Driver 17 theo hướng dẫn ở trên.

### Lỗi: `Connection refused` tới SQL Server trong Docker
→ Đảm bảo SQL Server cho phép TCP/IP connections.  
→ Kiểm tra `SQL_SERVER_HOST=host.docker.internal` trong `.env`.  
→ Trên Linux, kiểm tra firewall: `sudo ufw allow 1433`.

### Lỗi: `ChromaDB import error`
→ Chạy lại: `pip install chromadb==0.4.24`

### Frontend không kết nối được API
→ Kiểm tra `NEXT_PUBLIC_API_BASE` trong `web/.env.local`:
```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

### Lỗi build Docker frontend
→ Xóa cache: `docker compose build --no-cache frontend`

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

*Built with ❤️ using FastAPI, Next.js, OpenAI, ChromaDB, and Memphis Design.*
