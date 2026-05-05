# Stage 13: SQL Correction + SQL Rewriter

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/generation/sql_corrector.py`, `askdataai/generation/sql_rewriter.py` |
| **Classes** | `SQLCorrector`, `SQLRewriter`, `CorrectionPlanner` (Sprint 5), `CorrectionFixer` (Sprint 5) |
| **LLM Call** | 0–3 (execution_only) hoặc 0–4 (taxonomy_guided cap=2 retries × 2 calls) |
| **Bật/tắt** | Luôn chạy (auto-skip nếu voting thành công ở Stage 12) |
| **Strategy toggle** | `settings.correction_strategy` (env `CORRECTION_STRATEGY`) hoặc per-request override |
| **Row limit** | `settings.exec_row_limit` (default 10000, env `EXEC_ROW_LIMIT`) |

## Chức năng

Validate SQL trên database thật, nếu lỗi → gửi LLM sửa → retry. Self-correction loop với 2 strategies.

## Hai strategies

### `execution_only` (default, legacy)

Mỗi attempt: execute → on error → 1 LLM call để fix toàn bộ SQL.

```
attempt 0: rewrite → execute → OK? → return (0 LLM calls)
attempt 0: ERROR → LLM single-shot fix (1 call)
attempt 1: rewrite → execute → OK? → return
attempt 1: ERROR → LLM single-shot fix (2nd call)
attempt 2: rewrite → execute → OK? → return
attempt 2: ERROR → LLM single-shot fix (3rd call)
attempt 3: rewrite → execute → return kết quả
```

LLM correction prompt chứa: DDL + SQL bị lỗi + error message → LLM sửa SQL.

### `taxonomy_guided` (Sprint 5)

Mỗi retry: 2 LLM calls (Planner + Fixer). Cap 2 retries (Sprint 5.6 fix).

```
attempt 0: rewrite → execute → OK? → return
attempt 0: ERROR → CorrectionPlanner.plan() (call 1)
                 → CorrectionFixer.fix() (call 2)
attempt 1: rewrite → execute → OK? → return
attempt 1: ERROR → bail nếu lỗi y hệt attempt 0 (no progress)
                 → otherwise: Planner + Fixer (call 3+4)
attempt 2: cap → return kết quả cuối
```

#### CorrectionPlanner

- Đọc `error_taxonomy.yaml` (~25 sub-categories trong 9 categories: schema_linking, join_errors, aggregation_errors, …).
- Output: `CorrectionPlan{category, sub_category, root_cause, repair_strategy, confidence}`.
- 1 LLM call/retry.

#### CorrectionFixer

- Nhận `CorrectionPlan` + question + ddl + error → produce corrected SQL theo repair strategy chỉ định.
- 1 LLM call/retry.

#### Sprint 5.6 cải tiến

- Cap retries=2 (giảm từ 3) cho taxonomy → tránh stuck loop (vd: medium_008 v1 hang 122s).
- Bail-on-no-progress: nếu lỗi 2 lần liên tiếp identical → break ngay (không waste thêm 2 LLM calls).
- `_execute_sql(limit=settings.exec_row_limit)`: dùng config singleton thay vì hardcode 100. Trước Sprint 5.6: pipeline cắt 100 rows ngay tại correction validate → false-fail trên queries trả >100 rows.

## SQL Rewriter (sub-component)

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/generation/sql_rewriter.py` |
| **Class** | `SQLRewriter` |
| **LLM Call** | × — regex replacement |

Chức năng: Convert model names → tên DB thật trong SQL.

```
Input:  SELECT customers.FirstName FROM customers
Output: SELECT [dbo].[DimCustomer].FirstName FROM [dbo].[DimCustomer]
```

Mapping từ manifest. Sort by name length DESC để tránh partial replacement (ví dụ: `product_subcategories` phải replace trước `products`).

## Output

```
CorrectionResult:
  valid: true/false
  sql: "SELECT ..."             # SQL đã rewrite (DB names)
  original_sql: "SELECT ..."    # SQL gốc (model names)
  retries: 1                    # Số lần retry
  errors: ["Invalid column name 'X'"]
  result: {columns: [...], rows: [...], row_count: N}
  # Sprint 5 — chỉ với taxonomy_guided
  correction_plans: [CorrectionPlan(...), ...]
  strategy_used: "execution_only" | "taxonomy_guided"
```

## Vai trò trong pipeline

Safety net cuối cùng — đảm bảo SQL thực thi thành công. Nếu có lỗi syntax hay column sai, hệ thống tự phát hiện và sửa mà không cần người dùng can thiệp.

## Khi nào dùng strategy nào?

- **execution_only**: nhanh hơn (1 LLM call/retry vs 2), tiết kiệm cost. Phù hợp khi error message LLM-readable (SQL Server messages thường rõ ràng).
- **taxonomy_guided**: chia nhỏ Plan→Fix giúp LLM focus tốt hơn cho lỗi phức tạp (ambiguous column, missing GROUP BY, subquery scope). Cost gấp đôi nhưng recovery rate cao hơn ~10-15% trên hard queries.
