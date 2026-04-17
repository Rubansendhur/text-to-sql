"""
core/chat_memory.py
────────────────────
Persistent chat history storage in PostgreSQL.

Stores every conversation turn (question + SQL + response + metadata) so
that:
  1. Future analytics can identify common query patterns and failures.
  2. Session context can survive server restarts (optional — the in-memory
     session_store is still used for immediate prompt context).
  3. Admin dashboard can show per-user / per-department query volumes.

Design notes
────────────
  • Uses the same SQLAlchemy engine returned by upload.helpers.get_db().
  • All writes are fire-and-forget: a failure to save history NEVER breaks
    the chat response to the user.
  • Reads are only for analytics/history endpoints — not on the hot path.
  • The table schema lives in migrations/001_create_chat_messages_table.sql.
    Run that migration before enabling this module.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text

log = logging.getLogger(__name__)


def _get_engine():
    """Lazy import to avoid circular deps at module load time."""
    try:
        from upload.helpers import get_db
        return get_db()
    except Exception as e:
        log.warning("Could not import get_db: %s", e)
        return None


# ── ChatHistory ───────────────────────────────────────────────────────────────

class ChatHistory:
    """
    Interface for reading and writing chat history from PostgreSQL.

    All methods are async-compatible (they use sync SQLAlchemy under the
    hood but are called with await from async FastAPI handlers via
    run_in_executor in a future iteration — for now they're fast enough).
    """

    async def save_message(
        self,
        user_id: str,
        session_id: str,
        question: str,
        sql: Optional[str],
        response: str,
        results_json: Optional[str],
        result_count: int,
        model_used: str,
        confidence: str,
        execution_ms: float,
        error: Optional[str] = None,
        department_code: Optional[str] = None,
        intent: Optional[str] = None,
        validation_errors: Optional[list[str]] = None,
    ) -> int:
        """
        Persist a single chat exchange.  Returns the auto-generated message ID,
        or -1 if the write fails (non-fatal — caller should not raise on -1).
        """
        engine = _get_engine()
        if engine is None:
            return -1

        try:
            insert_sql = text("""
                INSERT INTO chat_messages (
                    user_id, session_id, question, sql, response,
                    results_json, result_count, model_used, confidence,
                    execution_ms, error, department_code, intent,
                    validation_errors, timestamp
                ) VALUES (
                    :user_id, :session_id, :question, :sql, :response,
                    :results_json, :result_count, :model_used, :confidence,
                    :execution_ms, :error, :department_code, :intent,
                    :validation_errors, NOW()
                )
                RETURNING id
            """)

            params = {
                "user_id":           user_id,
                "session_id":        session_id,
                "question":          question[:2000] if question else "",
                "sql":               sql,
                "response":          response[:4000] if response else "",
                "results_json":      results_json,
                "result_count":      result_count,
                "model_used":        model_used or "unknown",
                "confidence":        confidence or "low",
                "execution_ms":      int(execution_ms),
                "error":             error,
                "department_code":   department_code,
                "intent":            intent,
                "validation_errors": json.dumps(validation_errors) if validation_errors else None,
            }

            with engine.connect() as conn:
                result = conn.execute(insert_sql, params)
                conn.commit()
                msg_id = result.scalar()
                log.debug(
                    "Saved chat message %s | user=%s session=%s dept=%s",
                    msg_id, user_id, session_id[:8], department_code
                )
                return msg_id or -1

        except Exception as e:
            log.warning("Failed to save chat message (non-fatal): %s", e)
            return -1

    async def get_session_history(
        self,
        user_id: str,
        session_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """
        Retrieve all turns for a session, oldest first.
        Returns [] on any error.
        """
        engine = _get_engine()
        if engine is None:
            return []

        try:
            query = text("""
                SELECT
                    id, question, sql, response, result_count,
                    model_used, confidence, execution_ms, error,
                    department_code, intent, validation_errors, timestamp
                FROM chat_messages
                WHERE user_id = :user_id AND session_id = :session_id
                ORDER BY timestamp ASC
                LIMIT :limit
            """)
            with engine.connect() as conn:
                rows = [dict(r._mapping) for r in conn.execute(query, {
                    "user_id":    user_id,
                    "session_id": session_id,
                    "limit":      limit,
                })]
            # Deserialise JSON columns
            for row in rows:
                if row.get("validation_errors"):
                    try:
                        row["validation_errors"] = json.loads(row["validation_errors"])
                    except Exception:
                        row["validation_errors"] = []
            return rows

        except Exception as e:
            log.warning("Failed to retrieve session history (non-fatal): %s", e)
            return []

    async def get_recent_sessions(
        self,
        user_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """
        Return a summary of recent sessions for a user, newest first.
        """
        engine = _get_engine()
        if engine is None:
            return []

        try:
            query = text("""
                SELECT
                    session_id,
                    MAX(timestamp) AS last_message,
                    COUNT(*)       AS message_count,
                    MIN(question)  AS preview
                FROM chat_messages
                WHERE user_id = :user_id
                GROUP BY session_id
                ORDER BY MAX(timestamp) DESC
                LIMIT :limit
            """)
            with engine.connect() as conn:
                return [dict(r._mapping) for r in conn.execute(query, {
                    "user_id": user_id,
                    "limit":   limit,
                })]
        except Exception as e:
            log.warning("Failed to retrieve sessions (non-fatal): %s", e)
            return []

    async def get_analytics_summary(
        self,
        department_code: Optional[str] = None,
        days: int = 7,
    ) -> dict:
        """
        Return aggregate stats useful for platform optimisation.
        Covers the last `days` days (default 7).
        """
        engine = _get_engine()
        if engine is None:
            return {}

        try:
            dept_filter = "AND department_code = :dept" if department_code else ""
            query = text(f"""
                SELECT
                    COUNT(*)                                           AS total_queries,
                    COUNT(*) FILTER (WHERE error IS NOT NULL)         AS error_count,
                    COUNT(*) FILTER (WHERE result_count = 0
                                    AND error IS NULL)                AS empty_results,
                    ROUND(AVG(execution_ms))                          AS avg_execution_ms,
                    COUNT(DISTINCT user_id)                           AS unique_users,
                    COUNT(DISTINCT session_id)                        AS unique_sessions
                FROM chat_messages
                WHERE timestamp >= NOW() - INTERVAL '{days} days'
                {dept_filter}
            """)
            params = {"dept": department_code} if department_code else {}
            with engine.connect() as conn:
                row = conn.execute(query, params).fetchone()
                return dict(row._mapping) if row else {}
        except Exception as e:
            log.warning("Failed to get analytics summary (non-fatal): %s", e)
            return {}

    async def get_common_failures(
        self,
        department_code: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Return the most common failed questions — useful for adding new
        few-shot examples to improve future accuracy.
        """
        engine = _get_engine()
        if engine is None:
            return []

        try:
            dept_filter = "AND department_code = :dept" if department_code else ""
            query = text(f"""
                SELECT
                    question,
                    COUNT(*) AS failure_count,
                    MAX(error) AS sample_error
                FROM chat_messages
                WHERE error IS NOT NULL
                {dept_filter}
                GROUP BY question
                ORDER BY failure_count DESC
                LIMIT :limit
            """)
            params = {"limit": limit}
            if department_code:
                params["dept"] = department_code
            with engine.connect() as conn:
                return [dict(r._mapping) for r in conn.execute(query, params)]
        except Exception as e:
            log.warning("Failed to get common failures (non-fatal): %s", e)
            return []

    async def save_feedback(
        self,
        *,
        user_id: str,
        message_id: int,
        feedback_score: int,
    ) -> bool:
        """
        Persist thumbs-up/thumbs-down feedback for a specific chat message.
        Returns True when updated, False otherwise.
        """
        engine = _get_engine()
        if engine is None:
            return False

        try:
            # Self-heal schema drift: if migration 003 was not applied yet,
            # add feedback columns before writing user feedback.
            ensure_sql = text("""
                ALTER TABLE chat_messages
                ADD COLUMN IF NOT EXISTS feedback_score SMALLINT,
                ADD COLUMN IF NOT EXISTS feedback_at TIMESTAMPTZ
            """)
            query = text("""
                UPDATE chat_messages
                SET feedback_score = :feedback_score,
                    feedback_at = NOW()
                WHERE id = :message_id
                  AND user_id = :user_id
            """)
            with engine.connect() as conn:
                conn.execute(ensure_sql)
                result = conn.execute(query, {
                    "feedback_score": feedback_score,
                    "message_id": message_id,
                    "user_id": user_id,
                })
                conn.commit()
                return bool(result.rowcount and result.rowcount > 0)
        except Exception as e:
            log.warning("Failed to save feedback (non-fatal): %s", e)
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────
_chat_history: Optional[ChatHistory] = None


def get_chat_history() -> ChatHistory:
    global _chat_history
    if _chat_history is None:
        _chat_history = ChatHistory()
    return _chat_history