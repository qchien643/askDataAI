# Stage 11: CoT Reasoning

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/generation/sql_reasoner.py` |
| **Class** | `SQLReasoner` |
| **Method** | `reason(question, ddl_context)` |
| **LLM Call** | Co — 1 lần `chat_json()` qua OpenAI API |
| **Bật/tắt** | Co — `enable_cot_reasoning` |

## Chức năng

Chain-of-Thought (CoT) reasoning — LLM phân tích câu hỏi thành kế hoạch truy vấn chi tiết **trước khi viết SQL**. Thay vì sinh SQL ngay, hệ thống yêu cầu LLM suy nghĩ từng bước.

**Inspired by**: DIN-SQL, SQL-of-Thought, STaR-SQL

## Output

```
ReasoningResult:
  steps: [
    "Bước 1: JOIN internet_sales với customers qua CustomerKey",
    "Bước 2: GROUP BY khách hàng",
    "Bước 3: SUM(SalesAmount) cho mỗi khách hàng",
    "Bước 4: ORDER BY DESC và lấy TOP 5"
  ]
  tables_needed: ["internet_sales", "customers"]
  columns_needed: ["internet_sales.SalesAmount", "customers.FirstName"]
  aggregations: ["SUM(internet_sales.SalesAmount)"]
  grouping: ["customers.CustomerKey"]
  ordering: "DESC"
  reasoning_text: "### KẾ HOẠCH TRUY VẤN ###\n..."
```

`reasoning_text` được inject vào prompt SQL Generation → LLM sinh SQL theo plan.

## Tại sao CoT quan trọng?

Với câu hỏi đơn giản ("tổng doanh thu"), LLM có thể sinh SQL đúng ngay. Nhưng với câu hỏi Multi-Hop phức tạp, CoT giúp LLM:
- Xác định tables cần JOIN
- Xác định aggregation cần dùng
- Lập thứ tự các bước logic
- Tránh bỏ sót GROUP BY hay JOIN condition

## Vai trò trong pipeline

Tăng chất lượng SQL cho câu hỏi phức tạp. `reasoning_text` là "bản kế hoạch" mà SQL Generator sẽ follow.
