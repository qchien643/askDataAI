"""
Schema Profiler — Batch SQL profiling for column statistics.

Queries the database to collect real statistics for columns that need
AI-generated descriptions. Used by the XiYan pipeline (Phase 2) to
provide evidence-based data to the description agent.

Reuses: SQLServerConnector.execute() for all SQL queries.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from askdataai.connectors.connection import SQLServerConnector

logger = logging.getLogger(__name__)


@dataclass
class ColumnProfile:
    """Statistics for a single column."""

    table_ref: str          # "dbo.DimProduct"
    column_name: str        # "Color"
    sql_type: str           # "NVARCHAR(15)"
    is_nullable: bool = True
    is_pk: bool = False
    total_count: int = 0
    non_null_count: int = 0
    null_rate: float = 0.0
    distinct_count: int = 0
    sample_values: list[Any] = field(default_factory=list)
    min_value: Any = None
    max_value: Any = None
    avg_value: float | None = None
    # Pre-existing metadata from models.yaml
    existing_enum_values: list[str] = field(default_factory=list)
    existing_description: str = ""

    def to_dict(self) -> dict:
        """Convert to dict for agent tool consumption."""
        return {
            "table": self.table_ref,
            "column": self.column_name,
            "sql_type": self.sql_type,
            "is_nullable": self.is_nullable,
            "is_pk": self.is_pk,
            "total_count": self.total_count,
            "non_null_count": self.non_null_count,
            "null_rate": f"{self.null_rate:.1f}%",
            "distinct_count": self.distinct_count,
            "sample_values": self.sample_values[:15],
            "min": self.min_value,
            "max": self.max_value,
            "avg": self.avg_value,
            "existing_enum_values": self.existing_enum_values,
            "existing_description": self.existing_description,
        }


class SchemaProfiler:
    """
    Batch SQL profiler for column statistics.

    Generates COUNT, DISTINCT, MIN/MAX, sample values for columns
    that need AI-generated descriptions.

    Usage:
        profiler = SchemaProfiler(connector)
        profiles = profiler.profile_table("dbo.DimProduct", ["Color", "Size", "ListPrice"])
        cache = profiler.profile_all_empty(manifest)
    """

    def __init__(
        self,
        connector: SQLServerConnector,
        sample_limit: int = 20,
        query_timeout: int = 10,
    ):
        self._connector = connector
        self._sample_limit = sample_limit
        self._query_timeout = query_timeout

    def profile_column(
        self,
        table_ref: str,
        column_name: str,
        sql_type: str = "unknown",
        is_pk: bool = False,
        existing_enum_values: list[str] | None = None,
        existing_description: str = "",
    ) -> ColumnProfile:
        """
        Profile a single column with batch SQL stats.

        Args:
            table_ref: Full table reference (e.g., "dbo.DimProduct")
            column_name: Column name
            sql_type: SQL data type
            is_pk: Whether column is primary key
            existing_enum_values: Pre-existing enum values from models.yaml
            existing_description: Pre-existing description

        Returns:
            ColumnProfile with statistics
        """
        profile = ColumnProfile(
            table_ref=table_ref,
            column_name=column_name,
            sql_type=sql_type,
            is_pk=is_pk,
            existing_enum_values=existing_enum_values or [],
            existing_description=existing_description,
        )

        # Skip profiling for PK columns (not useful for descriptions)
        if is_pk:
            return profile

        try:
            # Single query for basic stats: count, non-null, distinct, min, max, avg
            stats = self._query_basic_stats(table_ref, column_name)
            profile.total_count = stats.get("total_count", 0)
            profile.non_null_count = stats.get("non_null_count", 0)
            profile.distinct_count = stats.get("distinct_count", 0)
            profile.min_value = stats.get("min_val")
            profile.max_value = stats.get("max_val")
            profile.avg_value = stats.get("avg_val")

            if profile.total_count > 0:
                null_count = profile.total_count - profile.non_null_count
                profile.null_rate = (null_count / profile.total_count) * 100
                profile.is_nullable = null_count > 0

            # Sample values (only if not too many distinct values or is categorical)
            if profile.distinct_count <= 50:
                profile.sample_values = self._query_sample_values(
                    table_ref, column_name
                )

        except Exception as e:
            logger.warning(
                f"Failed to profile {table_ref}.{column_name}: {e}"
            )

        return profile

    def profile_table(
        self,
        table_ref: str,
        columns: list[dict],
        primary_key: str | None = None,
    ) -> dict[str, ColumnProfile]:
        """
        Profile all specified columns in a table.

        Args:
            table_ref: Full table reference
            columns: List of column dicts with keys: name, type, enum_values, description
            primary_key: Primary key column name

        Returns:
            Dict mapping "table_ref.column_name" -> ColumnProfile
        """
        profiles: dict[str, ColumnProfile] = {}

        for col in columns:
            col_name = col["name"]
            key = f"{table_ref}.{col_name}"

            profile = self.profile_column(
                table_ref=table_ref,
                column_name=col_name,
                sql_type=col.get("type", "unknown"),
                is_pk=(col_name == primary_key),
                existing_enum_values=col.get("enum_values", []),
                existing_description=col.get("description", ""),
            )
            profiles[key] = profile

        logger.info(
            f"Profiled {len(profiles)} columns in {table_ref}"
        )
        return profiles

    def profile_all_empty(self, manifest) -> dict[str, ColumnProfile]:
        """
        Profile all columns with empty descriptions across all models.

        Args:
            manifest: Manifest object from ManifestBuilder

        Returns:
            Dict mapping "table_ref.column_name" -> ColumnProfile
            for all columns needing descriptions.
        """
        all_profiles: dict[str, ColumnProfile] = {}

        for model in manifest.models:
            # Collect columns that need descriptions
            empty_cols = [
                {
                    "name": col.name,
                    "type": col.type,
                    "enum_values": col.enum_values,
                    "description": col.description,
                }
                for col in model.columns
                if not col.description.strip()
            ]

            if not empty_cols:
                logger.info(f"Skipping {model.name}: all columns described")
                continue

            table_profiles = self.profile_table(
                table_ref=model.table_reference,
                columns=empty_cols,
                primary_key=model.primary_key,
            )
            all_profiles.update(table_profiles)

        logger.info(
            f"Total profiled: {len(all_profiles)} empty columns "
            f"across {len(manifest.models)} models"
        )
        return all_profiles

    # ─── Private SQL Methods ────────────────────────────────────────

    def _query_basic_stats(
        self, table_ref: str, column_name: str
    ) -> dict[str, Any]:
        """Single query for count, distinct, min, max, avg."""
        # Use CASE to skip AVG for date/datetime types that fail FLOAT cast
        sql = f"""
            SELECT
                COUNT(*) AS total_count,
                COUNT([{column_name}]) AS non_null_count,
                COUNT(DISTINCT [{column_name}]) AS distinct_count,
                MIN(CAST([{column_name}] AS NVARCHAR(200))) AS min_val,
                MAX(CAST([{column_name}] AS NVARCHAR(200))) AS max_val
            FROM {table_ref}
        """
        try:
            rows = self._connector.execute(sql, timeout=self._query_timeout)
            result = rows[0] if rows else {}

            # Try AVG separately (fails for date/datetime/binary columns)
            try:
                avg_sql = f"""
                    SELECT AVG(TRY_CAST([{column_name}] AS FLOAT)) AS avg_val
                    FROM {table_ref}
                """
                avg_rows = self._connector.execute(avg_sql, timeout=self._query_timeout)
                if avg_rows:
                    result["avg_val"] = avg_rows[0].get("avg_val")
            except Exception:
                result["avg_val"] = None

            return result
        except Exception as e:
            logger.warning(f"Stats query failed for {table_ref}.{column_name}: {e}")
            return {}

    def _query_sample_values(
        self, table_ref: str, column_name: str
    ) -> list[Any]:
        """Get distinct sample values (up to sample_limit)."""
        sql = f"""
            SELECT DISTINCT TOP {self._sample_limit}
                [{column_name}]
            FROM {table_ref}
            WHERE [{column_name}] IS NOT NULL
            ORDER BY [{column_name}]
        """
        try:
            rows = self._connector.execute(sql, timeout=self._query_timeout)
            return [row[column_name] for row in rows]
        except Exception as e:
            logger.warning(f"Sample query failed for {table_ref}.{column_name}: {e}")
            return []
