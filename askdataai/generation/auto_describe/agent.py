"""
Description Agent — LangChain ReAct agent for table-level description generation.

Uses LangGraph's create_react_agent to orchestrate a table-level ReAct loop
with 3 tools (search_similar_descriptions, get_column_stats, get_table_relationships).

The agent receives all empty columns for ONE table, gathers evidence via tools,
then outputs structured JSON descriptions for all columns at once.

Framework: LangChain + LangGraph
"""

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from askdataai.generation.auto_describe.prompts import TABLE_AGENT_SYSTEM, TABLE_AGENT_USER
from askdataai.generation.auto_describe.tools import create_tools

logger = logging.getLogger(__name__)


class DescAgent:
    """
    Table-level ReAct agent for column description generation.

    One agent session per table. The agent:
    1. Searches similar descriptions for style reference
    2. Gets column stats for evidence
    3. Checks relationships for FK context
    4. Generates all descriptions in one structured output

    Usage:
        agent = DescAgent(api_key, base_url, model, indexer, profile_cache, manifest)
        result = await agent.generate_for_table(table_name, columns, context)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4.1-mini",
        temperature: float = 0.1,
        max_tool_calls: int = 4,
        indexer=None,
        profile_cache: dict[str, Any] | None = None,
        manifest=None,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._max_tool_calls = max_tool_calls
        self._indexer = indexer
        self._profile_cache = profile_cache or {}
        self._manifest = manifest

    async def generate_for_table(
        self,
        table_name: str,
        empty_columns: list[dict],
        classifications: dict[str, dict],
        style_guide: dict,
        domain_info: dict,
        table_description: str = "",
        primary_key: str | None = None,
        existing_described: list[dict] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Generate descriptions for all empty columns in a table.

        Args:
            table_name: Model name
            empty_columns: List of column dicts: [{"name": ..., "type": ...}]
            classifications: Dict from TypeEngine: col_name -> {"category": ...}
            style_guide: Style guide dict from Phase 1
            domain_info: Domain understanding from Phase 1
            table_description: Existing table description
            primary_key: Primary key column name
            existing_described: Already-described columns for context

        Returns:
            Dict mapping column_name -> {
                "description": str,
                "enum_values": list[str],
                "category": str,
                "confidence": float
            }
        """
        # Create tools bound to current infrastructure
        tools = create_tools(
            indexer=self._indexer,
            profile_cache=self._profile_cache,
            manifest=self._manifest,
        )

        # Create LLM
        llm = ChatOpenAI(
            model=self._model,
            api_key=self._api_key,
            base_url=self._base_url,
            temperature=self._temperature,
        )

        # Create ReAct agent (LangGraph handles the tool-calling loop)
        agent = create_react_agent(
            llm,
            tools=tools,
        )

        # Build system prompt
        style_guide_str = json.dumps(style_guide, ensure_ascii=False, indent=2)

        # Dynamic style examples from the actual style guide (NOT hard-coded)
        sg_examples = style_guide.get("examples", [])
        if sg_examples:
            style_examples = "\n".join(f'- "{ex}"' for ex in sg_examples[:5])
        else:
            # Fallback: use existing described columns from this table
            style_examples = "\n".join(
                f'- "{c.get("description", "")}"'
                for c in (existing_described or [])[:5]
                if c.get("description")
            ) or '- "Short, concise description without any prefix"'

        # Dynamic anti-prefix examples using actual column names (NOT hard-coded)
        sample_cols = empty_columns[:3]
        anti_examples = []
        for c in sample_cols:
            anti_examples.append(
                f'- "[{table_name}.{c["name"]}] ({c["type"]}): some description"'
            )
        if not anti_examples:
            anti_examples = ['- "[table.column] (type): some description"']
        anti_prefix_examples = "\n".join(anti_examples)

        system_prompt = TABLE_AGENT_SYSTEM.format(
            domain=domain_info.get("domain", "unknown"),
            table_name=table_name,
            table_description=table_description or "No description",
            style_guide=style_guide_str,
            style_examples=style_examples,
            anti_prefix_examples=anti_prefix_examples,
        )

        # Build user prompt
        columns_info = "\n".join(
            f"  - {c['name']} ({c['type']})"
            for c in empty_columns
        )

        class_info = "\n".join(
            f"  - {name}: {info.get('category', 'TEXT')} "
            f"(confidence: {info.get('confidence', 0):.0%}, {info.get('reason', '')})"
            for name, info in classifications.items()
        )

        existing_str = "None"
        if existing_described:
            existing_str = "\n".join(
                f"  - {c['name']}: {c.get('description', '')[:80]}"
                for c in existing_described[:10]  # Limit to 10 for context
            )

        user_prompt = TABLE_AGENT_USER.format(
            table_name=table_name,
            columns_info=columns_info,
            classifications=class_info,
            table_description=table_description or "No description",
            primary_key=primary_key or "N/A",
            existing_described=existing_str,
        )

        # Run agent
        logger.info(
            f"Starting agent for {table_name} "
            f"({len(empty_columns)} columns, max {self._max_tool_calls} tool calls)"
        )

        # Scale recursion limit based on column count
        # Agent makes ~2 tool calls (search + stats) per column + relationship lookups
        # Each tool call = 2 graph steps (call + response), plus final output
        n_cols = len(empty_columns)
        recursion_limit = n_cols * 3 + 20  # e.g., 21 cols → 83, 13 cols → 59

        try:
            result = await agent.ainvoke(
                {
                    "messages": [
                        ("system", system_prompt),
                        ("user", user_prompt),
                    ]
                },
                config={
                    "recursion_limit": recursion_limit,
                },
            )

            # Extract final message content
            last_message = result["messages"][-1]
            content = last_message.content if hasattr(last_message, 'content') else str(last_message)

            # Parse JSON from response
            descriptions = self._parse_response(content)

            logger.info(
                f"Agent completed for {table_name}: "
                f"{len(descriptions)} descriptions generated"
            )
            return descriptions

        except Exception as e:
            logger.error(f"Agent failed for {table_name}: {e}")
            return {}

    def _parse_response(self, content: str) -> dict[str, dict[str, Any]]:
        """Parse agent response to extract descriptions dict."""
        # Try direct JSON parse
        try:
            data = json.loads(content)
            if "descriptions" in data:
                return self._clean_descriptions(data["descriptions"])
            return self._clean_descriptions(data)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        import re
        json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if "descriptions" in data:
                    return self._clean_descriptions(data["descriptions"])
                return self._clean_descriptions(data)
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse agent response: {content[:200]}")
        return {}

    def _clean_descriptions(self, descriptions: dict) -> dict:
        """Post-process descriptions to strip unwanted prefixes.

        The LLM sometimes outputs descriptions like:
          '[table.col] (type): actual description'
        This method strips those prefixes to return clean description text.
        """
        import re
        # Pattern: [anything] (anything): rest  OR  table.col (type): rest
        prefix_pattern = re.compile(
            r'^\[.*?\]\s*\(.*?\)\s*:\s*'  # [table.col] (type):
            r'|^[a-zA-Z_]+\.[a-zA-Z_]+\s*[-:]\s*'  # table.col: or table.col -
        )

        cleaned = {}
        for col_name, col_data in descriptions.items():
            if isinstance(col_data, dict) and "description" in col_data:
                raw = col_data["description"]
                col_data["description"] = prefix_pattern.sub('', raw).strip()
            elif isinstance(col_data, str):
                col_data = prefix_pattern.sub('', col_data).strip()
            cleaned[col_name] = col_data

        return cleaned

