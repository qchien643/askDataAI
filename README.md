# Mini Wren AI

Phiên bản đơn giản của [WrenAI](https://github.com/Canner/WrenAI) — Text-to-SQL với SQL Server.

Hỏi câu hỏi bằng tiếng Việt → sinh SQL → trả kết quả từ database.

## Kiến trúc

```
User Question
    │
    ├─ Intent Classifier (TEXT_TO_SQL / GENERAL / AMBIGUOUS)
    │
    ├─ Schema Retriever (ChromaDB vector search + relationship expansion)
    │
    ├─ Context Builder (DDL với model names)
    │
    ├─ SQL Generator (LLM: T-SQL system prompt)
    │
    ├─ SQL Rewriter (model names → DB table names)
    │
    └─ SQL Corrector (execute + retry 3x if error)
```

## Cài đặt

```bash
# Clone repo
git clone <repo-url>
cd mini-wren-ai

# Tạo virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows

# Cài dependencies
pip install -r requirements.txt

# Tạo file .env
cp .env.example .env
# Sửa .env với key thật
```

## Cấu hình (.env)

```env
# SQL Server
SQL_SERVER_HOST=localhost
SQL_SERVER_PORT=1433
SQL_SERVER_DB=AdventureWorksDW2025
SQL_SERVER_USER=sa
SQL_SERVER_PASS=your_password

# LLM (OpenAI-compatible)
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://models.github.ai/inference

# HuggingFace Embeddings
HUGGINGFACE_API_KEY=your_key
```

## Chạy server

```bash
.\venv\Scripts\activate
python -m uvicorn src.server:app --reload --port 8000
```

Server tự động deploy khi khởi động. Swagger UI: http://localhost:8000/docs

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
  -d '{"question": "Top 5 san pham ban chay nhat"}'
```

```json
{
  "intent": "TEXT_TO_SQL",
  "sql": "SELECT TOP 5 ... FROM [dbo].[FactInternetSales] ...",
  "valid": true,
  "columns": ["ProductKey", "EnglishProductName", "TotalQuantitySold"],
  "rows": [{"ProductKey": 477, "EnglishProductName": "Water Bottle", "TotalQuantitySold": 4244}],
  "row_count": 5
}
```

Chi tiết đầy đủ: xem [API_DOCS.md](API_DOCS.md)

## Cấu trúc project

```
mini-wren-ai/
├── src/
│   ├── connectors/          # Phase 1: DB connection + schema introspection
│   ├── modeling/             # Phase 2: MDL schema + manifest builder
│   ├── indexing/             # Phase 3: DDLChunker + ChromaDB + embeddings
│   ├── retrieval/            # Phase 4: Schema retrieval + DDL context
│   ├── generation/           # Phase 5: SQL generation + correction
│   ├── pipelines/            # Phase 6: Ask + Deploy pipelines
│   ├── server.py             # Phase 6: FastAPI server
│   └── config.py             # Settings (.env)
├── tests/                    # Test scripts
├── models.yaml               # Model definitions
├── .env.example              # Template cấu hình
├── API_DOCS.md               # API documentation
└── requirements.txt          # Dependencies
```

## Tech Stack

- **Database**: SQL Server (AdventureWorksDW2025)
- **Embeddings**: HuggingFace `multilingual-e5-large`
- **Vector Store**: ChromaDB
- **LLM**: OpenAI-compatible API (GitHub Models)
- **API**: FastAPI + Uvicorn
