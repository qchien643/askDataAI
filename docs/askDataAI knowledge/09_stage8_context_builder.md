# Stage 8: ContextBuilder

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/retrieval/context_builder.py` |
| **Class** | `ContextBuilder` |
| **Method** | `build(db_schemas, model_names)` |
| **LLM Call** | Không — pure string formatting |
| **Bật/tắt** | Luôn chạy |

## Chức năng

Chuyển đổi db_schemas dict thành **DDL text string**. Đây là input chính cho tất cả LLM stages phía sau (CoT Reasoning, SQL Generation, SQL Correction).

## Output format

```sql
/* {'alias': 'customers', 'description': 'Thông tin khách hàng'} */
CREATE TABLE customers (
  -- {'alias': 'Mã khách hàng', 'description': 'Primary key'}
  CustomerKey INTEGER PRIMARY KEY,
  -- {'alias': 'Tên', 'description': 'Tên khách hàng'}
  FirstName VARCHAR,
  -- {'alias': 'Họ', 'description': 'Họ khách hàng'}
  LastName VARCHAR,
  FOREIGN KEY (GeographyKey) REFERENCES geography(GeographyKey)
);

-- Relationships:
-- internet_sales.CustomerKey = customers.CustomerKey (many_to_one)
```

## Điểm quan trọng

- DDL dùng **model names** (`customers`) KHÔNG PHẢI tên DB thật (`dbo.DimCustomer`)
- Descriptions tiếng Việt được embed trong SQL comments
- FK constraints xuất hiện trong DDL để LLM biết cách JOIN
- **SQL Rewriter** (ở Stage 13) xử lý việc convert model names → DB names khi execute

## Vai trò trong pipeline

Là "ngôn ngữ giao tiếp" giữa hệ thống và LLM. LLM đọc DDL này để hiểu schema. Descriptions tiếng Việt trong comments giúp LLM hiểu ngữ cảnh nghiệp vụ.
