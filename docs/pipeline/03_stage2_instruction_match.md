# Stage 2: InstructionMatch

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/generation/instruction_matcher.py` |
| **Class** | `InstructionMatcher` |
| **Method** | `match(question)` |
| **LLM Call** | Không — keyword/regex matching |
| **Bật/tắt** | Luôn chạy |

## Chức năng

Match câu hỏi với danh sách **Knowledge Instructions** (business rules) đã được cấu hình trước. Khi match, inject business rules vào context trước khi SQL generation.

Lấy ý tưởng từ WrenAI Interactive Mode: "Apply relevant instructions — checks predefined instructions or business rules that should be applied before generating the query."

## Cách hoạt động

1. Mỗi instruction có:
   - `match_patterns`: Danh sách regex patterns
   - `sql_condition`: SQL WHERE condition cần inject
   - `context_hint`: Gợi ý context cho LLM
   - `scope`: `"global"` (áp dụng mọi query) hoặc `"question"` (chỉ khi match)

2. Global instructions luôn được áp dụng
3. Question-matching instructions chỉ áp dụng khi regex match

## Ví dụ

**Instruction**:
```
id: "exclude_cancelled"
description: "Khi tính doanh thu, luôn exclude đơn cancelled"
match_patterns: ["doanh\\s*thu", "revenue", "sales"]
sql_condition: "Status != 'Cancelled'"
context_hint: "Khi tính doanh thu, luôn loại trừ đơn hàng đã bị hủy (Status = 'Cancelled')"
```

**Câu hỏi**: "Tổng doanh thu tháng 1" → match "doanh thu" → inject filter

**Output context**:
```
## Business Rules (Instructions)
Áp dụng các quy tắc sau khi sinh SQL:
• Khi tính doanh thu, luôn loại trừ đơn hàng đã bị hủy (Status = 'Cancelled')
```

## Vai trò trong pipeline

Đảm bảo các business rules luôn được áp dụng nhất quán, không phụ thuộc vào việc người dùng có nhắc đến hay không. Giúp LLM sinh SQL đúng ngữ cảnh nghiệp vụ.
