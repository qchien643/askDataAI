"""
SQL Generator - Sinh SQL từ câu hỏi + DDL context.

System prompt tối ưu cho T-SQL (SQL Server):
- TOP thay LIMIT
- GETDATE() thay NOW()
- ISNULL thay COALESCE
- Anti-hallucination rules

Tương đương SQLGeneration trong WrenAI gốc
(wren-ai-service/src/pipelines/generation/sql_generation.py).
"""

import logging
from dataclasses import dataclass

from src.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class SQLGenerationResult:
    sql: str
    explanation: str = ""
    raw_response: dict | None = None


SQL_GENERATION_SYSTEM_PROMPT = """Bạn là chuyên gia T-SQL cho Microsoft SQL Server. Nhiệm vụ: sinh SQL query từ câu hỏi tự nhiên.

### QUY TẮC SQL SERVER ###
- Dùng TOP thay cho LIMIT. Ví dụ: SELECT TOP 10 * FROM ...
- Dùng GETDATE() thay cho NOW()
- Dùng ISNULL() thay cho COALESCE() khi chỉ 2 tham số
- Dùng CONVERT() hoặc CAST() cho type conversion
- String concatenation: dùng + thay cho ||
- Dùng [tên] hoặc "tên" cho tên có ký tự đặc biệt
- Date format: dùng CONVERT(VARCHAR, date_col, format_code) thay cho TO_CHAR()
- KHÔNG DÙNG DECLARE @variable — inline giá trị trực tiếp vào query

### QUY TẮC CHỐNG HALLUCINATE ###
- CHỈ SỬ DỤNG tables và columns có trong DATABASE SCHEMA bên dưới
- KHÔNG BỊA tên table hoặc column không tồn tại
- KHÔNG sử dụng DELETE, UPDATE, INSERT, DROP hoặc bất kỳ lệnh thay đổi dữ liệu
- CHỈ dùng SELECT statements
- Dùng alias trong comment (nếu có) để hiểu ý nghĩa column

### QUY TẮC JOIN ###
- BẮT BUỘC dùng JOIN khi query nhiều tables
- Ưu tiên dùng CTE (WITH) thay vì subqueries
- Dùng JOIN conditions từ phần Relationships trong schema

### QUY TẮC RANKING ###  
- Với bài toán xếp hạng (top X, bottom X), dùng DENSE_RANK() hoặc ROW_NUMBER()
- Thêm cột ranking vào SELECT cuối cùng

### QUY TẮC SO SÁNH CHUỖI ###
- Dùng LOWER(column) = LOWER(value) cho so sánh case-insensitive
- Dùng LIKE với % cho pattern matching

### QUY TẮC LOGIC QUAN TRỌNG ###
Khi câu hỏi yêu cầu "TOP N <entity> kèm thông tin chi tiết <detail>":
1. CTE bước 1: Tìm TOP N <entity> DISTINCT dựa trên metric (GROUP BY entity key, ORDER BY metric DESC)
2. Final SELECT: JOIN kết quả CTE với tables chứa thông tin <detail>
3. TUYỆT ĐỐI KHÔNG: SELECT TOP N entity, detail FROM ... GROUP BY entity, detail
   → Điều này sẽ cho CÙNG entity lặp lại với các detail khác nhau!

SAI: SELECT TOP 10 ProductName, City FROM ... GROUP BY ProductName, City
→ Kết quả: 1 sản phẩm × 10 thành phố (KHÔNG PHẢI 10 sản phẩm!)

ĐÚNG:
WITH top_products AS (
  SELECT TOP 10 p.ProductKey, p.ProductName, SUM(s.Sales) AS TotalSales
  FROM products p JOIN sales s ON p.ProductKey = s.ProductKey
  GROUP BY p.ProductKey, p.ProductName
  ORDER BY TotalSales DESC
)
SELECT tp.ProductName, tp.TotalSales, g.City
FROM top_products tp
JOIN sales s ON tp.ProductKey = s.ProductKey
JOIN geography g ON s.GeographyKey = g.GeographyKey

### FORMAT KẾT QUẢ ###
Trả lời dưới dạng JSON:
{
    "sql": "<T-SQL query>",
    "explanation": "<giải thích ngắn gọn bằng tiếng Việt>"
}
"""



SQL_GENERATION_USER_PROMPT = """### DATABASE SCHEMA ###
{ddl_context}

### CÂU HỎI ###
{question}

Hãy sinh T-SQL chính xác để trả lời câu hỏi trên.
"""


class SQLGenerator:
    """Sinh SQL từ câu hỏi + DDL context."""

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    def generate(
        self,
        question: str,
        ddl_context: str,
        sql_samples: list[dict] | None = None,
    ) -> SQLGenerationResult:
        """
        Sinh SQL query.

        Args:
            question: Câu hỏi user.
            ddl_context: DDL context từ Phase 4 ContextBuilder.
            sql_samples: Few-shot SQL examples (optional).

        Returns:
            SQLGenerationResult với sql và explanation.
        """
        user_prompt = SQL_GENERATION_USER_PROMPT.format(
            ddl_context=ddl_context,
            question=question,
        )

        # Thêm SQL samples nếu có
        if sql_samples:
            samples_text = "\n### SQL SAMPLES ###\n"
            for s in sql_samples:
                samples_text += f"Question: {s['question']}\nSQL: {s['sql']}\n\n"
            user_prompt = samples_text + user_prompt

        result = self._llm.chat_json(
            user_prompt=user_prompt,
            system_prompt=SQL_GENERATION_SYSTEM_PROMPT,
        )

        sql = result.get("sql", "")
        explanation = result.get("explanation", "")

        if not sql:
            logger.error(f"No SQL generated: {result}")

        logger.info(f"Generated SQL: {sql[:100]}...")
        return SQLGenerationResult(
            sql=sql,
            explanation=explanation,
            raw_response=result,
        )
