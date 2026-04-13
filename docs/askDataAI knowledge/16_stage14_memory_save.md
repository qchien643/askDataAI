# Stage 14: MemorySave

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/generation/semantic_memory.py` |
| **Class** | `SemanticMemory` |
| **Method** | `save_trace(question, sql, success, result_hash, models_used, error, retries)` |
| **LLM Call** | Không — write JSON file |
| **Bật/tắt** | Co — `enable_memory` |

## Chức năng

Lưu kết quả xử lý (thành công hoặc thất bại) vào `semantic_memory.json`. Stage 10 (SemanticMemory Lookup) sử dụng dữ liệu này để tìm câu hỏi tương tự.

## Dữ liệu lưu trữ

```json
{
  "question": "Top 5 khách hàng mua nhiều nhất",
  "sql": "SELECT TOP 5 c.FirstName, SUM(s.SalesAmount)...",
  "success": true,
  "result_hash": "a1b2c3d4e5f6...",
  "models_used": ["internet_sales", "customers"],
  "error": "",
  "retries": 0,
  "timestamp": "2026-03-31T10:30:00"
}
```

## Giới hạn

- Giữ tối đa **500 traces** mới nhất
- Khi vượt giới hạn → xóa trace cũ nhất

## Vai trò trong pipeline

Hoàn tất vòng lặp self-learning: Stage 14 lưu → Stage 10 đọc → LLM học từ quá khứ. Hệ thống tự cải thiện theo thời gian mà không cần training hay fine-tuning.
