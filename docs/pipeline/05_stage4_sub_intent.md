# Stage 4: SubIntentDetect

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/generation/sub_intent.py` |
| **Class** | `SubIntentDetector` |
| **Method** | `detect(question)` |
| **LLM Call** | Ưu tiên keyword matching (instant), fallback LLM nếu không match |
| **Bật/tắt** | Luôn chạy (sau IntentClassifier) |

## Chức năng

Sau khi Stage 3 xác định intent = TEXT_TO_SQL, Stage 4 phân loại chi tiết hơn để SQL Generator chọn strategy phù hợp. Cung cấp `sql_hints` giúp LLM sinh SQL đúng pattern.

## 7 Sub-Intent

| Sub-Intent | Ví dụ | SQL Hints |
|---|---|---|
| **RETRIEVAL** | "Danh sách khách hàng" | Simple SELECT with relevant columns |
| **AGGREGATION** | "Tổng doanh thu" | SUM, COUNT, AVG + GROUP BY |
| **COMPARISON** | "So sánh Q1 vs Q2" | CASE WHEN, subquery comparison |
| **TREND** | "Xu hướng theo tháng" | DATEPART, GROUP BY time period |
| **RANKING** | "Top 5 sản phẩm" | TOP N, ORDER BY DESC |
| **FILTER** | "Khách hàng ở Hà Nội" | WHERE clause conditions |
| **MULTI_HOP** | Câu hỏi phức tạp nhiều bảng | CTE chain, multiple JOINs |

## Cách hoạt động

1. **Keyword matching** (ưu tiên, instant): Dùng regex patterns để match keywords
   - "top 5" → RANKING
   - "tổng", "đếm", "trung bình" → AGGREGATION
   - "xu hướng", "theo tháng" → TREND
   - "so sánh", "vs" → COMPARISON

2. **LLM fallback**: Nếu không match pattern nào → gọi LLM phân loại (optional)

3. **Default**: RETRIEVAL nếu không match được

## Output

```
SubIntentResult:
  sub_intent: RANKING
  confidence: 0.85
  sql_hints: "Use TOP N or ORDER BY with DESC/ASC..."
```

`sql_hints` được inject vào prompt của SQL Generation stage.

## Vai trò trong pipeline

Giúp SQL Generator biết nên dùng SQL pattern nào (aggregation vs ranking vs trend...), tăng chính xác của SQL sinh ra.
