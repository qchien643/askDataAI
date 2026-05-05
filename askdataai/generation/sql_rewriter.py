"""
SQL Rewriter - Convert model names → DB names in SQL.

LLM generates SQL using model names (e.g. customers, internet_sales).
SQL Rewriter converts to real DB names (e.g. dbo.DimCustomer, dbo.FactInternetSales).

In original WrenAI: wren-engine/ibis-server/app/mdl/rewriter.py (Rust engine).
This implementation uses sqlparse + string replacement for simplicity.
"""

import logging
import re

from askdataai.modeling.mdl_schema import Manifest

logger = logging.getLogger(__name__)


class SQLRewriter:
    """
    Convert model names → DB table names in SQL query.

    LLM generates: SELECT customers.FirstName FROM customers
    Rewritten:     SELECT [dbo].[DimCustomer].FirstName FROM [dbo].[DimCustomer]
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
        Rewrite SQL: replace model names → DB table names.

        Args:
            sql: SQL query using model names.

        Returns:
            SQL query using real DB table names.
        """
        if not sql:
            return sql

        rewritten = sql

        # Sort by name length descending to prevent partial replacement
        # (e.g. "product_subcategories" must be replaced before "products")
        sorted_names = sorted(
            self._table_map.keys(),
            key=len,
            reverse=True,
        )

        for model_name in sorted_names:
            table_ref = self._table_map[model_name]

            # Bracket DB name: dbo.DimCustomer → [dbo].[DimCustomer]
            bracketed = self._bracket_name(table_ref)

            # Replace pattern: model_name as word boundary
            # Handles all contexts: FROM customers, JOIN customers,
            # customers.ColumnName, "customers" (quoted)
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
        """Return mapping of model_name → table_reference."""
        return dict(self._table_map)
