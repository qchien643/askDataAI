"""
Chart Generator — Generate Vega-Lite chart schema from SQL query results.

Flow:
  question + sql + columns + rows → preprocess → LLM → Vega-Lite JSON

Supports 7 chart types:
  bar, grouped_bar, stacked_bar, line, multi_line, area, pie

Inspired by WrenAI chart_generation pipeline.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ChartResult:
    """Chart generation result."""
    reasoning: str = ""
    chart_type: str = ""  # bar | grouped_bar | stacked_bar | line | multi_line | area | pie | ""
    chart_schema: dict = field(default_factory=dict)
    error: str = ""


CHART_SYSTEM_PROMPT = """You are a data visualization expert using Vega-Lite.
Given a question, SQL query, and sample data, generate the most appropriate Vega-Lite schema.

### CHART TYPES ###
- bar: Compare categories (1 categorical x, 1 quantitative y)
- grouped_bar: Compare sub-categories (2 categorical, 1 quantitative). Use xOffset, NOT stack.
- stacked_bar: Composition within categories. Use "stack": "zero" in y-encoding.
- line: Trend over time (1 temporal/ordinal x, 1 quantitative y)
- multi_line: Multiple metrics over time. Use transform fold.
- area: Volume over time (like line but mark area)
- pie: Percentages. Use mark "arc", theta encoding, color encoding. DO NOT use innerRadius.

### RULES ###
1. Only use column names present in the data
2. If x-axis is temporal:
   - Yearly → timeUnit: "year"
   - Monthly → timeUnit: "yearmonth"
   - Daily → timeUnit: "yearmonthdate"
3. Each axis must have a clear, descriptive title
4. Chart title must describe the content concisely
5. If data is not suitable for a chart → return chart_type = "" and chart_schema = {}
6. If only 1 row → use bar chart
7. If there is a date/time column → prefer line/area chart
8. If many categories (>7) → consider top N or horizontal bar chart

### EXAMPLE OUTPUT ###

Bar chart:
{
    "title": "Revenue by Region",
    "mark": {"type": "bar"},
    "encoding": {
        "x": {"field": "Region", "type": "nominal", "title": "Region"},
        "y": {"field": "Sales", "type": "quantitative", "title": "Revenue"},
        "color": {"field": "Region", "type": "nominal", "title": "Region"}
    }
}

Line chart:
{
    "title": "Revenue Trend by Month",
    "mark": {"type": "line"},
    "encoding": {
        "x": {"field": "Date", "type": "temporal", "timeUnit": "yearmonth", "title": "Month"},
        "y": {"field": "Sales", "type": "quantitative", "title": "Revenue"}
    }
}

Pie chart:
{
    "title": "Revenue Share",
    "mark": {"type": "arc"},
    "encoding": {
        "theta": {"field": "Sales", "type": "quantitative"},
        "color": {"field": "Category", "type": "nominal", "title": "Category"}
    }
}

### OUTPUT FORMAT (JSON) ###
{
    "reasoning": "<brief explanation>",
    "chart_type": "bar" | "grouped_bar" | "stacked_bar" | "line" | "multi_line" | "area" | "pie" | "",
    "chart_schema": <VEGA_LITE_JSON or {}>
}"""


CHART_USER_PROMPT = """### QUESTION ###
{question}

### SQL ###
{sql}

### SAMPLE DATA (max 15 rows) ###
{sample_data}

### COLUMNS & SAMPLE VALUES ###
{column_info}

Generate the most appropriate Vega-Lite chart schema."""


class ChartGenerator:
    """Generate Vega-Lite chart schema from query results."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def generate(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> ChartResult:
        """
        Generate chart from query results.

        Args:
            question: User question.
            sql: Executed SQL query.
            columns: Column names.
            rows: Data rows (list of dicts).

        Returns:
            ChartResult with chart_schema (Vega-Lite JSON).
        """
        if not rows or not columns:
            return ChartResult(
                reasoning="No data available to generate a chart.",
                error="No data available",
            )

        # Preprocess: sample data + column info
        sample_data = rows[:15]
        column_info = self._build_column_info(columns, rows)

        user_prompt = CHART_USER_PROMPT.format(
            question=question,
            sql=sql,
            sample_data=str(sample_data),
            column_info=column_info,
        )

        try:
            result = self._llm.chat_json(
                user_prompt=user_prompt,
                system_prompt=CHART_SYSTEM_PROMPT,
            )

            reasoning = result.get("reasoning", "")
            chart_type = result.get("chart_type", "")
            chart_schema = result.get("chart_schema", {})

            # Ensure chart_schema is a dict
            if isinstance(chart_schema, str):
                import json
                try:
                    chart_schema = json.loads(chart_schema)
                except (json.JSONDecodeError, ValueError):
                    chart_schema = {}

            # Inject Vega-Lite $schema
            if chart_schema:
                chart_schema["$schema"] = "https://vega.github.io/schema/vega-lite/v5.json"

            logger.info(f"Chart generated: type={chart_type}, has_schema={bool(chart_schema)}")

            return ChartResult(
                reasoning=reasoning,
                chart_type=chart_type,
                chart_schema=chart_schema,
            )

        except Exception as e:
            logger.error(f"Chart generation failed: {e}", exc_info=True)
            return ChartResult(
                reasoning="",
                error=str(e),
            )

    @staticmethod
    def _build_column_info(
        columns: list[str],
        rows: list[dict[str, Any]],
        sample_values: int = 5,
    ) -> str:
        """Build column info with sample unique values."""
        parts = []
        for col in columns:
            values = list({str(row.get(col, "")) for row in rows})[:sample_values]
            # Detect type heuristic
            col_type = "text"
            sample = [row.get(col) for row in rows[:10] if row.get(col) is not None]
            if sample:
                if all(isinstance(v, (int, float)) for v in sample):
                    col_type = "numeric"
                elif any(
                    isinstance(v, str) and any(
                        kw in v for kw in ["-", "/", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]
                    )
                    for v in sample
                ):
                    col_type = "temporal"

            parts.append(f"- {col} ({col_type}): {values}")

        return "\n".join(parts)
