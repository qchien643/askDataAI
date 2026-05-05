# Stage 3: IntentClassifier

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/generation/intent_classifier.py` |
| **Class** | `IntentClassifier` |
| **Method** | `classify(question, model_names)` |
| **LLM Call** | Co — 1 lần `chat_json()` qua OpenAI API |
| **Bật/tắt** | Luôn chạy |

## Chức năng

Phân loại câu hỏi thành 1 trong 4 loại intent bằng LLM. Đây là bước đầu tiên sử dụng LLM trong pipeline.

Prompt đã được tối ưu nhỏ gọn vì Stage 1 (PreFilter) đã lọc bớt greeting và obvious out-of-scope.

## 4 Intent

| Intent | Mô tả | Hành động |
|---|---|---|
| **TEXT_TO_SQL** | Câu hỏi yêu cầu truy vấn/phân tích dữ liệu | Tiếp tục pipeline → Stage 4 |
| **SCHEMA_EXPLORE** | Câu hỏi về cấu trúc database | Chuyển cho SchemaExplorer (không sinh SQL) |
| **GENERAL** | Câu hỏi không liên quan | Trả lời từ chối |
| **AMBIGUOUS** | Câu hỏi mơ hồ, cần làm rõ | Yêu cầu hỏi lại |

## Input

- `question`: Câu hỏi user (đã qua PreFilter)
- `model_names`: Danh sách tên models trong manifest (ví dụ: `["internet_sales", "customers", "products"]`)

Model names được inject vào system prompt để LLM biết database chứa gì.

## Output

```
IntentResult:
  intent: TEXT_TO_SQL
  reason: "Câu hỏi yêu cầu truy vấn top 5 khách hàng theo doanh số"
```

## Ví dụ phân loại

| Câu hỏi | Intent |
|---|---|
| "Tổng doanh thu theo tháng" | TEXT_TO_SQL |
| "Có bảng nào trong database?" | SCHEMA_EXPLORE |
| "Thời tiết hôm nay thế nào?" | GENERAL |
| "Cho xem dữ liệu" | AMBIGUOUS |

## Vai trò trong pipeline

Là checkpoint chính để quyết định câu hỏi có cần sinh SQL hay không. Nếu không phải TEXT_TO_SQL, pipeline dừng ngay tại đây — tiết kiệm 4–10 LLM calls phía sau.
