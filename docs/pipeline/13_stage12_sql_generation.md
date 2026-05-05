# Stage 12: SQL Generation + Voting

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **Files** | `askdataai/generation/candidate_generator.py`, `askdataai/generation/execution_voter.py`, `askdataai/generation/sql_generator.py` |
| **Classes** | `CandidateGenerator`, `ExecutionVoter`, `SQLGenerator` |
| **LLM Call** | Co — N lần (default 3, hoặc 1 nếu voting tắt) |
| **Bật/tắt** | Co — `enable_voting` + `num_candidates` |

## Chức năng

Sinh SQL từ context đã enriched. Có 2 chế độ:

### Chế độ 1: Single-pass (voting tắt)
- Dùng `SQLGenerator`, 1 LLM call, temperature 0.0
- Output: 1 SQL

### Chế độ 2: Multi-candidate + Voting (voting bật)
- Sinh **N SQL candidates** với strategies khác nhau
- Chạy tất cả trên DB thật
- Majority vote chọn SQL tốt nhất

## 3 Strategies (Multi-candidate)

| # | Strategy | Temperature | CoT Reasoning? |
|---|---|:---:|:---:|
| 1 | `precise_with_reasoning` | 0.0 | Co |
| 2 | `balanced_with_reasoning` | 0.3 | Co |
| 3 | `creative_no_reasoning` | 0.7 | Không |

**Inspired by**: CHASE-SQL, CSC-SQL

## Voting Flow

1. **Rewrite** mỗi candidate SQL (model names → DB names) qua `SQLRewriter`
2. **Execute** trên SQL Server thật (limit 50 rows)
3. **Hash** kết quả bằng MD5: `hash(sorted_columns + rows)`
4. **Group** candidates theo result hash
5. **Majority vote**: nhóm có nhiều candidates nhất → chiến thắng
6. Trong nhóm thắng → chọn candidate có **temperature thấp nhất**

## Voting methods

| Method | Điều kiện |
|---|---|
| `majority` | 2+ candidates ra cùng kết quả |
| `single_success` | Chỉ 1 candidate chạy được |
| `single` | Chỉ có 1 candidate |
| `fallback` | Không candidate nào chạy được → chuyển cho Stage 13 |

Nếu voting thành công → **bỏ qua Stage 13** (SQL Correction), vào thẳng Stage 14.

## Input

- `question`: Câu hỏi user
- `ddl_context`: DDL enriched (glossary + memory + instructions + DDL)
- `reasoning_plan`: CoT plan từ Stage 11
- `schema_hints`: Schema linking hints từ Stage 6

## Vai trò trong pipeline

Đây là stage sinh SQL thực tế. Multi-candidate voting là kỹ thuật SOTA đảm bảo chính xác: nếu 2/3 candidates ra cùng kết quả → rất khả năng đúng.
