# Stage 1: PreFilter

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/generation/pre_filter.py` |
| **Class** | `PreFilter` |
| **Method** | `filter(question)` |
| **LLM Call** | Không — regex/keyword matching |
| **Bật/tắt** | Luôn chạy |

## Chức năng

Lọc nhanh câu hỏi bằng regex/keyword, KHÔNG dùng LLM. Tiết kiệm API calls cho khoảng 40% câu hỏi không cần SQL generation. Chạy dưới 1ms.

## Phân loại

| Kết quả | Hành động | Ví dụ |
|---|---|---|
| **GREETING** | Trả lời chào ngay | "Xin chào", "Hello" |
| **DESTRUCTIVE** | Từ chối ngay (bảo mật) | "Xóa bảng customers", "DROP TABLE" |
| **OUT_OF_SCOPE** | Từ chối (không liên quan) | "Thời tiết hôm nay" |
| **SCHEMA_EXPLORE** | Chuyển cho SchemaExplorer | "Có bảng nào?", "Mô tả bảng customers" |
| **NEEDS_LLM** | Tiếp tục pipeline → Stage 2 | "Top 5 khách hàng mua nhiều nhất" |

## Thứ tự ưu tiên

1. Empty/quá ngắn → reject
2. GREETING → trả lời chào
3. DESTRUCTIVE → từ chối (xóa/sửa/thêm dữ liệu)
4. OUT_OF_SCOPE → reject
5. SCHEMA_EXPLORE → trả lời schema
6. NEEDS_LLM → cần LLM classify tiếp

## Các patterns

- **Greeting**: "xin chào", "hello", "hi", "chào bạn"...
- **Destructive**: "xóa", "delete", "drop", "truncate", "insert", "update"...
- **Schema**: "bảng nào", "mô tả bảng", "cấu trúc", "schema", "relationship"...

## Vai trò trong pipeline

PreFilter là "cổng bảo vệ" đầu tiên — chặn sớm các câu hỏi không cần xử lý, tiết kiệm chi phí LLM. Đặc biệt quan trọng trong việc chặn destructive intent trước khi bất kỳ LLM nào được gọi.
