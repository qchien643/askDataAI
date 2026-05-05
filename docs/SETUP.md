# Hướng dẫn khởi động dự án

Tài liệu chi tiết cách chạy **mini-wren-ai** ở cả 3 chế độ:

1. [Manual setup (development)](#1-manual-setup-development) — chạy backend + frontend riêng, hot reload
2. [PowerShell scripts](#2-powershell-scripts) — script tự động hoá cho Windows
3. [Docker (production-like)](#3-docker-production-like) — full stack qua docker compose

---

## Yêu cầu chung

| Phần | Phiên bản | Ghi chú |
|---|---|---|
| Python | 3.10+ | 3.11 khuyên dùng |
| Node.js | 18+ | 20 khuyên dùng |
| ODBC Driver for SQL Server | 17 hoặc 18 | Cài qua Microsoft installer |
| SQL Server | 2017+ | Local hoặc remote |
| OpenAI API key | — | Hoặc endpoint OpenAI-compatible (vd: GitHub Models) |
| Docker Desktop | — | Chỉ cần cho phương án 3 |

### Cài ODBC Driver 17 (Windows)

```powershell
# Tải installer:
# https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server

# Hoặc qua winget:
winget install Microsoft.MSODBCSQL.17
```

Kiểm tra: `Control Panel → ODBC Data Sources → Drivers` → phải thấy "ODBC Driver 17 for SQL Server".

### Bật SQL Server Authentication + TCP/IP

1. **SQL Server Management Studio** → Server Properties → Security → `SQL Server and Windows Authentication mode`.
2. **SQL Server Configuration Manager** → SQL Server Network Configuration → TCP/IP → **Enable** → restart service.
3. Mở firewall port **1433**.

---

## 1. Manual setup (development)

Phù hợp khi dev — code thay đổi → reload tự động, debug dễ.

### 1.1 Cấu hình `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Điền đầy đủ:

```env
SQL_SERVER_HOST=localhost
SQL_SERVER_PORT=1433
SQL_SERVER_DB=AdventureWorksDW2025
SQL_SERVER_USER=sa
SQL_SERVER_PASS=YourStrong!Password

OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://models.github.ai/inference

CHROMA_PERSIST_DIR=./data/chroma_data
GLOSSARY_PATH=./configs/glossary.yaml
MEMORY_PATH=./data/semantic_memory.json
```

### 1.2 Backend

```powershell
# Tạo venv
python -m venv venv
.\venv\Scripts\Activate.ps1

# Cài deps
pip install -r requirements.txt

# Chạy server (auto-reload)
python -m uvicorn askdataai.server:app --reload --host 0.0.0.0 --port 8000
```

Xác nhận: mở http://localhost:8000/health → `{"status":"ok"}`.
API docs: http://localhost:8000/docs (Swagger UI).

### 1.3 Frontend

Mở terminal **mới** (giữ backend chạy):

```powershell
cd web

# Cấu hình endpoint backend (chỉ lần đầu)
"NEXT_PUBLIC_API_BASE=http://localhost:8000" | Out-File -Encoding utf8 .env.local

# Cài deps
npm install --legacy-peer-deps

# Chạy dev server (hot reload)
npm run dev
```

Mở http://localhost:3000.

### 1.4 Sử dụng lần đầu

1. Trang Setup hiện ra → nhập SQL Server credentials → **Connect**.
2. Vào trang **Modeling** → kiểm tra danh sách bảng → optional: bấm **Auto Describe** để LLM tự sinh mô tả tiếng Việt.
3. Chuyển trang **Home** → bắt đầu chat.
4. Hỏi thử: _"Top 5 sản phẩm có doanh thu cao nhất"_.

### 1.5 Khắc phục sự cố

| Lỗi | Khắc phục |
|---|---|
| `pyodbc.Error: ODBC Driver not found` | Cài ODBC Driver 17 (mục **Yêu cầu chung** trên). |
| `Login failed for user 'sa'` | Bật SQL Server Authentication mode. |
| `Connection refused` | Bật TCP/IP + firewall port 1433. |
| `ModuleNotFoundError` | venv chưa active hoặc deps chưa cài: `pip install -r requirements.txt`. |
| Frontend `Failed to fetch` | Kiểm tra `web/.env.local` có `NEXT_PUBLIC_API_BASE=http://localhost:8000`. |
| ChromaDB lỗi | Xoá thư mục cũ rồi deploy lại: `Remove-Item -Recurse data/chroma_data`. |

---

## 2. PowerShell scripts

Script tự động hoá ở thư mục `scripts/`. Lần đầu chạy:

```powershell
# Cho phép chạy script trong session hiện tại (không cần admin)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### `scripts/setup.ps1` — Cài đặt lần đầu

Tạo venv, cài deps Python + Node, copy `.env.example` → `.env`, tạo `web/.env.local`.

```powershell
.\scripts\setup.ps1
```

### `scripts/start-backend.ps1` — Chạy backend

Activate venv (tự tạo nếu chưa có), khởi động uvicorn ở port 8000 với auto-reload.

```powershell
.\scripts\start-backend.ps1
# Tuỳ chọn:
.\scripts\start-backend.ps1 -Port 8001
.\scripts\start-backend.ps1 -NoReload
```

### `scripts/start-frontend.ps1` — Chạy frontend

`cd web`, ensure deps, `npm run dev` ở port 3000.

```powershell
.\scripts\start-frontend.ps1
.\scripts\start-frontend.ps1 -Port 3002
```

### `scripts/start-all.ps1` — Chạy cả hai

Mở 2 cửa sổ PowerShell mới: backend ở port 8000, frontend ở 3000.

```powershell
.\scripts\start-all.ps1
```

### `scripts/stop-all.ps1` — Dừng

Tìm process uvicorn + node trên port 8000/3000 và kill.

```powershell
.\scripts\stop-all.ps1
```

### `scripts/clean.ps1` — Reset state

Xoá `data/chroma_data`, `data/semantic_memory.json`, `data/manifests/*` (giữ lại folder structure). KHÔNG xoá venv hay node_modules.

```powershell
.\scripts\clean.ps1
```

---

## 3. Docker (production-like)

Phù hợp khi deploy hoặc demo nhanh — tự build cả backend + frontend, mount config/data.

### 3.1 Yêu cầu

- Docker Desktop (Windows/macOS) hoặc Docker Engine (Linux)
- File `.env` đã cấu hình (mục **1.1** trên)

### 3.2 Chạy

```powershell
# Build + start cả 2 services (background)
docker compose up -d --build

# Xem logs realtime
docker compose logs -f backend
docker compose logs -f frontend
```

Truy cập:
- Frontend: http://localhost:**3001** (Docker map 3000 → 3001 để tránh xung đột với dev mode)
- Backend: http://localhost:8000
- API docs: http://localhost:8000/docs

### 3.3 Volume mounts

`docker-compose.yml` mount để config/data persist giữa các lần restart:

| Host | Container | Mục đích |
|---|---|---|
| `./configs/models.yaml` | `/app/configs/models.yaml` | Semantic models |
| `./configs/glossary.yaml` | `/app/configs/glossary.yaml` | Business glossary |
| `./data/semantic_memory.json` | `/app/data/semantic_memory.json` | Query memory |
| `./data/manifests` | `/app/data/manifests` | Manifest snapshots |
| `chroma_data` (named volume) | `/app/data/chroma_data` | Vector DB |

### 3.4 Reach SQL Server từ container

`docker-compose.yml` đã cấu hình:

```yaml
SQL_SERVER_HOST: host.docker.internal
extra_hosts:
  - "host.docker.internal:host-gateway"
```

→ container truy cập SQL Server đang chạy trên host máy được. Nếu SQL Server chạy trong Docker network khác, đổi `SQL_SERVER_HOST` thành tên service đó.

### 3.5 Lệnh thường dùng

```powershell
# Xem trạng thái
docker compose ps

# Restart 1 service
docker compose restart backend

# Rebuild sau khi sửa code (chỉ image bị thay đổi)
docker compose up -d --build backend

# Dừng (giữ data)
docker compose down

# Dừng + xoá volumes (mất ChromaDB!)
docker compose down -v

# Vào shell container backend
docker compose exec backend bash

# Xoá orphan containers
docker compose down --remove-orphans
```

### 3.6 Hot-reload trong Docker (advanced)

Mặc định Dockerfile chạy uvicorn không có `--reload`. Để dev với hot-reload trong Docker:

1. Mount source code: thêm `- ./askdataai:/app/askdataai` vào `docker-compose.yml` (backend service).
2. Override CMD: thêm `command: python -m uvicorn askdataai.server:app --reload --host 0.0.0.0 --port 8000`.

Hoặc dùng cách 2 ở trên (manual setup) cho dev — đơn giản hơn.

---

## So sánh nhanh 3 cách

| | Manual | PS1 scripts | Docker |
|---|:---:|:---:|:---:|
| Setup time | ~5 phút | 1 lệnh | ~5 phút (lần đầu build) |
| Hot reload | ✅ | ✅ | ⚠️ cần config thêm |
| Dependencies isolation | venv | venv | container |
| Multi-machine consistent | ❌ | ❌ | ✅ |
| Phù hợp cho | Dev hằng ngày | Dev nhanh | Demo, CI, deploy |

Khuyến nghị:
- **Dev**: Manual hoặc PS1 scripts
- **Demo/share**: Docker
- **CI/CD**: Docker
