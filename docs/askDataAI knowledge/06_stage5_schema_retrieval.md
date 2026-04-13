# Stage 5: SchemaRetrieval

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `src/retrieval/schema_retriever.py` |
| **Class** | `SchemaRetriever` |
| **Method** | `retrieve(query, top_k=5)` |
| **LLM Call** | Không — dùng vector search (ChromaDB + OpenAI Embedding) |
| **Bật/tắt** | Luôn chạy |

## Chức năng

Tìm tables/columns liên quan đến câu hỏi bằng embedding similarity search, sau đó tự động kéo thêm related tables qua Foreign Key relationships (1-hop expansion).

## 3 bước nội bộ

### Bước 1: Table Retrieval
- Embed câu hỏi bằng **OpenAI Embedding API**
- Vector search trong collection `table_descriptions` của ChromaDB
- Trả về top-K model names gần nhất

### Bước 2: Relationship Expansion (FK Expansion)
- Từ model names tìm được, duyệt manifest relationships
- Kéo thêm **1-hop** related models qua Foreign Key
- Ví dụ: "doanh thu khách hàng" → tìm `internet_sales` → expand thêm `customers` (qua FK CustomerKey)

### Bước 3: Schema Retrieval
- Fetch TABLE + TABLE_COLUMNS documents từ collection `db_schema`
- Assemble thành db_schemas dict (chứa cấu trúc đầy đủ)

## Output

```
RetrievalResult:
  query: "Top 5 khách hàng mua nhiều nhất"
  model_names: ["internet_sales", "customers", "products"]  # sau expansion
  expanded_from: ["internet_sales", "customers"]             # trước expansion
  db_schemas: [
    {type: "TABLE", name: "internet_sales", columns: [...]},
    {type: "TABLE", name: "customers", columns: [...]},
    ...
  ]
```

## FK Expansion — tại sao quan trọng?

Đây là cơ chế chính giúp askDataAI xử lý **Multi-Hop queries**. Khi người dùng hỏi "doanh thu theo khu vực", hệ thống tìm `internet_sales` → tự kéo thêm `customers` → rồi kéo thêm `geography`. Không cần người dùng nhắc đến các bảng trung gian.

## Vai trò trong pipeline

Cung cấp schema context cho tất cả stages phía sau (Schema Linking, Column Pruning, Context Building, SQL Generation). Nếu stage này miss bảng cần thiết → SQL sẽ sai.
