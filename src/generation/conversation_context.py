"""
Conversation Context Engine — Stage 0.5.

Kiến trúc: Rolling Summary + 7 Recent Turns (không dùng mem0/ChromaDB).

Tại sao bỏ mem0:
  - mem0 dùng semantic search + LLM fact-extraction → dễ hallucinate khi
    context ngắn (user nhắc đến "tháng đó" → mem0 search ra fact sai).
  - Với Text-to-SQL, sequential ordering của turns quan trọng hơn semantic similarity.

Thiết kế mới:
  ┌─────────────────────────────────────────────────────┐
  │  session_store[session_id] = {                      │
  │    "turns":   deque(maxlen=7),   # raw turns        │
  │    "summary": str,               # rolling summary  │
  │  }                                                  │
  └─────────────────────────────────────────────────────┘

  enrich(question):
    1. Lấy summary + 7 turns gần nhất từ store.
    2. Build context block → LLM rewrite nếu question có reference.
    3. Trả về enriched_question.

  save_turn(question, sql, result_summary):
    1. Append turn vào deque(7).
    2. Cứ mỗi 5 turns → LLM cập nhật rolling summary (background).
    → Không gọi LLM nếu không cần.

Ưu điểm:
  ✓ Zero external dependency (không cần ChromaDB, mem0ai).
  ✓ Deterministic: LLM chỉ thấy ĐÚNG những gì user đã nhắn.
  ✓ Ordered context: turns theo thứ tự thời gian → giải quyết anaphora tốt.
  ✓ Rolling summary ngăn context bùng nổ sau nhiều turns.
"""

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from src.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Số turns gần nhất đưa vào context ─────────────────────────────────────────
MAX_RECENT_TURNS = 7

# ── Cập nhật rolling summary mỗi N turns ──────────────────────────────────────
SUMMARY_UPDATE_EVERY = 5


# ── Prompts ────────────────────────────────────────────────────────────────────

_ENRICHMENT_SYSTEM = """\
Bạn là AI chuyên giải quyết tham chiếu ngữ cảnh trong hội thoại Text-to-SQL.

NHIỆM VỤ: Viết lại câu hỏi thành câu HỌC ĐỘC LẬP, rõ ràng, không mơ hồ.

QUY TẮC:
1. Giải quyết MỌI tham chiếu đến turns trước: "đó", "nó", "tháng đó",
   "cùng kỳ", "cao nhất ở trên", "cái kia", "tương tự", v.v.
2. Chỉ dùng thông tin CÓ TRONG lịch sử hội thoại — KHÔNG bịa thêm.
3. Nếu câu hỏi ĐÃ TỰ ĐỦ NGHĨA (không có tham chiếu mơ hồ) → copy nguyên xi.
4. Output: CHỈ câu hỏi được viết lại. Không giải thích, không prefix."""

_ENRICHMENT_USER = """\
### TÓM TẮT HỘI THOẠI TRƯỚC:
{summary}

### 7 TURNS GẦN NHẤT (theo thứ tự thời gian):
{recent_turns}

### CÂU HỎI MỚI CẦN VIẾT LẠI:
"{question}"

Câu hỏi được viết lại:\
"""

_SUMMARY_SYSTEM = """\
Bạn là AI tóm tắt lịch sử hội thoại Text-to-SQL một cách súc tích.

YÊU CẦU:
- Giữ lại: các bảng đã truy vấn, bộ lọc (năm/tháng/sản phẩm/khu vực),
  kết quả đáng chú ý (max/min/tổng), chủ đề đang theo dõi.
- Bỏ qua: câu chào, xác nhận, chi tiết SQL syntax.
- Tóm tắt ≤ 150 từ, dạng bullet list."""

_SUMMARY_USER = """\
### TÓM TẮT CŨ:
{old_summary}

### CÁC TURNS MỚI:
{new_turns}

Tóm tắt cập nhật (≤ 150 từ, bullet):\
"""


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Turn:
    """Một turn hội thoại."""
    question: str           # câu hỏi gốc của user
    sql: str                # SQL đã thực thi
    result_summary: str     # tóm tắt kết quả ngắn


@dataclass
class EnrichResult:
    """Kết quả từ Stage 0.5 ConversationContextEngine."""
    enriched_question: str
    was_enriched: bool = False
    memories_used: list[str] = field(default_factory=list)
    session_id: str = ""


# ── Session store ──────────────────────────────────────────────────────────────

@dataclass
class _Session:
    turns: deque = field(default_factory=lambda: deque(maxlen=MAX_RECENT_TURNS))
    summary: str = "(Chưa có lịch sử hội thoại)"
    turns_since_summary: int = 0   # đếm để trigger summary update


# ── ConversationContextEngine ──────────────────────────────────────────────────

class ConversationContextEngine:
    """
    Stage 0.5: Enrich câu hỏi bằng rolling summary + 7 turns gần nhất.

    - enrich()              : SYNC — chạy trong main pipeline thread.
    - save_turn_background(): ASYNC — background thread, không block response.
    """

    def __init__(self, llm_client: LLMClient, enabled: bool = True):
        self._llm = llm_client
        self._enabled = enabled
        # Dict[session_id → _Session]  (in-memory, không cần persistence)
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def enrich(
        self,
        question: str,
        session_id: str,
        user_id: str = "default",
    ) -> EnrichResult:
        """
        SYNC — chạy trong main pipeline thread.

        1. Lấy summary + 7 turns gần nhất của session.
        2. Nếu context rỗng → trả về nguyên gốc (không gọi LLM).
        3. LLM viết lại câu hỏi thành self-contained.
        """
        if not self._enabled:
            return EnrichResult(enriched_question=question, session_id=session_id)

        session = self._get_session(session_id)

        # Không có lịch sử → câu đầu tiên, bỏ qua enrichment
        if not session.turns:
            logger.info("[0.5/ConvCtx] No history yet → skip enrichment.")
            return EnrichResult(
                enriched_question=question,
                was_enriched=False,
                memories_used=[],
                session_id=session_id,
            )

        # Build context block
        recent_turns_text = self._format_turns(list(session.turns))
        memories_used = [t.question for t in session.turns]

        enriched_question = self._llm_rewrite(
            question=question,
            summary=session.summary,
            recent_turns=recent_turns_text,
        )
        was_enriched = enriched_question.strip().lower() != question.strip().lower()

        if was_enriched:
            logger.info(
                f"[0.5/ConvCtx] Enriched:\n"
                f"  Original : {question}\n"
                f"  Enriched : {enriched_question}"
            )
        else:
            logger.info("[0.5/ConvCtx] Question is self-contained, no change.")

        return EnrichResult(
            enriched_question=enriched_question,
            was_enriched=was_enriched,
            memories_used=memories_used,
            session_id=session_id,
        )

    def save_turn_background(
        self,
        question: str,
        enriched_question: str,
        sql: str,
        result_summary: str,
        session_id: str,
        user_id: str = "default",
    ) -> None:
        """
        ASYNC (daemon thread) — không block main pipeline response.

        1. Append turn vào deque(7).
        2. Mỗi SUMMARY_UPDATE_EVERY turns → cập nhật rolling summary.
        """
        if not self._enabled:
            return

        t = threading.Thread(
            target=self._save_turn_sync,
            args=(question, sql, result_summary, session_id),
            daemon=True,
        )
        t.start()

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE
    # ──────────────────────────────────────────────────────────────────────────

    def _get_session(self, session_id: str) -> _Session:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = _Session()
            return self._sessions[session_id]

    def _format_turns(self, turns: list[Turn]) -> str:
        """Format danh sách turns thành text block rõ ràng."""
        if not turns:
            return "(Chưa có turns)"

        lines = []
        for i, t in enumerate(turns, 1):
            lines.append(f"[Turn {i}]")
            lines.append(f"  User: {t.question}")
            if t.sql:
                # Cắt SQL dài để tránh token bloat
                sql_preview = t.sql.strip()[:300].replace("\n", " ")
                lines.append(f"  SQL : {sql_preview}")
            if t.result_summary:
                lines.append(f"  KQ  : {t.result_summary}")
        return "\n".join(lines)

    def _llm_rewrite(self, question: str, summary: str, recent_turns: str) -> str:
        """Gọi LLM để viết lại câu hỏi với context từ summary + turns."""
        user_prompt = _ENRICHMENT_USER.format(
            summary=summary,
            recent_turns=recent_turns,
            question=question,
        )
        try:
            result = self._llm.chat(
                user_prompt=user_prompt,
                system_prompt=_ENRICHMENT_SYSTEM,
            )
            cleaned = result.strip().strip('"').strip("'").strip()
            return cleaned if cleaned else question
        except Exception as exc:
            logger.warning(f"[ConversationContext] LLM rewrite failed: {exc}")
            return question  # fail-safe

    def _save_turn_sync(
        self,
        question: str,
        sql: str,
        result_summary: str,
        session_id: str,
    ) -> None:
        """Chạy trong background thread."""
        session = self._get_session(session_id)

        new_turn = Turn(
            question=question,
            sql=sql,
            result_summary=result_summary,
        )

        with self._lock:
            session.turns.append(new_turn)
            session.turns_since_summary += 1
            should_update_summary = (
                session.turns_since_summary >= SUMMARY_UPDATE_EVERY
            )

        logger.info(
            f"[ConversationContext] Saved turn (session={session_id}, "
            f"turns_in_window={len(session.turns)})"
        )

        # Cập nhật rolling summary khi đủ turns mới
        if should_update_summary:
            self._update_summary(session, session_id)

    def _update_summary(self, session: _Session, session_id: str) -> None:
        """LLM cập nhật rolling summary từ old_summary + turns hiện tại."""
        with self._lock:
            current_turns = list(session.turns)
            old_summary = session.summary

        new_turns_text = self._format_turns(current_turns)
        user_prompt = _SUMMARY_USER.format(
            old_summary=old_summary,
            new_turns=new_turns_text,
        )

        try:
            new_summary = self._llm.chat(
                user_prompt=user_prompt,
                system_prompt=_SUMMARY_SYSTEM,
            )
            new_summary = new_summary.strip()

            with self._lock:
                session.summary = new_summary
                session.turns_since_summary = 0

            logger.info(f"[ConversationContext] Rolling summary updated (session={session_id}).")
        except Exception as exc:
            logger.warning(f"[ConversationContext] Summary update failed: {exc}")
