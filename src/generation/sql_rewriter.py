"""
SQL Rewriter - Convert model names → DB names trong SQL.

LLM sinh SQL dùng model names (vd: customers, internet_sales).
SQL Rewriter convert sang tên DB thật (vd: dbo.DimCustomer, dbo.FactInternetSales).

Trong WrenAI gốc: wren-engine/ibis-server/app/mdl/rewriter.py (Rust engine).
Mình implement đơn giản hơn bằng sqlparse + string replacement.
"""

import logging
import re

from src.modeling.mdl_schema import Manifest

logger = logging.getLogger(__name__)


class SQLRewriter:
    """
    Convert model names → DB table names trong SQL query.

    LLM sinh: SELECT customers.FirstName FROM customers
    Rewrite:  SELECT [dbo].[DimCustomer].FirstName FROM [dbo].[DimCustomer]
    """

    def __init__(self, manifest: Manifest):
        self._manifest = manifest
        # Build mapping: model_name → table_reference
        self._table_map = {
            m.name: m.table_reference
            for m in manifest.models
        }
        logger.info(
            f"SQLRewriter initialized: {len(self._table_map)} model mappings"
        )

    def rewrite(self, sql: str) -> str:
        """
        Rewrite SQL: thay model names → DB table names.

        Args:
            sql: SQL query dùng model names.

        Returns:
            SQL query dùng DB table names thật.
        """
        if not sql:
            return sql

        rewritten = sql

        # Sort by name length descending để tránh partial replacement
        # (vd: "product_subcategories" phải replace trước "products")
        sorted_names = sorted(
            self._table_map.keys(),
            key=len,
            reverse=True,
        )

        for model_name in sorted_names:
            table_ref = self._table_map[model_name]

            # Bracket tên DB: dbo.DimCustomer → [dbo].[DimCustomer]
            bracketed = self._bracket_name(table_ref)

            # Replace pattern: model_name as word boundary
            # Cần cẩn thận: thay cả khi nó xuất hiện trong:
            # - FROM customers
            # - JOIN customers
            # - customers.ColumnName
            # - "customers" (quoted)
            pattern = re.compile(
                r'(?<![.\w])' + re.escape(model_name) + r'(?![.\w])',
                re.IGNORECASE,
            )
            rewritten = pattern.sub(bracketed, rewritten)

        logger.info(f"SQL rewritten: {len(sql)} → {len(rewritten)} chars")
        return rewritten

    @staticmethod
    def _bracket_name(table_ref: str) -> str:
        """
        Bracket DB name: dbo.DimCustomer → [dbo].[DimCustomer]
        """
        parts = table_ref.split(".")
        return ".".join(f"[{p}]" for p in parts)

    def get_mapping(self) -> dict[str, str]:
        """Trả về mapping model_name → table_reference."""
        return dict(self._table_map)
