# Stage 10: SemanticMemory

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/generation/semantic_memory.py` |
| **Class** | `SemanticMemory` |
| **Methods** | `find_similar(question)`, `build_context(traces)`, `save_trace(...)` |
| **LLM Call** | Không — Jaccard similarity matching |
| **Bật/tắt** | Co — `enable_memory` |
| **Data source** | `semantic_memory.json` |

## Chức năng

Tìm câu hỏi tương tự đã xử lý thành công trước đó → inject SQL mẫu vào prompt (few-shot learning). Đây là cơ chế **self-learning**: hệ thống càng dùng → càng chính xác.

## Cách hoạt động

### Tìm kiếm (Lookup)
- Tính **Jaccard similarity** trên word set giữa câu hỏi mới và traces cũ
- Threshold: chỉ trả traces có score > 0.3
- Max results: 3 traces tương tự nhất
- Chỉ sử dụng traces có `success=True`

### Lưu (Save — Stage 14)
- Mỗi query thành công → lưu `{question, sql, models_used, result_hash}`
- Giữ tối đa **500 traces** mới nhất

## Ví dụ

Câu hỏi mới: "Top 5 khách hàng mua nhiều nhất"

Trace cũ match:
```
Q: Tổng doanh thu theo khách hàng
SQL: SELECT c.FirstName, SUM(s.SalesAmount) FROM internet_sales s JOIN customers c ON ...
```

→ Inject vào prompt → LLM tham khảo SQL pattern

## Output context

```
### CÂU HỎI TƯƠNG TỰ TRƯỚC ĐÂY ###
Q: Tổng doanh thu theo khách hàng
SQL: SELECT c.FirstName, SUM(s.SalesAmount)...

Q: Top 10 sản phẩm bán chạy nhất
SQL: SELECT TOP 10 p.ProductName, SUM(s.OrderQuantity)...
```

## Vai trò trong pipeline

Few-shot learning tự động — LLM học từ các câu hỏi thành công trước đó mà không cần training hay fine-tuning. Đặc biệt hữu ích cho domain-specific queries.
