# Stage 8: ContextBuilder

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/retrieval/context_builder.py` |
| **Class** | `ContextBuilder` |
| **Primary API** | `build_for_llm(db_schemas, model_names, enable_mschema=None)` |
| **LLM Call** | × — pure string formatting |
| **Bật/tắt** | Luôn chạy |
| **Format toggle** | `settings.enable_mschema` (env `ENABLE_MSCHEMA`) hoặc per-request override |

## Chức năng

Chuyển đổi db_schemas dict + manifest column metadata thành **schema context string**. Đây là input chính cho tất cả LLM stages phía sau (CoT Reasoning, SQL Generation, SQL Correction).

Sprint 2 thêm chế độ **M-Schema** (XiYan-SQL inspired): format key-value gọn hơn DDL, đính kèm examples + ranges + inline FK.

## Hai chế độ output

### Legacy DDL (`enable_mschema=False`, default)

`build()` trả format CREATE TABLE giống WrenAI gốc:

```sql
/* {'alias': 'customers', 'description': 'Thông tin khách hàng'} */
CREATE TABLE customers (
  -- {'alias': 'Mã khách hàng', 'description': 'Primary key'}
  CustomerKey INTEGER PRIMARY KEY,
  -- {'alias': 'Tên', 'description': 'Tên khách hàng'}
  FirstName VARCHAR,
  ...
  FOREIGN KEY (GeographyKey) REFERENCES geography(GeographyKey)
);

-- Relationships:
-- internet_sales.CustomerKey = customers.CustomerKey (many_to_one)
```

### M-Schema (`enable_mschema=True`, Sprint 2)

`build_mschema()` trả format key-value:

```
# Database Schema (M-Schema)

# Table: customers
[Description]: Individual customer information...
[Fields]:
  CustomerKey: INTEGER, PK, examples: [11000, 11001, 11002]
  YearlyIncome: DECIMAL, range: [10000.00 - 170000.00], desc: 'Annual income (USD)'
  Gender: STRING, examples: ['M', 'F'], desc: 'Gender code: M=Male, F=Female'
  GeographyKey: INTEGER, FK -> geography.GeographyKey
  ...

[Relationships]:
  customers.GeographyKey = geography.GeographyKey (MANY_TO_ONE)
```

Mỗi field hiển thị (theo thứ tự): name, type, PK marker, FK target, display name, description, examples (top-3), range (cho numeric/date), enum values.

**Inline FK**: Ưu tiên `col.foreign_key` field trong YAML; fallback duyệt manifest relationships nếu target table có trong scope.

## Helper API

- `build()` — legacy DDL (gọi trực tiếp khi cần force DDL)
- `build_mschema(model_names)` — M-Schema (gọi trực tiếp khi cần force M-Schema)
- `build_for_llm(db_schemas, model_names, enable_mschema=None)` — **primary API**, dispatch dựa trên toggle

## Điểm quan trọng

- DDL/M-Schema dùng **model names** (`customers`) KHÔNG PHẢI tên DB thật (`dbo.DimCustomer`)
- Descriptions trong YAML có thể tiếng Việt hoặc tiếng Anh; M-Schema giữ nguyên
- M-Schema yêu cầu YAML enriched (examples, range, foreign_key) — xem [configs/models.yaml](../../configs/models.yaml)
- **SQL Rewriter** (ở Stage 13) xử lý việc convert model names → DB names khi execute

## Vai trò trong pipeline

Là "ngôn ngữ giao tiếp" giữa hệ thống và LLM. M-Schema gọn hơn DDL ~30% tokens và giàu thông tin hơn (examples + ranges) → giúp LLM hiểu giá trị cột thực tế (ví dụ: `Status: ['A', 'I']` rõ hơn `Status VARCHAR`).

## Ablation insight

M-Schema nổi bật khi YAML có examples/range đầy đủ. Trên AdventureWorks DW với 100% examples + 95% range coverage, gain ~+2-3% EX. Mất gain trên DB không enrich.
