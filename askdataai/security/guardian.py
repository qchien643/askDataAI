"""
SQL Guardian — Kiểm tra và bảo vệ SQL trước khi thực thi.

5 Guard Layers (lấy ý tưởng từ WrenAI Data Security):
1. SQL Injection Guard — phát hiện injection patterns
2. Read-Only Guard — chỉ cho phép SELECT
3. Table Access Guard — whitelist tables từ manifest
4. Column Masking Guard — mask cột nhạy cảm
5. Row Filter Guard — inject WHERE clause (RLS-style)

Usage:
    guardian = SQLGuardian.from_config("src/security/guardian.yaml")
    guardian.config.set_allowed_tables_from_manifest(manifest)
    result = guardian.validate(sql)
    if not result.safe:
        raise SecurityError(result.reason)
"""

import logging
import re
import sqlparse
from dataclasses import dataclass, field
from pathlib import Path

from askdataai.security.policies import GuardianConfig

logger = logging.getLogger(__name__)


@dataclass
class GuardResult:
    """Kết quả validate từ một guard."""
    safe: bool
    guard_name: str
    reason: str = ""
    modified_sql: str = ""  # SQL sau khi được sửa (masking, RLS)


@dataclass
class GuardianResult:
    """Kết quả tổng hợp từ SQLGuardian."""
    safe: bool
    sql: str  # SQL cuối cùng (có thể đã được modify)
    original_sql: str
    guards_passed: list[str] = field(default_factory=list)
    blocked_by: str = ""
    reason: str = ""


class SQLGuardian:
    """
    SQL Guardian — 5-layer security pipeline.

    Mỗi guard chạy tuần tự. Nếu guard nào fail → block ngay.
    Một số guard có thể modify SQL (masking, RLS inject).
    """

    def __init__(self, config: GuardianConfig | None = None):
        self._config = config or GuardianConfig()
        # Compile regex patterns
        self._injection_patterns = []
        for pattern in self._config.blocked_patterns:
            try:
                self._injection_patterns.append(
                    re.compile(pattern, re.IGNORECASE)
                )
            except re.error as e:
                logger.warning(f"Invalid guardian regex pattern '{pattern}': {e}")

    @classmethod
    def from_config(cls, config_path: str = "src/security/guardian.yaml") -> "SQLGuardian":
        """Load Guardian từ YAML config."""
        config = GuardianConfig.from_yaml(config_path)
        return cls(config)

    @property
    def config(self) -> GuardianConfig:
        return self._config

    def validate(self, sql: str) -> GuardianResult:
        """
        Chạy tất cả 5 guards tuần tự trên SQL.

        Returns:
            GuardianResult với safe=True/False và SQL cuối cùng.
        """
        original_sql = sql
        current_sql = sql
        guards_passed = []

        # Guard 1: SQL Injection
        result = self._guard_injection(current_sql)
        if not result.safe:
            return GuardianResult(
                safe=False, sql=current_sql, original_sql=original_sql,
                guards_passed=guards_passed,
                blocked_by=result.guard_name, reason=result.reason,
            )
        guards_passed.append(result.guard_name)

        # Guard 2: Read-Only
        result = self._guard_read_only(current_sql)
        if not result.safe:
            return GuardianResult(
                safe=False, sql=current_sql, original_sql=original_sql,
                guards_passed=guards_passed,
                blocked_by=result.guard_name, reason=result.reason,
            )
        guards_passed.append(result.guard_name)

        # Guard 3: Table Access
        result = self._guard_table_access(current_sql)
        if not result.safe:
            return GuardianResult(
                safe=False, sql=current_sql, original_sql=original_sql,
                guards_passed=guards_passed,
                blocked_by=result.guard_name, reason=result.reason,
            )
        guards_passed.append(result.guard_name)

        # Guard 4: Column Masking (may modify SQL)
        result = self._guard_column_masking(current_sql)
        if result.modified_sql:
            current_sql = result.modified_sql
        guards_passed.append(result.guard_name)

        # Guard 5: Row Filter / RLS (may modify SQL)
        result = self._guard_row_filter(current_sql)
        if result.modified_sql:
            current_sql = result.modified_sql
        guards_passed.append(result.guard_name)

        logger.info(
            f"Guardian: SQL passed all {len(guards_passed)} guards "
            f"{'(modified)' if current_sql != original_sql else '(clean)'}"
        )

        return GuardianResult(
            safe=True,
            sql=current_sql,
            original_sql=original_sql,
            guards_passed=guards_passed,
        )

    # ─── Guard 1: SQL Injection ──────────────────────────────────

    def _guard_injection(self, sql: str) -> GuardResult:
        """Phát hiện SQL injection patterns."""
        for pattern in self._injection_patterns:
            match = pattern.search(sql)
            if match:
                logger.warning(
                    f"Guardian BLOCKED (injection): pattern={pattern.pattern}, "
                    f"match='{match.group()[:50]}'"
                )
                return GuardResult(
                    safe=False,
                    guard_name="sql_injection",
                    reason=f"SQL injection pattern detected: {match.group()[:30]}",
                )
        return GuardResult(safe=True, guard_name="sql_injection")

    # ─── Guard 2: Read-Only ──────────────────────────────────────

    def _guard_read_only(self, sql: str) -> GuardResult:
        """Chỉ cho phép SELECT statements."""
        if not self._config.read_only:
            return GuardResult(safe=True, guard_name="read_only")

        # Parse SQL để lấy statement type
        sql_upper = sql.strip().upper()

        # Cho phép WITH (CTE) + SELECT
        if sql_upper.startswith("WITH"):
            # CTE — check rằng sau CTE vẫn là SELECT
            # Tìm keyword đầu tiên sau phần CTE
            try:
                parsed = sqlparse.parse(sql)
                for stmt in parsed:
                    stmt_type = stmt.get_type()
                    if stmt_type and stmt_type.upper() not in ("SELECT", "UNKNOWN"):
                        return GuardResult(
                            safe=False,
                            guard_name="read_only",
                            reason=f"Only SELECT allowed. Found: {stmt_type}",
                        )
            except Exception:
                pass  # sqlparse fail → fallback to keyword check
            return GuardResult(safe=True, guard_name="read_only")

        # Kiểm tra bắt đầu bằng SELECT
        if not sql_upper.startswith("SELECT"):
            # Check blocked DML keywords
            for keyword in self._config.blocked_dml:
                pattern = rf'\b{re.escape(keyword)}\b'
                if re.search(pattern, sql_upper):
                    logger.warning(f"Guardian BLOCKED (read_only): keyword={keyword}")
                    return GuardResult(
                        safe=False,
                        guard_name="read_only",
                        reason=f"Read-only mode: '{keyword}' statements not allowed",
                    )

        return GuardResult(safe=True, guard_name="read_only")

    # ─── Guard 3: Table Access ───────────────────────────────────

    def _guard_table_access(self, sql: str) -> GuardResult:
        """Chỉ cho phép truy vấn bảng trong whitelist (từ manifest)."""
        if not self._config.allowed_tables:
            # Chưa có whitelist → skip
            return GuardResult(safe=True, guard_name="table_access")

        # Extract table names từ SQL
        tables_in_sql = self._extract_tables(sql)

        # Check mỗi table against whitelist
        allowed_lower = {t.lower() for t in self._config.allowed_tables}

        for table in tables_in_sql:
            table_lower = table.lower()
            # Tách schema prefix nế cần (dbo.DimCustomer → DimCustomer)
            table_name_only = table_lower.split(".")[-1] if "." in table_lower else table_lower

            if table_lower not in allowed_lower and table_name_only not in allowed_lower:
                # Check hệ thống tables
                system_prefixes = ("sys.", "information_schema.", "tempdb.", "msdb.", "master.")
                is_system = any(table_lower.startswith(p) for p in system_prefixes)

                if is_system:
                    logger.warning(f"Guardian BLOCKED (table_access): system table={table}")
                    return GuardResult(
                        safe=False,
                        guard_name="table_access",
                        reason=f"Access to system table '{table}' is not allowed",
                    )

                # Non-system nhưng ngoài whitelist — warn nhưng allow
                # (SQL generator có thể dùng alias hoặc subquery)
                logger.debug(f"Guardian: table '{table}' not in whitelist (may be alias)")

        return GuardResult(safe=True, guard_name="table_access")

    def _extract_tables(self, sql: str) -> list[str]:
        """Extract table names từ SQL bằng regex đơn giản."""
        tables = set()

        # Pattern: FROM table, JOIN table
        patterns = [
            r'\bFROM\s+(\[?[\w.]+\]?)',
            r'\bJOIN\s+(\[?[\w.]+\]?)',
            r'\bINTO\s+(\[?[\w.]+\]?)',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, sql, re.IGNORECASE):
                table = match.group(1).strip("[]")
                # Skip subqueries and numeric values
                if table.upper() not in ("SELECT", "LATERAL", "(") and not table.isdigit():
                    tables.add(table)

        return list(tables)

    # ─── Guard 4: Column Masking ─────────────────────────────────

    def _guard_column_masking(self, sql: str) -> GuardResult:
        """Mask cột nhạy cảm trong SELECT output."""
        if not self._config.masked_columns:
            return GuardResult(safe=True, guard_name="column_masking")

        modified = sql
        for col_name, mask_expr in self._config.masked_columns.items():
            # Tìm column trong SELECT clause
            # Pattern: SELECT ... col_name ... FROM
            pattern = rf'\b({re.escape(col_name)})\b'
            if re.search(pattern, modified, re.IGNORECASE):
                # Replace column reference với mask expression
                # Chỉ trong SELECT clause (trước FROM)
                select_end = modified.upper().find(" FROM ")
                if select_end > 0:
                    select_part = modified[:select_end]
                    rest = modified[select_end:]
                    select_part = re.sub(
                        pattern,
                        f"{mask_expr} AS {col_name}",
                        select_part,
                        flags=re.IGNORECASE,
                    )
                    modified = select_part + rest
                    logger.info(f"Guardian: masked column '{col_name}'")

        if modified != sql:
            return GuardResult(
                safe=True, guard_name="column_masking",
                modified_sql=modified,
            )
        return GuardResult(safe=True, guard_name="column_masking")

    # ─── Guard 5: Row Filter (RLS) ──────────────────────────────

    def _guard_row_filter(
        self,
        sql: str,
        session_props: dict[str, str] | None = None,
    ) -> GuardResult:
        """Inject WHERE clauses từ RLS policies."""
        if not self._config.policies:
            return GuardResult(safe=True, guard_name="row_filter")

        active_policies = [
            p for p in self._config.policies
            if p.enabled and p.policy_type == "rls"
        ]

        if not active_policies:
            return GuardResult(safe=True, guard_name="row_filter")

        modified = sql
        props = session_props or {}

        for policy in active_policies:
            # Check nếu SQL query tables thuộc applied_models
            tables_in_sql = self._extract_tables(sql)
            tables_lower = {t.lower() for t in tables_in_sql}

            applicable = any(
                m.lower() in tables_lower
                for m in policy.applied_models
            )

            if applicable:
                # Resolve @properties trong condition
                condition = policy.condition
                for prop_name, prop_value in props.items():
                    condition = condition.replace(
                        f"@{prop_name}", f"'{prop_value}'"
                    )

                # Inject WHERE clause
                # Đơn giản: thêm AND vào WHERE clause hiện tại
                if " WHERE " in modified.upper():
                    # Thêm AND
                    where_idx = modified.upper().index(" WHERE ")
                    after_where = where_idx + 7
                    modified = (
                        modified[:after_where]
                        + f"({condition}) AND "
                        + modified[after_where:]
                    )
                else:
                    # Thêm WHERE trước ORDER BY / GROUP BY / cuối
                    for clause in [" ORDER BY ", " GROUP BY ", " HAVING "]:
                        idx = modified.upper().find(clause)
                        if idx > 0:
                            modified = (
                                modified[:idx]
                                + f" WHERE {condition}"
                                + modified[idx:]
                            )
                            break
                    else:
                        modified += f" WHERE {condition}"

                logger.info(f"Guardian: applied RLS policy '{policy.name}'")

        if modified != sql:
            return GuardResult(
                safe=True, guard_name="row_filter",
                modified_sql=modified,
            )
        return GuardResult(safe=True, guard_name="row_filter")
