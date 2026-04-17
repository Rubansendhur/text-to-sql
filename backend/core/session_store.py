"""
core/session_store.py
─────────────────────
In-memory conversation session store.

Replaces the chat_messages DB table approach.

Why in-memory?
  - Chat history for a college monitoring tool doesn't need to survive
    server restarts — users start a new conversation each time they visit.
  - No schema migrations, no FK constraints, no JSON columns needed.
  - Much faster: no DB round-trip per message.
  - Still scoped per user + session.

What's stored per turn:
  role        "user" | "assistant"
  content     the text of the turn
  sql         (assistant only) the generated SQL, for debugging
  data        (assistant only) rows / columns / display_type
  intent      classified intent for this turn
  ts          unix timestamp

Session expiry:
  Sessions older than SESSION_TTL_HOURS are silently dropped on next access.
  This prevents unbounded memory growth on long-running servers.
"""

import time
import logging
from collections import OrderedDict
from typing import Optional

log = logging.getLogger(__name__)

SESSION_TTL_SECONDS = int(60 * 60 * 8)   # 8 hours — one working day
MAX_SESSIONS        = 500                 # hard cap across all users
MAX_TURNS_PER_SESSION = 50               # oldest turns pruned beyond this

# ── Session data structure ────────────────────────────────────────────────────
class Turn:
    __slots__ = ("role", "content", "sql", "data", "intent", "ts")

    def __init__(self, role: str, content: str,
                 sql: str | None = None,
                 data: dict | None = None,
                 intent: str | None = None):
        self.role    = role       # "user" | "assistant"
        self.content = content
        self.sql     = sql
        self.data    = data or {}
        self.intent  = intent
        self.ts      = time.time()


class Session:
    def __init__(self, user_id: str, session_id: str, department_code: str | None):
        self.user_id         = user_id
        self.session_id      = session_id
        self.department_code = department_code
        self.turns: list[Turn] = []
        self.pending_clarification: dict | None = None  # clarification state
        self.created_at = time.time()
        self.last_active = time.time()

    def add_turn(self, turn: Turn):
        self.turns.append(turn)
        self.last_active = time.time()
        # prune oldest turns if over limit
        if len(self.turns) > MAX_TURNS_PER_SESSION:
            self.turns = self.turns[-MAX_TURNS_PER_SESSION:]

    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > SESSION_TTL_SECONDS

    def recent_turns(self, n: int = 6) -> list[Turn]:
        """Return the last n turns (for prompt context injection)."""
        return self.turns[-n:]

    def last_user_question(self) -> str | None:
        """Return the most recent user question (excluding current one)."""
        user_turns = [t for t in self.turns if t.role == "user"]
        if len(user_turns) >= 2:
            return user_turns[-2].content
        return None

    def to_prompt_context(self, max_turns: int = 4) -> str:
        """
        Format the last few turns into a compact context block for the
        RAG prompt.  Keeps it short so we don't blow the LLM context window.
        """
        turns = self.recent_turns(max_turns * 2)   # *2 because user+assistant pairs
        if not turns:
            return ""
        lines = []
        for t in turns:
            prefix = "User" if t.role == "user" else "Assistant"
            # For assistant turns, show the summary not the full SQL
            text = t.content[:200]  # cap at 200 chars
            lines.append(f"{prefix}: {text}")
        return "### Conversation so far:\n" + "\n".join(lines) + "\n"


# ── Store ─────────────────────────────────────────────────────────────────────
class SessionStore:
    """
    Thread-safe (GIL is enough for async FastAPI workers) ordered dict of sessions.
    Key: (user_id, session_id)
    """

    def __init__(self):
        self._sessions: OrderedDict[tuple, Session] = OrderedDict()

    def _evict_expired(self):
        """Remove sessions that have timed out."""
        expired = [k for k, s in self._sessions.items() if s.is_expired()]
        for k in expired:
            del self._sessions[k]
            log.debug("Evicted expired session %s", k)

    def _enforce_cap(self):
        """Keep total session count under MAX_SESSIONS."""
        while len(self._sessions) >= MAX_SESSIONS:
            oldest_key = next(iter(self._sessions))
            del self._sessions[oldest_key]

    def get_or_create(
        self,
        user_id: str,
        session_id: str,
        department_code: str | None = None,
    ) -> Session:
        self._evict_expired()
        key = (user_id, session_id)
        if key not in self._sessions:
            self._enforce_cap()
            self._sessions[key] = Session(user_id, session_id, department_code)
            log.info("New session %s for user %s", session_id[:8], user_id)
        else:
            # Move to end (LRU ordering keeps recently-used sessions alive)
            self._sessions.move_to_end(key)
        return self._sessions[key]

    def get(self, user_id: str, session_id: str) -> Optional[Session]:
        key = (user_id, session_id)
        s = self._sessions.get(key)
        if s and s.is_expired():
            del self._sessions[key]
            return None
        return s

    def list_sessions(self, user_id: str) -> list[dict]:
        """Return summary info for all live sessions belonging to user_id."""
        self._evict_expired()
        result = []
        for (uid, sid), s in self._sessions.items():
            if uid != user_id:
                continue
            preview = ""
            if s.turns:
                last = s.turns[-1]
                preview = last.content[:80]
            result.append({
                "session_id":    sid,
                "message_count": len(s.turns),
                "last_active":   s.last_active,
                "preview":       preview,
            })
        # newest first
        result.sort(key=lambda x: x["last_active"], reverse=True)
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store