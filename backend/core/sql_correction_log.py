"""
core/sql_correction_log.py
────────────────────────────
Fire-and-forget logging of automatic SQL corrections (schema-drift fixes and
department-scope injections) for the planned model fine-tuning dataset.
Mirrors the fire-and-forget pattern in core/chat_memory.py exactly: lazy
engine import, plain synchronous SQLAlchemy call, non-fatal on failure.

Call this plainly `await`ed from central_agent.py right after a correction
fires — do not schedule it via asyncio.create_task. That would be
inconsistent with how the rest of the history-logging pipeline
(routers/chat.py._save_history) behaves, and could leave an untracked
background task outliving the request in edge cases (e.g. server shutdown
mid-request).
"""

import json
import logging
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


async def log_correction(
    *,
    user_id: str,
    session_id: str,
    question: str,
    original_sql: str,
    corrected_sql: str,
    rule_names: list[str],
    department_code: Optional[str] = None,
) -> None:
    """Best-effort insert into sql_corrections. Never raises — a logging
    failure must not affect the chat response. No-op when nothing actually
    changed."""
    if not rule_names or original_sql == corrected_sql:
        return

    engine = _get_engine()
    if engine is None:
        return

    try:
        insert_sql = text("""
            INSERT INTO sql_corrections (
                user_id, session_id, question, original_sql, corrected_sql,
                rule_names, department_code
            ) VALUES (
                :user_id, :session_id, :question, :original_sql, :corrected_sql,
                :rule_names, :department_code
            )
        """)
        with engine.connect() as conn:
            conn.execute(insert_sql, {
                "user_id": user_id,
                "session_id": session_id,
                "question": (question or "")[:2000],
                "original_sql": original_sql,
                "corrected_sql": corrected_sql,
                "rule_names": json.dumps(rule_names),
                "department_code": department_code,
            })
            conn.commit()
    except Exception as e:
        log.warning("Failed to log SQL correction (non-fatal): %s", e)
