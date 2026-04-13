# Stage 13: SQL Correction + SQL Rewriter

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/generation/sql_corrector.py`, `src/generation/sql_rewriter.py` |
| **Classes** | `SQLCorrector`, `SQLRewriter` |
| **LLM Call** | Co — 0 đến 3 lần (retry loop) |
| **Bật/tắt** | Luôn chạy (auto-skip nếu voting thành công ở Stage 12) |

## Chức năng

Validate SQL trên database thật, nếu lỗi → gửi LLM sửa → retry (max 3 lần). Self-correction loop.

## Retry Loop

```
attempt 0: rewrite SQL → execute → OK? → return (0 LLM calls)
attempt 0: rewrite SQL → execute → ERROR → gửi LLM sửa (1 call)
attempt 1: rewrite corrected SQL → execute → OK? → return
attempt 1: rewrite → execute → ERROR → gửi LLM sửa (2nd call)
attempt 2: rewrite → execute → OK? → return
attempt 2: rewrite → execute → ERROR → gửi LLM sửa (3rd call)
attempt 3: rewrite → execute → return kết quả (valid hoặc invalid)
```

LLM correction prompt chứa: DDL + SQL bị lỗi + error message → LLM sửa SQL.

## SQL Rewriter (sub-component)

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/generation/sql_rewriter.py` |
| **Class** | `SQLRewriter` |
| **LLM Call** | Không — regex replacement |

Chức năng: Convert model names → tên DB thật trong SQL.

```
Input:  SELECT customers.FirstName FROM customers
Output: SELECT [dbo].[DimCustomer].FirstName FROM [dbo].[DimCustomer]
```

Mapping từ manifest. Sort by name length DESC để tránh partial replacement (ví dụ: `product_subcategories` phải replace trước `products`).

## Output

```
CorrectionResult:
  valid: true/false
  sql: "SELECT ..."         # SQL đã rewrite (DB names)
  original_sql: "SELECT ..." # SQL gốc (model names)
  retries: 1                 # Số lần retry
  errors: ["Invalid column name 'X'"]  # Lỗi gặp phải
  result: {columns: [...], rows: [...], row_count: N}
```

## Vai trò trong pipeline

Safety net cuối cùng — đảm bảo SQL thực thi thành công. Nếu có lỗi syntax hay column sai, hệ thống tự phát hiện và sửa mà không cần người dùng can thiệp.
