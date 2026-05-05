"""
Security Policies — Dataclasses cho Guardian config.

Lấy ý tưởng từ WrenAI Data Security:
- RLS (Row-Level Security): filter rows bằng session properties
- CLS (Column-Level Security): mask/block cột nhạy cảm
- Table Access: whitelist bảng được phép truy vấn
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SecurityPolicy:
    """Một policy bảo mật (RLS hoặc CLS)."""
    name: str
    policy_type: str  # "rls" | "cls" | "table_access"
    condition: str    # SQL predicate, e.g. "org_id = @user_org_id"
    applied_models: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class GuardianConfig:
    """Toàn bộ config cho SQLGuardian."""

    # Guard 1: SQL Injection patterns (regex)
    blocked_patterns: list[str] = field(default_factory=list)

    # Guard 2: Read-only mode
    read_only: bool = True

    # Guard 3: Table whitelist (populated from manifest)
    allowed_tables: list[str] = field(default_factory=list)

    # Guard 4: Column masking rules
    masked_columns: dict[str, str] = field(default_factory=dict)

    # Guard 5: RLS/CLS policies
    policies: list[SecurityPolicy] = field(default_factory=list)

    # DML keywords to block in read-only mode
    blocked_dml: list[str] = field(default_factory=lambda: [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
        "TRUNCATE", "EXEC", "EXECUTE", "CREATE", "GRANT",
        "REVOKE", "MERGE", "xp_cmdshell", "sp_executesql",
    ])

    @classmethod
    def from_yaml(cls, path: str) -> "GuardianConfig":
        """Load config từ YAML file."""
        config_path = Path(path)
        if not config_path.exists():
            logger.warning(f"Guardian config not found: {path}, using defaults")
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        policies = []
        for p in data.get("rls_policies", []):
            policies.append(SecurityPolicy(
                name=p.get("name", "unnamed"),
                policy_type=p.get("type", "rls"),
                condition=p.get("condition", ""),
                applied_models=p.get("applied_models", []),
                enabled=p.get("enabled", True),
            ))

        default_dml = [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "TRUNCATE", "EXEC", "EXECUTE", "CREATE", "GRANT",
            "REVOKE", "MERGE", "xp_cmdshell", "sp_executesql",
        ]

        return cls(
            blocked_patterns=data.get("blocked_patterns", []),
            read_only=data.get("read_only", True),
            allowed_tables=data.get("allowed_tables", []),
            masked_columns=data.get("masked_columns", {}),
            policies=policies,
            blocked_dml=data.get("blocked_dml", default_dml),
        )

    def set_allowed_tables_from_manifest(self, manifest: Any) -> None:
        """Auto-populate allowed tables từ manifest models."""
        if hasattr(manifest, "models"):
            self.allowed_tables = []
            for model in manifest.models:
                self.allowed_tables.append(model.name.lower())
                if hasattr(model, "table_reference") and model.table_reference:
                    # Thêm cả schema.table (dbo.DimCustomer)
                    ref = model.table_reference.lower()
                    self.allowed_tables.append(ref)
                    # Thêm chỉ table name (DimCustomer)
                    parts = ref.split(".")
                    if len(parts) > 1:
                        self.allowed_tables.append(parts[-1])

            logger.info(
                f"Guardian: allowed {len(self.allowed_tables)} table references"
            )
