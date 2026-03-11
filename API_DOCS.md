# Mini Wren AI — API Documentation

## Khởi động server

```bash
cd e:\code\project\mini-wren-ai\mini-wren-ai
.\venv\Scripts\activate
python -m uvicorn src.server:app --reload --port 8000
```

> **Lưu ý**: PHẢI chạy từ thư mục `mini-wren-ai/` (chứa `src/`), không phải từ `tests/`.

Server tự động deploy khi khởi động. Swagger UI có tại: http://localhost:8000/docs

---

## Endpoints

### 1. Health Check

```
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "deployed": true
}
```

---

### 2. Deploy Manifest

Deploy lại models.yaml → build manifest → index ChromaDB.

```
POST /v1/deploy
Content-Type: application/json
```

**Request body:** không cần

**Curl:**
```bash
curl -X POST http://localhost:8000/v1/deploy
```

**PowerShell:**
```powershell
Invoke-RestMethod -Uri http://localhost:8000/v1/deploy -Method POST
```

**Response:**
```json
{
  "success": true,
  "message": "Deploy successful",
  "models_count": 12,
  "relationships_count": 17,
  "manifest_hash": "abc123...",
  "indexed": true
}
```

---

### 3. Ask (Text-to-SQL)

Hỏi câu hỏi → nhận SQL + kết quả.

```
POST /v1/ask
Content-Type: application/json
```

**Request body:**
```json
{
  "question": "Tổng doanh thu internet sales"
}
```

**Curl:**
```bash
curl -X POST http://localhost:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Tong doanh thu internet sales\"}"
```

**PowerShell:**
```powershell
$body = @{question="Tong doanh thu internet sales"} | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/v1/ask -Method POST -Body $body -ContentType "application/json"
```

**JavaScript (fetch):**
```javascript
const response = await fetch("http://localhost:8000/v1/ask", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question: "Tổng doanh thu internet sales" })
});
const data = await response.json();
```

**Response (thành công):**
```json
{
  "question": "Tong doanh thu internet sales",
  "intent": "TEXT_TO_SQL",
  "sql": "SELECT SUM(SalesAmount) AS TotalRevenue FROM [dbo].[FactInternetSales];",
  "original_sql": "SELECT SUM(SalesAmount) AS TotalRevenue FROM internet_sales;",
  "explanation": "Tính tổng doanh thu từ bảng internet_sales",
  "columns": ["TotalRevenue"],
  "rows": [
    {"TotalRevenue": 29358677.22}
  ],
  "row_count": 1,
  "valid": true,
  "retries": 0,
  "error": "",
  "models_used": ["internet_sales", "customers", "products"]
}
```

**Response (câu hỏi không liên quan):**
```json
{
  "question": "Bạn là ai?",
  "intent": "GENERAL",
  "sql": "",
  "columns": [],
  "rows": [],
  "valid": false,
  "error": "Câu hỏi không liên quan đến dữ liệu."
}
```

---

### 4. Execute SQL

Chạy SQL trực tiếp trên database.

```
POST /v1/sql/execute
Content-Type: application/json
```

**Request body:**
```json
{
  "sql": "SELECT TOP 5 FirstName, LastName FROM [dbo].[DimCustomer]",
  "limit": 100
}
```

| Field | Type | Required | Default | Mô tả |
|-------|------|----------|---------|-------|
| `sql` | string | ✅ | — | SQL query (phải dùng tên DB thật) |
| `limit` | integer | ❌ | 100 | Số rows tối đa trả về |

**Curl:**
```bash
curl -X POST http://localhost:8000/v1/sql/execute \
  -H "Content-Type: application/json" \
  -d "{\"sql\": \"SELECT TOP 5 FirstName, LastName FROM [dbo].[DimCustomer]\", \"limit\": 5}"
```

**PowerShell:**
```powershell
$body = @{sql="SELECT TOP 5 FirstName, LastName FROM [dbo].[DimCustomer]"; limit=5} | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/v1/sql/execute -Method POST -Body $body -ContentType "application/json"
```

**Response:**
```json
{
  "columns": ["FirstName", "LastName"],
  "rows": [
    {"FirstName": "Jon", "LastName": "Yang"},
    {"FirstName": "Eugene", "LastName": "Huang"},
    {"FirstName": "Ruben", "LastName": "Torres"}
  ],
  "row_count": 3
}
```

---

### 5. Get Models

Xem danh sách models + relationships.

```
GET /v1/models
```

**Curl:**
```bash
curl http://localhost:8000/v1/models
```

**Response:**
```json
{
  "models_count": 12,
  "relationships_count": 17,
  "models": [
    {
      "name": "customers",
      "table_reference": "dbo.DimCustomer",
      "description": "Thông tin khách hàng cá nhân...",
      "primary_key": "CustomerKey",
      "columns": [
        {
          "name": "CustomerKey",
          "display_name": "Mã khách hàng",
          "type": "integer",
          "description": "Mã KH (PK, dùng để join)"
        }
      ]
    }
  ],
  "relationships": [
    {
      "name": "internet_sales_customers",
      "model_from": "internet_sales",
      "model_to": "customers",
      "join_type": "MANY_TO_ONE",
      "condition": "internet_sales.CustomerKey = customers.CustomerKey"
    }
  ]
}
```

---

## Error Responses

| HTTP Status | Khi nào |
|-------------|---------|
| `400` | SQL syntax error (endpoint `/v1/sql/execute`) |
| `500` | Server internal error |
| `503` | Chưa deploy (gọi `POST /v1/deploy` trước) |

```json
{
  "detail": "Error message here"
}
```
