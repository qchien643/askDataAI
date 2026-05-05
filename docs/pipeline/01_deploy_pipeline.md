# Deploy Pipeline

## Tổng quan

Deploy Pipeline chạy **1 lần duy nhất** khi server khởi động hoặc khi người dùng kết nối database mới. Pipeline này không gọi LLM, chỉ xử lý metadata.

**File**: `askdataai/pipelines/deploy_pipeline.py`

## Luồng xử lý

```
models.yaml → [1] SchemaIntrospector → [2] ManifestBuilder → [3] SchemaIndexer → Ready
```

## Các bước chi tiết

### Bước 1: SchemaIntrospector
- **File**: `askdataai/connectors/schema_introspector.py`
- **Chức năng**: Kết nối SQL Server, đọc metadata từ `INFORMATION_SCHEMA`
- **Output**: `DatabaseSchema` object chứa danh sách tables, columns, foreign keys, data types
- **Không gọi LLM**

### Bước 2: ManifestBuilder
- **File**: `askdataai/modeling/manifest_builder.py`
- **Chức năng**: Đọc `models.yaml` + kết hợp DB metadata → build `Manifest` object
- **Manifest** chứa:
  - Danh sách Models (tên semantic, table_reference, description, columns)
  - Danh sách Relationships (join conditions, join types)
  - Mapping giữa model names (ngắn gọn) → tên DB thật (dbo.DimCustomer)
- **Validate**: Kiểm tra mỗi model/column trong YAML có tồn tại trong DB thật không

### Bước 3: SchemaIndexer
- **File**: `askdataai/indexing/schema_indexer.py`
- **Chức năng**: Embed schema documents → index vào ChromaDB
- **Embedding**: Gọi **OpenAI Embedding API** (text-embedding-3-small)
- **2 collections**:
  - `db_schema`: Chứa TABLE + TABLE_COLUMNS documents (DDL chi tiết cho SQL generation)
  - `table_descriptions`: Chứa description ngắn gọn (cho table discovery khi có câu hỏi)

## models.yaml

File cấu hình semantic layer, nơi định nghĩa mô tả tiếng Việt cho mỗi bảng/cột:

```yaml
models:
  - name: customers
    table_reference: dbo.DimCustomer
    description: "Thông tin khách hàng"
    columns:
      - name: CustomerKey
        source: CustomerKey
        type: integer
        alias: "Mã khách hàng"
        description: "Primary key"
        primary_key: true
      - name: FirstName
        source: FirstName
        type: string
        alias: "Tên"
        description: "Tên khách hàng"

relationships:
  - name: sales_customer
    model_from: internet_sales
    model_to: customers
    join_type: many_to_one
    condition: internet_sales.CustomerKey = customers.CustomerKey
```

## Tại sao Semantic Layer quan trọng?

Descriptions tiếng Việt giúp vector search match chính xác hơn. Khi người dùng hỏi "khách hàng", hệ thống tìm được bảng `customers` nhờ description "Thông tin khách hàng" thay vì phải đoán từ tên kỹ thuật `DimCustomer`.

Theo benchmark BIRD, có descriptions tốt tăng accuracy 10–15%.
