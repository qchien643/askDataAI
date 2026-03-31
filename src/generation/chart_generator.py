"""
Chart Generator — Sinh Vega-Lite chart schema từ SQL query results.

Luồng:
  question + sql + columns + rows → preprocess → LLM → Vega-Lite JSON

Hỗ trợ 7 loại chart:
  bar, grouped_bar, stacked_bar, line, multi_line, area, pie

Inspired by WrenAI chart_generation pipeline.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from src.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ChartResult:
    """Kết quả chart generation."""
    reasoning: str = ""
    chart_type: str = ""  # bar | grouped_bar | stacked_bar | line | multi_line | area | pie | ""
    chart_schema: dict = field(default_factory=dict)
    error: str = ""


CHART_SYSTEM_PROMPT = """Bạn là chuyên gia data visualization sử dụng Vega-Lite.
Cho trước câu hỏi, SQL query, và sample data, hãy sinh Vega-Lite schema phù hợp.

### CHART TYPES ###
- bar: So sánh categories (1 categorical x, 1 quantitative y)
- grouped_bar: So sánh sub-categories (2 categorical, 1 quantitative). Dùng xOffset, KHÔNG dùng stack.
- stacked_bar: Composition trong categories. Dùng "stack": "zero" trong y-encoding.
- line: Trend theo thời gian (1 temporal/ordinal x, 1 quantitative y)
- multi_line: Nhiều metrics theo thời gian. Dùng transform fold.
- area: Volume theo thời gian (giống line nhưng mark area)
- pie: Tỷ lệ phần trăm. Dùng mark "arc", theta encoding, color encoding. KHÔNG dùng innerRadius.

### QUY TẮC ###
1. Chỉ dùng các column names có trong data
2. Nếu x-axis là temporal:
   - Yearly → timeUnit: "year"
   - Monthly → timeUnit: "yearmonth"
   - Daily → timeUnit: "yearmonthdate"
3. Mỗi axis phải có title tiếng Việt dễ hiểu
4. Title chart phải mô tả nội dung bằng tiếng Việt
5. Nếu data không phù hợp để vẽ chart → trả chart_type = "" và chart_schema = {}
6. Nếu chỉ có 1 row → dùng bar chart
7. Nếu có cột thời gian → ưu tiên line/area chart
8. Nếu có nhiều categories (>7) → cân nhắc top N hoặc bar chart ngang

### VÍ DỤ OUTPUT ###

Bar chart:
{
    "title": "Doanh thu theo khu vực",
    "mark": {"type": "bar"},
    "encoding": {
        "x": {"field": "Region", "type": "nominal", "title": "Khu vực"},
        "y": {"field": "Sales", "type": "quantitative", "title": "Doanh thu"},
        "color": {"field": "Region", "type": "nominal", "title": "Khu vực"}
    }
}

Line chart:
{
    "title": "Xu hướng doanh thu theo tháng",
    "mark": {"type": "line"},
    "encoding": {
        "x": {"field": "Date", "type": "temporal", "timeUnit": "yearmonth", "title": "Tháng"},
        "y": {"field": "Sales", "type": "quantitative", "title": "Doanh thu"}
    }
}

Pie chart:
{
    "title": "Tỷ lệ doanh thu",
    "mark": {"type": "arc"},
    "encoding": {
        "theta": {"field": "Sales", "type": "quantitative"},
        "color": {"field": "Category", "type": "nominal", "title": "Danh mục"}
    }
}

### OUTPUT FORMAT (JSON) ###
{
    "reasoning": "<giải thích ngắn gọn bằng tiếng Việt>",
    "chart_type": "bar" | "grouped_bar" | "stacked_bar" | "line" | "multi_line" | "area" | "pie" | "",
    "chart_schema": <VEGA_LITE_JSON hoặc {}>
}"""


CHART_USER_PROMPT = """### CÂU HỎI ###
{question}

### SQL ###
{sql}

### SAMPLE DATA (tối đa 15 rows) ###
{sample_data}

### COLUMNS & SAMPLE VALUES ###
{column_info}

Hãy sinh Vega-Lite chart schema phù hợp nhất."""


class ChartGenerator:
    """Sinh Vega-Lite chart schema từ query results."""

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
        Sinh chart từ query results.

        Args:
            question: Câu hỏi user.
            sql: SQL đã thực thi.
            columns: Column names.
            rows: Data rows (list of dicts).

        Returns:
            ChartResult với chart_schema (Vega-Lite JSON).
        """
        if not rows or not columns:
            return ChartResult(
                reasoning="Không có dữ liệu để tạo biểu đồ.",
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
