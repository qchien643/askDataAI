# Stage 9: GlossaryLookup

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/retrieval/business_glossary.py` |
| **Class** | `BusinessGlossary` |
| **Methods** | `lookup(question)`, `build_context(matches)` |
| **LLM Call** | Không — keyword matching |
| **Bật/tắt** | Co — `enable_glossary` |
| **Data source** | `glossary.yaml` |

## Chức năng

Map thuật ngữ nghiệp vụ → SQL concepts. Giải quyết vấn đề "doanh thu" là cột nào? "Khách hàng VIP" có nghĩa gì trong SQL?

## glossary.yaml

```yaml
terms:
  - name: "doanh thu"
    aliases: ["revenue", "sales", "tổng doanh thu", "doanh số"]
    sql_hint: "SUM(internet_sales.SalesAmount)"
    tables: ["internet_sales"]
    description: "Tổng giá trị bán hàng"

  - name: "khách hàng VIP"
    aliases: ["VIP customer"]
    sql_hint: "WHERE TotalPurchaseAmount > 1000000"
    tables: ["customers"]
    description: "Khách hàng có tổng mua > 1 triệu"
```

## Cách matching

Scan câu hỏi (lowercase) tìm keyword matches. Longest match first để tránh match con (ví dụ "doanh thu ròng" match trước "doanh thu").

## Output

```
### BUSINESS GLOSSARY ###
- "doanh thu":
  Description: Tổng giá trị bán hàng
  SQL hint: SUM(internet_sales.SalesAmount)
  Tables: internet_sales
```

Context này được **prepend** vào DDL context trước khi gửi cho LLM.

## Quản lý

Glossary có thể quản lý qua:
- File `glossary.yaml` trực tiếp
- API endpoints: `GET/POST/PUT/DELETE /v1/knowledge/glossary`
- UI: Trang Glossary trong frontend

## Vai trò trong pipeline

Xóa bỏ khoảng cách giữa ngôn ngữ nghiệp vụ và kỹ thuật. Đảm bảo LLM hiểu đúng thuật ngữ domain-specific, đặc biệt quan trọng với tiếng Việt.
