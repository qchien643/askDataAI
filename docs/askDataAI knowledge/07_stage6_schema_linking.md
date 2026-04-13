# Stage 6: SchemaLinking

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/retrieval/schema_linker.py` |
| **Class** | `SchemaLinker` |
| **Method** | `link(question, ddl_context)` |
| **LLM Call** | Co — 1 lần `chat_json()` qua OpenAI API |
| **Bật/tắt** | Co — `enable_schema_linking` |

## Chức năng

Map explicitly các entity/value trong câu hỏi → table.column cụ thể. Giải quyết bài toán ambiguity: "khách hàng" là bảng nào? "Hà Nội" là cột nào?

**Inspired by**: DIN-SQL, CHESS, RSL-SQL (SOTA papers 2024)

## 2 loại linking

### Entity Links
Map khái niệm → table/column:
- "khách hàng" → `customers` (table)
- "doanh thu" → `internet_sales.SalesAmount` (column)

### Value Links
Map giá trị cụ thể → table.column = value:
- "Hà Nội" → `geography.City = 'Hà Nội'`
- "VIP" → `customers.CustomerType = 'VIP'`

## Output

```
SchemaLinkResult:
  entity_links: [
    {mention: "khách hàng", table: "customers", column: "*", confidence: 1.0}
  ]
  value_links: [
    {mention: "Hà Nội", table: "geography", column: "City", value: "Hà Nội", operator: "="}
  ]
  context_hints: "### SCHEMA LINKING ###\n- 'khách hàng' → table customers\n..."
```

`context_hints` được inject vào prompt SQL Generation.

## Ví dụ

Câu hỏi: "Top 5 khách hàng ở Hà Nội mua nhiều nhất"

Output:
```
### SCHEMA LINKING ###
- "khách hàng" → table customers
- "mua nhiều" → internet_sales.SalesAmount

### VALUE FILTERS ###
- "Hà Nội" → geography.City = 'Hà Nội'
```

## Vai trò trong pipeline

Giảm ambiguity cho LLM — thay vì LLM phải tự đoán "khách hàng" là bảng nào, Schema Linking đã map sẵn. Đặc biệt quan trọng với tiếng Việt vì tên kỹ thuật (DimCustomer) khác xa từ ngữ tự nhiên.
