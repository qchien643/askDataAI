# Stage 13.5: SQL Guardian

## Thông tin

| Thuộc tính | Giá trị |
|---|---|
| **File** | `askdataai/security/guardian.py` |
| **Class** | `SQLGuardian` |
| **Method** | `validate(sql)` |
| **LLM Call** | Không — regex + sqlparse |
| **Bật/tắt** | Luôn chạy |
| **Config** | `askdataai/security/guardian.yaml` |

## Chức năng

5-layer security pipeline kiểm tra và bảo vệ SQL trước khi trả kết quả cho người dùng. Mỗi guard chạy tuần tự, nếu guard nào fail → block ngay.

## 5 Guard Layers

### Layer 1: SQL Injection Guard
- Phát hiện injection patterns: `'; --`, `UNION SELECT`, `OR 1=1`...
- Kiểm tra bằng regex

### Layer 2: Read-Only Guard
- Chỉ cho phép **SELECT** statements
- Chặn: DELETE, DROP, UPDATE, INSERT, ALTER, TRUNCATE, EXEC, GRANT...
- Parse SQL bằng `sqlparse` để xác định statement type

### Layer 3: Table Access Guard
- Chỉ cho phép truy vấn tables trong **whitelist** (từ manifest)
- Extract table names từ SQL bằng regex
- Block nếu query bảng không có trong manifest

### Layer 4: Column Masking Guard
- Mask cột nhạy cảm trong SELECT output
- Ví dụ: `Phone` → `'***' AS Phone`, `Email` → `'***' AS Email`
- Cấu hình masked columns trong `guardian.yaml`
- Guard này **modify SQL** thay vì block

### Layer 5: Row-Level Security (RLS)
- Inject WHERE clauses tự động
- Ví dụ: nhân viên chỉ xem dữ liệu department mình
- `WHERE DepartmentID = {session.department_id}`
- Cấu hình RLS policies trong `guardian.yaml`
- Guard này **modify SQL** thay vì block

## Output

```
GuardianResult:
  safe: true/false
  sql: "SELECT ..."        # SQL đã modify (nếu có masking/RLS)
  original_sql: "SELECT ..." # SQL gốc
  guards_passed: ["injection", "read_only", "table_access", "masking", "rls"]
  blocked_by: ""           # Tên guard đã block (nếu fail)
  reason: ""               # Lý do (nếu fail)
```

## Vai trò trong pipeline

Bảo mật enterprise-grade. Chặn mọi SQL nguy hiểm trước khi trả kết quả, đồng thời tự động áp dụng data privacy (masking) và access control (RLS).
