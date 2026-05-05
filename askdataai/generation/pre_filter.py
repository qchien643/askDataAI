"""
Pre-Filter — Stage 1 of Multi-Stage Intent Pipeline.

Fast filtering using regex/keywords, NO LLM calls.
Saves API calls for ~40% of questions that don't need SQL generation.

Returns:
    - GREETING: greeting → respond immediately
    - DESTRUCTIVE: delete/modify/insert request → reject immediately
    - OUT_OF_SCOPE: unrelated to data → reject
    - SCHEMA_EXPLORE: schema question → use SchemaExplorer
    - NEEDS_LLM: requires LLM for further classification
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PreFilterResult(str, Enum):
    GREETING = "GREETING"
    DESTRUCTIVE = "DESTRUCTIVE"
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
    r"^(xin\s*ch\u00e0o|ch\u00e0o\s*b\u1ea1n|hello|hi|hey|good\s*morning|good\s*afternoon)",
    r"^(b\u1ea1n\s*\u01a1i|\u00ea|alo|yo)\s*$",
    r"^(ch\u00e0o|hi|hello)\s*$",
]

# Destructive intent — data modification requests
# Block IMMEDIATELY, no LLM needed, saves 2+ API calls
DESTRUCTIVE_PATTERNS = [
    # Delete (Vietnamese Unicode + ASCII + English)
    r"(x\u00f3a|xo\u00e1|xoa)\s+(d\u1eef\s*li\u1ec7u|du\s*lieu|b\u1ea3ng|bang|b\u1ea3n\s*ghi|ban\s*ghi|h\u00e0ng|hang|c\u1ed9t|cot|record|row|table|data|all|het|h\u1ebft|t\u1ea5t\s*c\u1ea3|tat\s*ca)",
    r"(h\u00e3y|hay|gi\u00fap|giup|please|can\s*you)\s+(x\u00f3a|xo\u00e1|xoa|delete|remove|drop)",
    r"(x\u00f3a|xo\u00e1|xoa)\s+\w+\s*(kh\u00e1ch|khach|nh\u00e2n|nhan|s\u1ea3n|san|\u0111\u01a1n|don|h\u00f3a|hoa|h\u00e0ng|hang|vi\u00ean|vien|ph\u1ea9m|pham)",
    r"(delete|remove|drop|truncate|destroy|erase|wipe)\s+\w*",
    r"(l\u00e0m\s*s\u1ea1ch|lam\s*sach|clear|d\u1ecdn\s*d\u1eb9p|don\s*dep|reset)\s+(d\u1eef\s*li\u1ec7u|du\s*lieu|data|b\u1ea3ng|bang|table|database|db)",
    # Insert
    r"(th\u00eam|them|ch\u00e8n|chen|t\u1ea1o\s*m\u1edbi|tao\s*moi|insert|add)\s+(d\u1eef\s*li\u1ec7u|du\s*lieu|b\u1ea3n\s*ghi|ban\s*ghi|record|row|h\u00e0ng|hang|entry)",
    r"(h\u00e3y|hay|gi\u00fap|giup|please)\s+(th\u00eam|them|ch\u00e8n|chen|insert|add|create)",
    r"(th\u00eam|them)\s+\w+\s*(kh\u00e1ch|khach|nh\u00e2n|nhan|s\u1ea3n|san|\u0111\u01a1n|don|h\u00f3a|hoa|h\u00e0ng|hang|vi\u00ean|vien|ph\u1ea9m|pham|v\u00e0o|vao|m\u1edbi|moi)",
    r"(insert\s+into|add\s+new|create\s+new)\s+\w+",
    # Update
    r"(s\u1eeda|sua|c\u1eadp\s*nh\u1eadt|cap\s*nhat|ch\u1ec9nh\s*s\u1eeda|chinh\s*sua|update|modify|edit|change)\s+(d\u1eef\s*li\u1ec7u|du\s*lieu|b\u1ea3n\s*ghi|ban\s*ghi|record|row|h\u00e0ng|hang|gi\u00e1|gia|t\u00ean|ten|name|value)",
    r"(h\u00e3y|hay|gi\u00fap|giup|please)\s+(s\u1eeda|sua|c\u1eadp\s*nh\u1eadt|cap\s*nhat|update|modify|edit|change)",
    r"(\u0111\u1ed5i|doi|thay\s*\u0111\u1ed5i|thay\s*doi|thay\s*the)\s+(t\u00ean|ten|gi\u00e1|gia|gi\u00e1\s*tr\u1ecb|gia\s*tri|name|price|value|status|tr\u1ea1ng\s*th\u00e1i|trang\s*thai)",
    r"(set|update)\s+\w+\s*(=|to)\s*",
    # Create/Drop table
    r"(t\u1ea1o|tao|create)\s+(b\u1ea3ng|bang|table|database|schema|index)",
    r"(x\u00f3a|xo\u00e1|xoa|drop|delete)\s+(b\u1ea3ng|bang|table|database|schema|index)",
]

OUT_OF_SCOPE_PATTERNS = [
    r"(th\u1eddi\s*ti\u1ebft|thoi\s*tiet|weather|nhi\u1ec7t\s*\u0111\u1ed9|nhiet\s*do|temperature)",
    r"(b\u1ea1n\s*l\u00e0\s*ai|ban\s*la\s*ai|who\s*are\s*you|b\u1ea1n\s*t\u00ean\s*g\u00ec|ban\s*ten\s*gi)",
    r"(k\u1ec3\s*chuy\u1ec7n|ke\s*chuyen|vi\u1ebft\s*b\u00e0i|viet\s*bai|write\s*a\s*poem)",
    r"(vi\u1ebft|viet).*(th\u01a1|tho|poem|truy\u1ec7n|truyen|chuy\u1ec7n|chuyen|b\u00e0i|bai)",
    r"(d\u1ecbch\s*sang|dich\s*sang|translate|d\u1ecbch\s*gi\u00fam|dich\s*gium|dich\s*cho)",
    r"(tin\s*t\u1ee9c|tin\s*tuc|news|th\u1ec3\s*thao|the\s*thao|sport)",
    r"(n\u1ea5u\s*\u0103n|nau\s*an|recipe|c\u00f4ng\s*th\u1ee9c|cong\s*thuc|m\u00f3n\s*\u0103n|mon\s*an)",
    r"(b\u1ea1n\s*c\u00f3\s*th\u1ec3\s*g\u00ec|ban\s*co\s*the\s*gi|what\s*can\s*you\s*do)\s*$",
    r"(gi\u1ea3i\s*th\u00edch\s*code|giai\s*thich\s*code|explain\s*code|vi\u1ebft\s*code|viet\s*code|write\s*code)",
    r"(t\u00ednh\s*to\u00e1n|tinh\s*toan|calculate)\s+\d+",
]

SCHEMA_EXPLORE_PATTERNS = [
    r"(c\u00f3\s*nh\u1eefng?\s*b\u1ea3ng\s*n\u00e0o|co\s*nhung?\s*bang\s*nao|b\u1ea3ng\s*n\u00e0o|bang\s*nao|list.*tables?|what.*tables?)",
    r"(b\u1ea3ng\s*\w+\s*c\u00f3\s*c\u1ed9t\s*g\u00ec|bang\s*\w+\s*co\s*cot\s*gi|columns?\s*(of|in)\s*\w+)",
    r"(m\u00f4\s*t\u1ea3\s*b\u1ea3ng|mo\s*ta\s*bang|describe\s*(table)?|explain\s*(the\s*)?table)",
    r"(m\u1ed1i\s*quan\s*h\u1ec7|moi\s*quan\s*he|relationship|li\u00ean\s*k\u1ebft|lien\s*ket|foreign\s*key)",
    r"(schema|c\u1ea5u\s*tr\u00fac\s*(d\u1eef\s*li\u1ec7u|database)|cau\s*truc\s*(du\s*lieu|database))",
    r"(t\u00f4i\s*c\u00f3\s*th\u1ec3\s*h\u1ecfi\s*g\u00ec|toi\s*co\s*the\s*hoi\s*gi|what\s*can\s*i\s*ask)",
    r"(gi\u1ea3i\s*th\u00edch\s*b\u1ea3ng|giai\s*thich\s*bang|c\u1ea5u\s*tr\u00fac\s*b\u1ea3ng|cau\s*truc\s*bang)",
]

GREETING_RESPONSES = [
    "Hello! \U0001f44b I'm askDataAI \u2014 your data query assistant. "
    "Ask me anything about your database, for example:\n"
    "\u2022 \"Total revenue by month\"\n"
    "\u2022 \"Top 5 customers by purchase volume\"\n"
    "\u2022 \"What tables are available?\"",
]

OUT_OF_SCOPE_RESPONSE = (
    "Sorry, I only support data queries within the connected database. "
    "This question is outside my scope. \U0001f600\n\n"
    "Try asking about your data, for example: \"Total revenue by month\""
)

DESTRUCTIVE_RESPONSE = (
    "\u26d4 I only support **reading data** (SELECT) and cannot perform data modification.\n\n"
    "The following operations are **not permitted**:\n"
    "\u2022 Delete data (DELETE/DROP)\n"
    "\u2022 Insert data (INSERT)\n"
    "\u2022 Update data (UPDATE)\n\n"
    "\U0001f4a1 Try asking about the data instead, for example:\n"
    "\u2022 \"List all customers\"\n"
    "\u2022 \"Total revenue by month\""
)


class PreFilter:
    """
    Stage 1: Fast question filtering without LLM.

    Runs < 1ms, saves tokens for simple questions.
    Blocks destructive intent (delete/modify/insert) BEFORE calling LLM.
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
        Fast question filtering.

        Priority order:
        1. Empty/too short → reject
        2. GREETING → respond with greeting
        3. DESTRUCTIVE → reject immediately (delete/modify/insert)
        4. OUT_OF_SCOPE → reject (unrelated)
        5. SCHEMA_EXPLORE → answer schema question
        6. NEEDS_LLM → requires LLM classification
        """
        q = question.strip()

        if not q:
            return FilterOutput(
                result=PreFilterResult.OUT_OF_SCOPE,
                response="Please enter your question.",
            )

        # Too short (< 2 characters)
        if len(q) < 2:
            return FilterOutput(
                result=PreFilterResult.OUT_OF_SCOPE,
                response="Question is too short. Please describe what you want to know.",
            )

        # Check GREETING
        for pattern in self._greeting_patterns:
            if pattern.search(q):
                logger.info(f"PreFilter: GREETING — {q[:30]}")
                return FilterOutput(
                    result=PreFilterResult.GREETING,
                    response=GREETING_RESPONSES[0],
                )

        # Check DESTRUCTIVE — block immediately, saves 2+ LLM calls
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

        # Requires LLM for classification
        return FilterOutput(result=PreFilterResult.NEEDS_LLM)
