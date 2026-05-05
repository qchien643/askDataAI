"""
Description Tools — LangChain @tool definitions for the XiYan agent.

Three tools that the table-level ReAct agent can call:
1. search_similar_descriptions — Few-shot retrieval from ChromaDB
2. get_column_stats — SQL profiling results from cache
3. get_table_relationships — FK relationship info from Manifest

These are factory functions that create tool instances bound to specific
infrastructure (indexer, profile cache, manifest).
"""

import json
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def create_tools(
    indexer,
    profile_cache: dict[str, Any],
    manifest,
) -> list:
    """
    Create LangChain tool instances bound to the pipeline infrastructure.

    Args:
        indexer: DescriptionIndexer instance (ChromaDB search)
        profile_cache: Dict mapping "table_ref.column" -> ColumnProfile
        manifest: Manifest object for relationship queries

    Returns:
        List of LangChain tool callables
    """

    @tool
    def search_similar_descriptions(
        query: str,
        n: int = 3,
        category: str | None = None,
    ) -> str:
        """Search existing human-written column descriptions for similar columns.

        Use this to learn the user's writing style and format conventions before
        writing new descriptions. Always call this at least once per table.

        Args:
            query: Natural language describing the column type you need examples for.
                   Good: "enum string column with categorical values like status or type"
                   Bad:  "column"
            n: Number of results to return (1-5, default 3)
            category: Optional filter: ENUM, MEASURE, CODE, TEXT, DATE, FK

        Returns:
            JSON string with matching descriptions and similarity scores.
        """
        try:
            results = indexer.search(query=query, n=n, category=category)
            return json.dumps(results, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"search_similar_descriptions failed: {e}")
            return json.dumps({"error": str(e)})

    @tool
    def get_column_stats(table: str, column: str) -> str:
        """Get real statistics from the database for a specific column.

        Use this when you need evidence-based data to write accurate descriptions:
        - Value range (min/max) for numeric columns
        - Null rate to mention nullable fields
        - Distinct count to determine if column is categorical
        - Sample values to list in enum descriptions

        NOTE: If existing_enum_values are returned, those are pre-validated
        values from the existing schema -- use them directly.

        Args:
            table: Table reference (e.g., "dbo.DimProduct")
            column: Column name (e.g., "Color")

        Returns:
            JSON string with column statistics.
        """
        # Look up in the pre-built profile cache
        key = f"{table}.{column}"
        profile = profile_cache.get(key)

        if profile is None:
            # Try matching by column name only (if table ref format differs)
            for k, v in profile_cache.items():
                if k.endswith(f".{column}"):
                    profile = v
                    break

        if profile is None:
            return json.dumps({
                "error": f"No profile found for {key}. "
                         f"Available: {list(profile_cache.keys())[:5]}..."
            })

        data = profile.to_dict() if hasattr(profile, 'to_dict') else profile
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    @tool
    def get_table_relationships(table: str) -> str:
        """Get foreign key relationships for a table from the semantic model.

        Use this to identify which columns are foreign keys and what tables
        they reference. Essential for writing FK descriptions.

        Args:
            table: Model name as defined in models.yaml (e.g., "internet_sales")

        Returns:
            JSON string with list of relationships.
        """
        try:
            rels = manifest.get_relationships_for(table)
            result = [
                {
                    "name": r.name,
                    "from": r.model_from,
                    "to": r.model_to,
                    "join_type": r.join_type.value if hasattr(r.join_type, 'value') else str(r.join_type),
                    "condition": r.condition,
                }
                for r in rels
            ]
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"get_table_relationships failed: {e}")
            return json.dumps({"error": str(e)})

    return [search_similar_descriptions, get_column_stats, get_table_relationships]
