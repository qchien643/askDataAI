"""
Business Glossary - Map thuật ngữ nghiệp vụ → SQL concepts.

Inspired by: Querio Context Layer, Semantic Layer for Text-to-SQL.

Khi user hỏi "doanh thu khách hàng VIP quý 1":
- Glossary match: "doanh thu" → SUM(SalesAmount), "quý 1" → MONTH BETWEEN 1 AND 3
- Inject context hints vào SQL generation prompt

Glossary giúp:
1. Giải quyết ambiguity ("doanh thu" → cột nào?)
2. Cung cấp business logic (VIP = TotalPurchase > 1M)
3. Map terms tiếng Việt → SQL
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class GlossaryTerm:
    """Một thuật ngữ nghiệp vụ."""
    name: str                    # Tên thuật ngữ 
    aliases: list[str] = field(default_factory=list)   # Các tên khác
    sql_hint: str = ""           # SQL expression hint
    tables: list[str] = field(default_factory=list)    # Tables liên quan
    description: str = ""        # Mô tả


@dataclass
class GlossaryMatch:
    """Match kết quả từ glossary lookup."""
    term: GlossaryTerm
    matched_keyword: str         # Từ khóa match được trong câu hỏi


class BusinessGlossary:
    """
    Business glossary: map thuật ngữ → SQL hints.

    Load từ YAML file, scan câu hỏi cho matching terms.
    """

    def __init__(self, glossary_path: str = ""):
        self._terms: list[GlossaryTerm] = []
        self._keyword_index: dict[str, GlossaryTerm] = {}

        if glossary_path and os.path.exists(glossary_path):
            self._load(glossary_path)

    def _load(self, path: str) -> None:
        """Load glossary từ YAML file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "terms" not in data:
                logger.warning(f"Glossary file empty or missing 'terms' key: {path}")
                return

            for item in data["terms"]:
                term = GlossaryTerm(
                    name=item.get("name", ""),
                    aliases=item.get("aliases", []),
                    sql_hint=item.get("sql_hint", ""),
                    tables=item.get("tables", []),
                    description=item.get("description", ""),
                )
                self._terms.append(term)

                # Index by name + aliases (lowercase)
                self._keyword_index[term.name.lower()] = term
                for alias in term.aliases:
                    self._keyword_index[alias.lower()] = term

            logger.info(f"Loaded {len(self._terms)} glossary terms from {path}")

        except Exception as e:
            logger.error(f"Failed to load glossary: {e}")

    def lookup(self, question: str) -> list[GlossaryMatch]:
        """
        Tìm glossary terms matching trong câu hỏi.

        Args:
            question: Câu hỏi user.

        Returns:
            List of matches.
        """
        if not self._terms:
            return []

        question_lower = question.lower()
        matches = []
        seen_terms = set()

        # Sort keywords by length DESC để match longer first
        sorted_keywords = sorted(
            self._keyword_index.keys(),
            key=len,
            reverse=True,
        )

        for keyword in sorted_keywords:
            if keyword in question_lower:
                term = self._keyword_index[keyword]
                if term.name not in seen_terms:
                    matches.append(GlossaryMatch(
                        term=term,
                        matched_keyword=keyword,
                    ))
                    seen_terms.add(term.name)

        logger.info(f"Glossary lookup: {len(matches)} matches for '{question[:50]}'")
        return matches

    def build_context(self, matches: list[GlossaryMatch]) -> str:
        """Build context hints text từ glossary matches."""
        if not matches:
            return ""

        parts = ["### BUSINESS GLOSSARY ###"]
        for m in matches:
            parts.append(f"- \"{m.matched_keyword}\":")
            if m.term.description:
                parts.append(f"  Description: {m.term.description}")
            if m.term.sql_hint:
                parts.append(f"  SQL hint: {m.term.sql_hint}")
            if m.term.tables:
                parts.append(f"  Tables: {', '.join(m.term.tables)}")

        return "\n".join(parts)

    @property
    def term_count(self) -> int:
        return len(self._terms)
