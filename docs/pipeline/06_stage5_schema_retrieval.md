# Stage 5: SchemaRetrieval

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/retrieval/schema_retriever.py` |
| **Class** | `SchemaRetriever` |
| **Method** | `retrieve(query, top_k=5, expand_relationships=True, enable_bidirectional=None)` |
| **LLM Call** | × ở chế độ legacy / ✓ 1 call ở chế độ bidirectional (Sprint 4) |
| **Bật/tắt** | Luôn chạy |
| **Toggle bidirectional** | `settings.enable_bidirectional_retrieval` (env `ENABLE_BIDIRECTIONAL_RETRIEVAL`) hoặc per-request override |

## Chức năng

Tìm tables/columns liên quan đến câu hỏi bằng embedding similarity search, sau đó tự động kéo thêm related tables qua Foreign Key relationships (1-hop expansion).

Sprint 4 thêm chế độ **bidirectional retrieval** (XiYan-SQL inspired): kết hợp table-first và column-first search để tăng recall trên DB lớn.

## Hai chế độ retrieval

### Legacy mode (`enable_bidirectional_retrieval=False`, default)

```
question → embed → vector search "table_descriptions" → top-K tables
                                                           │
                                                           ▼
                                            FK 1-hop expansion (manifest)
                                                           │
                                                           ▼
                                              fetch full table+columns
```

3 bước nội bộ:
1. **Table Retrieval**: Embed câu hỏi → vector search collection `table_descriptions` → top-K model names.
2. **Relationship Expansion**: Duyệt manifest, kéo thêm 1-hop related models qua FK.
3. **Schema Retrieval**: Fetch TABLE + TABLE_COLUMNS từ collection `db_schema`.

### Bidirectional mode (`enable_bidirectional_retrieval=True`, Sprint 4)

```
question → QuestionAugmenter (LLM) ──▶ keywords + entities + sub_questions
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              ▼                                                                ▼
   table-first vector search                                  column-first vector search
   (collection: table_descriptions)                          (collection: column_descriptions)
              │                                                                │
              └───────────────────┬─────────────────────────────────────────────┘
                                  ▼
                            merge tables
                                  ▼
                       FK closure (manifest)
                                  ▼
                         fetch schema docs
```

4 bước nội bộ:
1. **Augment** (`QuestionAugmenter` — 1 LLM call): extract keywords, entities, sub-questions.
2. **Table-first search**: vector search trên `table_descriptions` (như legacy).
3. **Column-first search**: vector search trên `column_descriptions` (collection mới, Sprint 4) → derive parent tables.
4. **Merge + FK closure + fetch schema**.

**Yêu cầu**: ChromaDB phải có collection `column_descriptions` (re-deploy nếu chưa có — `ColumnDescriptionChunker` chỉ index khi flag ON tại thời điểm deploy).

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

Cơ chế chính giúp xử lý **Multi-Hop queries**. Khi người dùng hỏi "doanh thu theo khu vực", hệ thống tìm `internet_sales` → tự kéo thêm `customers` → rồi kéo thêm `geography`. Không cần người dùng nhắc đến các bảng trung gian.

Cả legacy và bidirectional mode đều thực hiện FK expansion.

## Vai trò trong pipeline

Cung cấp schema context cho tất cả stages phía sau (Schema Linking, Column Pruning, Context Building, SQL Generation). Nếu stage này miss bảng cần thiết → SQL sẽ sai.

## Ablation insight (Sprint 6 benchmark)

Trên AdventureWorks DW (14 tables, 170 cols), bidirectional retrieval không cho gain rõ rệt do schema nhỏ. Trên DB nhiều bảng/cột (BIRD, Spider 2.0), gain expected +5-7% EX.
