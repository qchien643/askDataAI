"""
Pre-Filter — Stage 1 of Multi-Stage Intent Pipeline.

Lọc nhanh bằng regex/keyword, KHÔNG dùng LLM.
Tiết kiệm API calls cho ~40% câu hỏi không cần SQL generation.

Returns:
    - GREETING: chào hỏi → trả lời ngay
    - DESTRUCTIVE: yêu cầu xóa/sửa/thêm dữ liệu → từ chối ngay
    - OUT_OF_SCOPE: không liên quan data → reject
    - SCHEMA_EXPLORE: hỏi về schema → dùng SchemaExplorer
    - NEEDS_LLM: cần LLM để phân loại tiếp
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PreFilterResult(str, Enum):
    GREETING = "GREETING"
    DESTRUCTIVE = "DESTRUCTIVE"  # NEW: xóa/sửa/thêm dữ liệu
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SCHEMA_EXPLORE = "SCHEMA_EXPLORE"
    NEEDS_LLM = "NEEDS_LLM"


@dataclass
class FilterOutput:
    result: PreFilterResult
    response: str = ""  # Pre-built response (for GREETING, OUT_OF_SCOPE, DESTRUCTIVE)
    confidence: float = 1.0


# ─── Pattern definitions ────────────────────────────────────────

GREETING_PATTERNS = [
    r"^(xin\s*chào|chào\s*bạn|hello|hi|hey|good\s*morning|good\s*afternoon)",
    r"^(bạn\s*ơi|ê|alo|yo)\s*$",
    r"^(chào|hi|hello)\s*$",
]

# NEW: Destructive intent — yêu cầu thay đổi dữ liệu
# Chặn NGAY, không cần LLM, tiết kiệm 2+ API calls
DESTRUCTIVE_PATTERNS = [
    # Xóa (Vietnamese Unicode + ASCII + English)
    r"(xóa|xoá|xoa)\s+(dữ\s*liệu|du\s*lieu|bảng|bang|bản\s*ghi|ban\s*ghi|hàng|hang|cột|cot|record|row|table|data|all|het|hết|tất\s*cả|tat\s*ca)",
    r"(hãy|hay|giúp|giup|please|can\s*you)\s+(xóa|xoá|xoa|delete|remove|drop)",
    r"(xóa|xoá|xoa)\s+\w+\s*(khách|khach|nhân|nhan|sản|san|đơn|don|hóa|hoa|hàng|hang|viên|vien|phẩm|pham)",
    r"(delete|remove|drop|truncate|destroy|erase|wipe)\s+\w*",
    r"(làm\s*sạch|lam\s*sach|clear|dọn\s*dẹp|don\s*dep|reset)\s+(dữ\s*liệu|du\s*lieu|data|bảng|bang|table|database|db)",
    # Thêm / Insert
    r"(thêm|them|chèn|chen|tạo\s*mới|tao\s*moi|insert|add)\s+(dữ\s*liệu|du\s*lieu|bản\s*ghi|ban\s*ghi|record|row|hàng|hang|entry)",
    r"(hãy|hay|giúp|giup|please)\s+(thêm|them|chèn|chen|insert|add|create)",
    r"(thêm|them)\s+\w+\s*(khách|khach|nhân|nhan|sản|san|đơn|don|hóa|hoa|hàng|hang|viên|vien|phẩm|pham|vào|vao|mới|moi)",
    r"(insert\s+into|add\s+new|create\s+new)\s+\w+",
    # Sửa / Update
    r"(sửa|sua|cập\s*nhật|cap\s*nhat|chỉnh\s*sửa|chinh\s*sua|update|modify|edit|change)\s+(dữ\s*liệu|du\s*lieu|bản\s*ghi|ban\s*ghi|record|row|hàng|hang|giá|gia|tên|ten|name|value)",
    r"(hãy|hay|giúp|giup|please)\s+(sửa|sua|cập\s*nhật|cap\s*nhat|update|modify|edit|change)",
    r"(đổi|doi|thay\s*đổi|thay\s*doi|thay\s*the)\s+(tên|ten|giá|gia|giá\s*trị|gia\s*tri|name|price|value|status|trạng\s*thái|trang\s*thai)",
    r"(set|update)\s+\w+\s*(=|to)\s*",
    # Tạo / Drop bảng
    r"(tạo|tao|create)\s+(bảng|bang|table|database|schema|index)",
    r"(xóa|xoá|xoa|drop|delete)\s+(bảng|bang|table|database|schema|index)",
]

OUT_OF_SCOPE_PATTERNS = [
    r"(thời\s*tiết|thoi\s*tiet|weather|nhiệt\s*độ|nhiet\s*do|temperature)",
    r"(bạn\s*là\s*ai|ban\s*la\s*ai|who\s*are\s*you|bạn\s*tên\s*gì|ban\s*ten\s*gi)",
    r"(kể\s*chuyện|ke\s*chuyen|viết\s*bài|viet\s*bai|write\s*a\s*poem)",
    r"(viết|viet).*(thơ|tho|poem|truyện|truyen|chuyện|chuyen|bài|bai)",
    r"(dịch\s*sang|dich\s*sang|translate|dịch\s*giúm|dich\s*gium|dich\s*cho)",
    r"(tin\s*tức|tin\s*tuc|news|thể\s*thao|the\s*thao|sport)",
    r"(nấu\s*ăn|nau\s*an|recipe|công\s*thức|cong\s*thuc|món\s*ăn|mon\s*an)",
    r"(bạn\s*có\s*thể\s*gì|ban\s*co\s*the\s*gi|what\s*can\s*you\s*do)\s*$",
    r"(giải\s*thích\s*code|giai\s*thich\s*code|explain\s*code|viết\s*code|viet\s*code|write\s*code)",
    r"(tính\s*toán|tinh\s*toan|calculate)\s+\d+",
]

SCHEMA_EXPLORE_PATTERNS = [
    r"(có\s*những?\s*bảng\s*nào|co\s*nhung?\s*bang\s*nao|bảng\s*nào|bang\s*nao|list.*tables?|what.*tables?)",
    r"(bảng\s*\w+\s*có\s*cột\s*gì|bang\s*\w+\s*co\s*cot\s*gi|columns?\s*(of|in)\s*\w+)",
    r"(mô\s*tả\s*bảng|mo\s*ta\s*bang|describe\s*(table)?|explain\s*(the\s*)?table)",
    r"(mối\s*quan\s*hệ|moi\s*quan\s*he|relationship|liên\s*kết|lien\s*ket|foreign\s*key)",
    r"(schema|cấu\s*trúc\s*(dữ\s*liệu|database)|cau\s*truc\s*(du\s*lieu|database))",
    r"(tôi\s*có\s*thể\s*hỏi\s*gì|toi\s*co\s*the\s*hoi\s*gi|what\s*can\s*i\s*ask)",
    r"(giải\s*thích\s*bảng|giai\s*thich\s*bang|cấu\s*trúc\s*bảng|cau\s*truc\s*bang)",
]

GREETING_RESPONSES = [
    "Chào bạn! 👋 Tôi là Mini Wren AI — trợ lý truy vấn dữ liệu. "
    "Hãy hỏi tôi về dữ liệu trong database, ví dụ:\n"
    "• \"Tổng doanh thu theo tháng\"\n"
    "• \"Top 5 khách hàng mua nhiều nhất\"\n"
    "• \"Có những bảng nào?\"",
]

OUT_OF_SCOPE_RESPONSE = (
    "Xin lỗi, tôi chỉ hỗ trợ truy vấn dữ liệu trong database. "
    "Câu hỏi này nằm ngoài phạm vi của tôi. 😊\n\n"
    "Hãy thử hỏi về dữ liệu, ví dụ: \"Tổng doanh thu theo tháng\""
)

DESTRUCTIVE_RESPONSE = (
    "⛔ Tôi chỉ hỗ trợ **đọc dữ liệu** (SELECT), không thực hiện thay đổi dữ liệu.\n\n"
    "Các thao tác sau **không được phép**:\n"
    "• Xóa dữ liệu (DELETE/DROP)\n"
    "• Thêm dữ liệu (INSERT)\n"
    "• Sửa dữ liệu (UPDATE)\n\n"
    "💡 Hãy hỏi về dữ liệu thay vì thay đổi, ví dụ:\n"
    "• \"Danh sách khách hàng\"\n"
    "• \"Tổng doanh thu theo tháng\""
)


class PreFilter:
    """
    Stage 1: Lọc nhanh câu hỏi không cần LLM.

    Chạy < 1ms, tiết kiệm token cho câu hỏi đơn giản.
    Chặn destructive intent (xóa/sửa/thêm) TRƯỚC KHI gọi LLM.
    """

    def __init__(self):
        self._greeting_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE) for p in GREETING_PATTERNS
        ]
        self._destructive_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE) for p in DESTRUCTIVE_PATTERNS
        ]
        self._oos_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE) for p in OUT_OF_SCOPE_PATTERNS
        ]
        self._schema_patterns = [
            re.compile(p, re.IGNORECASE | re.UNICODE) for p in SCHEMA_EXPLORE_PATTERNS
        ]

    def filter(self, question: str) -> FilterOutput:
        """
        Lọc nhanh câu hỏi.

        Thứ tự ưu tiên:
        1. Empty/too short → reject
        2. GREETING → trả lời chào
        3. DESTRUCTIVE → từ chối ngay (xóa/sửa/thêm dữ liệu)
        4. OUT_OF_SCOPE → reject (không liên quan)
        5. SCHEMA_EXPLORE → trả lời schema
        6. NEEDS_LLM → cần LLM classify
        """
        q = question.strip()

        if not q:
            return FilterOutput(
                result=PreFilterResult.OUT_OF_SCOPE,
                response="Vui lòng nhập câu hỏi.",
            )

        # Quá ngắn (< 2 ký tự)
        if len(q) < 2:
            return FilterOutput(
                result=PreFilterResult.OUT_OF_SCOPE,
                response="Câu hỏi quá ngắn. Hãy mô tả rõ hơn bạn muốn biết gì.",
            )

        # Check GREETING
        for pattern in self._greeting_patterns:
            if pattern.search(q):
                logger.info(f"PreFilter: GREETING — {q[:30]}")
                return FilterOutput(
                    result=PreFilterResult.GREETING,
                    response=GREETING_RESPONSES[0],
                )

        # Check DESTRUCTIVE — chặn ngay, tiết kiệm 2+ LLM calls
        for pattern in self._destructive_patterns:
            if pattern.search(q):
                logger.info(f"PreFilter: DESTRUCTIVE — {q[:50]}")
                return FilterOutput(
                    result=PreFilterResult.DESTRUCTIVE,
                    response=DESTRUCTIVE_RESPONSE,
                )

        # Check OUT_OF_SCOPE
        for pattern in self._oos_patterns:
            if pattern.search(q):
                logger.info(f"PreFilter: OUT_OF_SCOPE — {q[:30]}")
                return FilterOutput(
                    result=PreFilterResult.OUT_OF_SCOPE,
                    response=OUT_OF_SCOPE_RESPONSE,
                )

        # Check SCHEMA_EXPLORE
        for pattern in self._schema_patterns:
            if pattern.search(q):
                logger.info(f"PreFilter: SCHEMA_EXPLORE — {q[:30]}")
                return FilterOutput(
                    result=PreFilterResult.SCHEMA_EXPLORE,
                )

        # Cần LLM để phân loại
        return FilterOutput(result=PreFilterResult.NEEDS_LLM)
