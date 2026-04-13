# Stage 7: ColumnPruning

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/retrieval/column_pruner.py` |
| **Class** | `ColumnPruner` |
| **Method** | `prune(question, db_schemas, min_columns=3)` |
| **LLM Call** | Co — 1 lần `chat_json()` (auto-skip nếu tổng columns ≤ 15) |
| **Bật/tắt** | Co — `enable_column_pruning` |

## Chức năng

Loại bỏ columns không liên quan đến câu hỏi → giảm token cost, tăng accuracy. LLM chọn columns cần thiết, nhưng hệ thống luôn giữ PK/FK để đảm bảo JOIN đúng.

**Inspired by**: CHESS Schema Selector, X-Linking

## Cách hoạt động

1. LLM nhận schema summary + câu hỏi → trả danh sách columns cần giữ
2. Hệ thống apply pruning với safety rules:
   - Luôn giữ PK columns (dù LLM không chọn)
   - Luôn giữ FK constraints
   - Mỗi table tối thiểu `min_columns` (default: 3)
   - Table không được LLM nhắc → giữ nguyên tất cả columns

## Auto-skip

Nếu **tổng columns ≤ 15** → trả original schemas, không gọi LLM. Vì context đã đủ nhỏ, pruning không cần thiết.

## Ví dụ

Câu hỏi: "Top 5 khách hàng mua nhiều"

Trước pruning: `internet_sales` có 20 columns
Sau pruning: giữ `SalesOrderNumber` (PK), `SalesAmount`, `CustomerKey` (FK), `OrderDate`

→ Giảm từ 20 → 4 columns = tiết kiệm tokens đáng kể

## Vai trò trong pipeline

Giảm noise cho LLM ở SQL Generation stage. Khi schema có quá nhiều cột không liên quan, LLM dễ bị "phân tâm" và chọn sai cột. Pruning giữ context gọn gàng, tập trung.
