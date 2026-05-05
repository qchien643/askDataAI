# askdataai/retrieval/ — context assembly

Tìm + lắp ráp schema context cho LLM. Không gọi LLM trực tiếp (trừ `schema_linker.py` và `column_pruner.py`).

## Pipeline order

```
schema_retriever  →  schema_linker  →  column_pruner  →  context_builder
   (vector + FK)     (entity/value)    (drop noise)      (DDL string)
                                                              ↓
                                                       business_glossary (prepend)
```

## Files

| File | Class | LLM? |
|---|---|:---:|
| `schema_retriever.py` | `SchemaRetriever` | × (vector search + FK 1-hop) hoặc ✓ (bidirectional, +augmenter LLM call) |
| `question_augmenter.py` | `QuestionAugmenter` | ✓ (1 LLM call extract keywords/entities/sub_questions) |
| `schema_linker.py` | `SchemaLinker` | ✓ (entity links + value links) |
| `column_pruner.py` | `ColumnPruner` | ✓ (auto-skip nếu ≤15 cột) |
| `context_builder.py` | `ContextBuilder` | × (DDL hoặc M-Schema string formatting) |
| `business_glossary.py` | `BusinessGlossary` | × (keyword match `configs/glossary.yaml`) |

## Key conventions

- **Model names vs DB names**: tất cả retrieval/context dùng **model names** (semantic, ví dụ `customers`). `SQLRewriter` (in `generation/`) chuyển sang DB names (`[dbo].[DimCustomer]`) khi execute.
- **Schema output**: gọi `context_builder.build_for_llm(db_schemas, model_names, enable_mschema=None)` — primary API. Nó dispatch giữa:
  - `build()` (legacy DDL `CREATE TABLE` format) khi `enable_mschema=False`
  - `build_mschema()` (XiYan-style key-value với examples + ranges + inline FK) khi `enable_mschema=True`
  - Param `enable_mschema=None` → fallback `settings.enable_mschema` (Sprint 5.6: per-request override).
- **Glossary inject**: `business_glossary.build_context()` prepend vào DDL trước khi gửi LLM. Format: `### BUSINESS GLOSSARY ###\n- "term": SQL hint`.
- **Schema retrieval modes** (Sprint 4): `SchemaRetriever.retrieve(query, top_k=None, expand_relationships=True, enable_bidirectional=None)` dispatch giữa:
  - `_retrieve_legacy()` (single-pass table search + FK 1-hop) khi `enable_bidirectional=False`
  - `_retrieve_bidirectional()` (augment → table-first + column-first → merge + FK closure) khi toggle ON; cần `column_descriptions` ChromaDB collection (re-deploy required).
  - Param `enable_bidirectional=None` → fallback `settings.enable_bidirectional_retrieval` (Sprint 5.6: per-request override).
- **FK expansion**: cả 2 retriever modes đều tự động kéo 1-hop related tables qua FK — đừng filter sớm trong stage trước.
- **FK rendering trong M-Schema**: `_lookup_fk()` ưu tiên `col.foreign_key` field từ YAML; fallback duyệt `manifest.relationships` nếu inline annotation rỗng và target table có trong scope retrieval.

## Khi thêm retrieval step

Đặt sau `schema_retriever`, trước `context_builder`. Output phải là dict `db_schemas` hoặc string hint inject vào DDL prefix.
