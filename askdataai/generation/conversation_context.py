"""
Conversation Context Engine — Stage 0.5.

Architecture: Rolling Summary + 7 Recent Turns (no mem0/ChromaDB required).

Why no mem0:
  - mem0 uses semantic search + LLM fact-extraction → prone to hallucination
    when context is short (e.g., "that month" → mem0 retrieves wrong fact).
  - For Text-to-SQL, sequential turn ordering matters more than semantic similarity.

Design:
  ┌─────────────────────────────────────────────────────┐
  │  session_store[session_id] = {                      │
  │    "turns":   deque(maxlen=7),   # raw turns        │
  │    "summary": str,               # rolling summary  │
  │  }                                                  │
  └─────────────────────────────────────────────────────┘

  enrich(question):
    1. Fetch summary + 7 most recent turns from store.
    2. Build context block → LLM rewrites if question has a reference.
    3. Return enriched_question.

  save_turn(question, sql, result_summary):
    1. Append turn to deque(7).
    2. Every 5 turns → LLM updates rolling summary (background).
    → No LLM call if not needed.

Advantages:
  ✓ Zero external dependencies (no ChromaDB, mem0ai).
  ✓ Deterministic: LLM only sees EXACTLY what the user wrote.
  ✓ Ordered context: turns in chronological order → handles anaphora well.
  ✓ Rolling summary prevents context explosion after many turns.
"""

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from askdataai.generation.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Number of recent turns to include in context ───────────────────────────────
MAX_RECENT_TURNS = 7

# ── Update rolling summary every N turns ──────────────────────────────────────
SUMMARY_UPDATE_EVERY = 5


# ── Prompts ────────────────────────────────────────────────────────────────────

_ENRICHMENT_SYSTEM = """\
You are an AI that resolves contextual references in Text-to-SQL conversations.

TASK: Rewrite the question into a SELF-CONTAINED, clear, unambiguous version.

RULES:
1. Resolve ALL references to previous turns: "that", "it", "that month",
   "same period", "the highest one above", "the other", "similar", etc.
2. Only use information PRESENT in the conversation history — do NOT invent anything.
3. If the question is ALREADY SELF-CONTAINED (no ambiguous references) → copy it verbatim.
4. Output: ONLY the rewritten question. No explanation, no prefix."""

_ENRICHMENT_USER = """\
### PREVIOUS CONVERSATION SUMMARY:
{summary}

### 7 MOST RECENT TURNS (chronological order):
{recent_turns}

### NEW QUESTION TO REWRITE:
"{question}"

Rewritten question:\
"""

_SUMMARY_SYSTEM = """\
You are an AI that summarizes Text-to-SQL conversation history concisely.

REQUIREMENTS:
- Keep: tables queried, filters applied (year/month/product/region),
  notable results (max/min/total), topics being tracked.
- Omit: greetings, confirmations, SQL syntax details.
- Summary ≤ 150 words, in bullet list format."""

_SUMMARY_USER = """\
### OLD SUMMARY:
{old_summary}

### NEW TURNS:
{new_turns}

Updated summary (≤ 150 words, bullet list):\
"""


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Turn:
    """A single conversation turn."""
    question: str           # user's original question
    sql: str                # executed SQL query
    result_summary: str     # brief summary of the result


@dataclass
class EnrichResult:
    """Result from Stage 0.5 ConversationContextEngine."""
    enriched_question: str
    was_enriched: bool = False
    memories_used: list[str] = field(default_factory=list)
    session_id: str = ""


# ── Session store ──────────────────────────────────────────────────────────────

@dataclass
class _Session:
    turns: deque = field(default_factory=lambda: deque(maxlen=MAX_RECENT_TURNS))
    summary: str = "(No conversation history yet)"
    turns_since_summary: int = 0   # counter to trigger summary update


# ── ConversationContextEngine ──────────────────────────────────────────────────

class ConversationContextEngine:
    """
    Stage 0.5: Enrich question using rolling summary + 7 most recent turns.

    - enrich()              : SYNC — runs in main pipeline thread.
    - save_turn_background(): ASYNC — background thread, does not block response.
    """

    def __init__(self, llm_client: LLMClient, enabled: bool = True):
        self._llm = llm_client
        self._enabled = enabled
        # Dict[session_id → _Session]  (in-memory, no persistence needed)
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
        SYNC — runs in main pipeline thread.

        1. Fetch summary + 7 most recent turns for this session.
        2. If context is empty → return original (no LLM call).
        3. LLM rewrites question to be self-contained.
        """
        if not self._enabled:
            return EnrichResult(enriched_question=question, session_id=session_id)

        session = self._get_session(session_id)

        # No history yet → first question, skip enrichment
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
        ASYNC (daemon thread) — does not block main pipeline response.

        1. Append turn to deque(7).
        2. Every SUMMARY_UPDATE_EVERY turns → update rolling summary.
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
        """Format list of turns into a clear text block."""
        if not turns:
            return "(No turns yet)"

        lines = []
        for i, t in enumerate(turns, 1):
            lines.append(f"[Turn {i}]")
            lines.append(f"  User: {t.question}")
            if t.sql:
                # Truncate long SQL to avoid token bloat
                sql_preview = t.sql.strip()[:300].replace("\n", " ")
                lines.append(f"  SQL : {sql_preview}")
            if t.result_summary:
                lines.append(f"  Result: {t.result_summary}")
        return "\n".join(lines)

    def _llm_rewrite(self, question: str, summary: str, recent_turns: str) -> str:
        """Call LLM to rewrite question with context from summary + turns."""
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
        """Runs in background thread."""
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

        # Update rolling summary when enough new turns accumulate
        if should_update_summary:
            self._update_summary(session, session_id)

    def _update_summary(self, session: _Session, session_id: str) -> None:
        """LLM updates rolling summary from old_summary + current turns."""
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
