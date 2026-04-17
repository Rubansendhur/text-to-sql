"""
routers/chat.py
───────────────
AI chat endpoints — production-grade NL→SQL chatbot.

Architecture
────────────
  1. IntentClassifier  (core/intent.py)
       GREETING       → friendly welcome
       CHITCHAT       → conversational reply
       CLARIFY_DAY    → timetable with no day → ask user
       CLARIFY_REPLY  → user replied with day → reconstruct question
       DATA_QUERY     → proceed to RAG pipeline

  2. SessionStore      (core/session_store.py)
       In-memory, TTL-based, scoped per user+session.
       Used for immediate follow-up context injection.

  3. RAG Engine        (core/rag_engine.py)
       Embeds question → retrieves similar few-shot SQL examples →
       builds prompt → calls Ollama → returns NlResult.

  4. SQL Validator Agent  (core/sql_validator.py)   ← NEW
       Checks generated SQL against known schema BEFORE hitting DB.
       • Detects timetable columns on wrong table alias
       • Detects non-existent columns
       • Provides targeted retry hints
       • Auto-fixes common mistakes where possible

  5. SQL Execution     (core/sql_executor.py)
       Runs the validated SELECT, returns rows.

  6. Self-healing retry loop
       • Timetable-column error → targeted hint retry
       • Repairable PostgreSQL error → error-aware retry
       • Join multiplication → deduplicate retry

  7. Persistent history  (core/chat_memory.py)     ← ENABLED
       Every turn is stored in chat_messages table for analytics.
       Failures are non-fatal (history write never breaks the response).

  8. Response generator (core/response_generator.py)
       Formats rows into a conversational summary + display_type.

Endpoints
─────────
  POST /api/chat              → main chat
  GET  /api/chat/sessions     → list user's sessions
  GET  /api/chat/history/{id} → full turn history (DB-backed)
  GET  /api/health            → server / DB / model status
  GET  /api/model             → active AI model info
"""

import logging
import uuid
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from core.intent import (
    Intent,
    classify,
    clarify_day_reply,
    chitchat_reply,
    greeting_reply,
    responsible_usage_reply,
)
from core.session_store import Turn, get_session_store
from core.sql_executor import get_executor
from core.chat_memory import get_chat_history
from core.central_agent import CentralAgent
from core.chat_helpers import get_engine, expand_followup_question
from core.response_generator import get_response_generator
from routers.auth import get_current_user, is_central_admin, require_department_code

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])

# How many times we'll retry SQL generation before giving up
_MAX_RETRIES = 2


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    role: str = "hod"

    @field_validator("role")
    @classmethod
    def normalise_role(cls, v: str) -> str:
        return v if v in {"hod", "staff"} else "hod"


class ChatResponse(BaseModel):
    session_id: str
    message_id: int | None = None
    question: str
    summary: str
    display_type: str       # "text" | "table" | "metric" | "clarify" | "error" | "empty"
    data: dict
    columns: list[str]
    row_count: int
    sql: str | None = None
    model_used: str
    confidence: str
    execution_ms: float
    error: str | None = None
    awaiting_clarification: bool = False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _text_response(
    session_id: str,
    question: str,
    summary: str,
    message_id: int | None = None,
    display_type: str = "text",
    model_used: str = "chat-intent",
    awaiting_clarification: bool = False,
) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        message_id=message_id,
        question=question,
        summary=summary,
        display_type=display_type,
        data={"message": summary},
        columns=[],
        row_count=0,
        sql=None,
        model_used=model_used,
        confidence="high",
        execution_ms=0.0,
        error=None,
        awaiting_clarification=awaiting_clarification,
    )


def _error_response(
    session_id: str,
    question: str,
    summary: str,
    error: str,
    message_id: int | None = None,
    sql: str | None = None,
    model_used: str = "unknown",
) -> ChatResponse:
    return ChatResponse(
        session_id=session_id,
        message_id=message_id,
        question=question,
        summary=summary,
        display_type="error",
        data={"error": error},
        columns=[],
        row_count=0,
        sql=sql,
        model_used=model_used,
        confidence="low",
        execution_ms=0.0,
        error=error,
    )


def _expand_with_session(question: str, session) -> str:
    """Expand a short follow-up using in-memory session turn history."""
    if not session or not session.turns:
        return question
    history_msgs = [
        {"question": t.content}
        for t in session.turns
        if t.role == "user"
    ]
    return expand_followup_question(question, history_msgs)


async def _save_history(
    *,
    user_id: str,
    session_id: str,
    question: str,
    sql: str | None,
    response: str,
    result_count: int,
    model_used: str,
    confidence: str,
    execution_ms: float,
    error: str | None,
    department_code: str | None,
    intent: str | None,
    validation_errors: list[str] | None = None,
    rows: list | None = None,
)-> int:
    """
    Fire-and-forget history persistence.
    Failures are logged but NEVER propagate to the caller.
    """
    import json
    from fastapi.encoders import jsonable_encoder
    try:
        chat_history = get_chat_history()
        results_json = json.dumps(jsonable_encoder(rows)) if rows else None
        return await chat_history.save_message(
            user_id=user_id,
            session_id=session_id,
            question=question,
            sql=sql,
            response=response,
            results_json=results_json,
            result_count=result_count,
            model_used=model_used,
            confidence=confidence,
            execution_ms=execution_ms,
            error=error,
            department_code=department_code,
            intent=intent,
            validation_errors=validation_errors,
        )
    except Exception as exc:
        logger.warning("Non-fatal: failed to persist chat history: %s", exc)
        return -1


class FeedbackRequest(BaseModel):
    message_id: int
    feedback_score: int  # +1 thumbs up, -1 thumbs down


class FeedbackResponse(BaseModel):
    ok: bool
    message: str


# ── Main Chat Endpoint ────────────────────────────────────────────────────────

@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ChatResponse:
    raw_question = req.question.strip()
    if not raw_question:
        raise HTTPException(400, "Question cannot be empty")
    if len(raw_question) > 500:
        raise HTTPException(400, "Question too long (max 500 chars)")

    # ── Context ───────────────────────────────────────────────────────────────
    session_id = req.session_id or str(uuid.uuid4())
    user_id    = current_user.get("username") or current_user.get("sub", "unknown")
    role       = current_user.get("role", "hod")
    is_admin   = is_central_admin(current_user)
    dept       = require_department_code(current_user) if not is_admin else None

    store   = get_session_store()
    session = store.get_or_create(user_id, session_id, dept)

    # Expand short follow-ups using recent session context BEFORE intent classify
    # so terse prompts like "on 22nd?" can inherit prior question context.
    expanded_for_intent = _expand_with_session(raw_question, session)

    # ── Intent classification ─────────────────────────────────────────────────
    classified = classify(
        expanded_for_intent,
        session.pending_clarification,
        department_code=dept,
        is_central_admin=is_admin,
    )
    intent     = classified["intent"]
    question   = classified["question"]   # "today" resolved to actual day if needed

    session.add_turn(Turn(role="user", content=raw_question, intent=intent))

    # ── Greeting ──────────────────────────────────────────────────────────────
    if intent == Intent.GREETING:
        reply = greeting_reply(dept)
        session.add_turn(Turn(role="assistant", content=reply, intent=intent))
        message_id = await _save_history(
            user_id=user_id, session_id=session_id, question=raw_question,
            sql=None, response=reply, result_count=0,
            model_used="chat-intent", confidence="high", execution_ms=0,
            error=None, department_code=dept, intent=intent,
        )
        return _text_response(session_id, raw_question, reply, message_id=message_id if message_id > 0 else None)

    # ── Chitchat ──────────────────────────────────────────────────────────────
    if intent == Intent.CHITCHAT:
        reply = chitchat_reply(raw_question, dept)
        session.add_turn(Turn(role="assistant", content=reply, intent=intent))
        message_id = await _save_history(
            user_id=user_id, session_id=session_id, question=raw_question,
            sql=None, response=reply, result_count=0,
            model_used="chat-intent", confidence="high", execution_ms=0,
            error=None, department_code=dept, intent=intent,
        )
        return _text_response(session_id, raw_question, reply, message_id=message_id if message_id > 0 else None)

    # ── Responsible usage guardrail ─────────────────────────────────────────
    if intent == Intent.UNSAFE:
        reply = responsible_usage_reply(raw_question)
        session.add_turn(Turn(role="assistant", content=reply, intent=intent))
        message_id = await _save_history(
            user_id=user_id, session_id=session_id, question=raw_question,
            sql=None, response=reply, result_count=0,
            model_used="chat-policy", confidence="high", execution_ms=0,
            error=None, department_code=dept, intent=intent,
        )
        return _text_response(session_id, raw_question, reply, message_id=message_id if message_id > 0 else None)

    # ── Needs clarification (no day given for timetable) ─────────────────────
    if intent == Intent.CLARIFY_DAY:
        pending_reason = (classified.get("pending") or {}).get("reason")
        if pending_reason == "weekend":
            reply = (
                "That looks like a weekend day (Saturday/Sunday). "
                "Are weekend classes running in your timetable? "
                "If yes, reply with that day again; otherwise tell me a working day "
                "(e.g., Monday) and I will fetch it for that day."
            )
        else:
            reply = clarify_day_reply(question)
        session.pending_clarification = classified["pending"]
        session.add_turn(Turn(role="assistant", content=reply, intent=intent))
        message_id = await _save_history(
            user_id=user_id, session_id=session_id, question=raw_question,
            sql=None, response=reply, result_count=0,
            model_used="chat-intent", confidence="high", execution_ms=0,
            error=None, department_code=dept, intent=intent,
        )
        return _text_response(
            session_id, raw_question, reply,
            message_id=message_id if message_id > 0 else None,
            display_type="clarify",
            awaiting_clarification=True,
        )

    # ── User replied with a day ───────────────────────────────────────────────
    if intent == Intent.CLARIFY_REPLY:
        session.pending_clarification = None

    # ── DATA_QUERY ────────────────────────────────────────────────────────────
    session.pending_clarification = None

    # ── DATA_QUERY via CentralAgent ───────────────────────────────────────────
    session.pending_clarification = None

    agent = CentralAgent(
        engine=get_engine(request),
        executor=get_executor(),
        session_store=store
    )

    # Question is already session-expanded before classification.
    semantic_q = question
    is_followup = expanded_for_intent.lower().strip() != raw_question.lower().strip()

    result = await agent.handle_data_query(
        user_id=user_id,
        session_id=session_id,
        question=semantic_q,
        role=role,
        department_code=dept,
        is_central_admin=is_admin
    )

    # ── Build a natural followup prefix if this was a context-expanded question ──
    summary = result.response
    if is_followup and result.display_type not in ("error",) and not result.error:
        faculty = result.resolved_faculty
        if faculty:
            # Clean up any title prefix for display (keep it natural)
            display_name = faculty.strip()
            summary = f"Sure! Here's **{display_name}**'s timetable:\n\n{summary}"
        else:
            # Generic followup acknowledgement
            summary = f"Got it — here are the results:\n\n{summary}"

    # Convert AgentResult to ChatResponse
    display_type = result.display_type

    # Simple heuristic to flip display_type back to 'text' if agent returned text without data
    if display_type == "table" and not result.results_json and not result.result_count:
        display_type = "text"

    session.add_turn(Turn(role="assistant", content=summary, intent=intent))

    # Log history asynchronously
    message_id = await _save_history(
        user_id=user_id,
        session_id=session_id,
        question=raw_question,
        sql=result.sql,
        response=result.response,
        result_count=result.result_count,
        model_used=result.model_used,
        confidence=result.confidence,
        execution_ms=result.execution_ms,
        error=result.error,
        department_code=dept,
        intent=intent,
        validation_errors=result.validation_errors
    )

    chat_response = ChatResponse(
        session_id=session_id,
        message_id=message_id if message_id > 0 else None,
        question=raw_question,
        summary=summary,  # uses the (possibly prefixed) summary
        display_type=display_type,
        data=result.display_data or ({"message": summary, "data": result.results_json} if result.results_json else {"message": summary}),
        columns=result.columns or [],
        row_count=result.result_count,
        sql=result.sql,
        model_used=result.model_used,
        confidence=result.confidence,
        execution_ms=result.execution_ms,
        error=result.error
    )

    return chat_response


@router.post("/api/chat/feedback", response_model=FeedbackResponse)
async def save_chat_feedback(
    req: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
) -> FeedbackResponse:
    if req.feedback_score not in (-1, 1):
        raise HTTPException(400, "feedback_score must be -1 or 1")

    user_id = current_user.get("username") or current_user.get("sub", "unknown")
    ok = await get_chat_history().save_feedback(
        user_id=user_id,
        message_id=req.message_id,
        feedback_score=req.feedback_score,
    )
    if not ok:
        return FeedbackResponse(ok=False, message="Unable to save feedback for this message")
    return FeedbackResponse(ok=True, message="Feedback saved")


# ── Session endpoints (in-memory) ─────────────────────────────────────────────

@router.get("/api/chat/sessions")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """List active in-memory sessions for the current user."""
    user_id = current_user.get("username") or current_user.get("sub", "unknown")
    return get_session_store().list_sessions(user_id)


# ── History endpoint (DB-backed) ──────────────────────────────────────────────

@router.get("/api/chat/history/{session_id}")
async def get_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Retrieve full turn history for a session from the database.
    Falls back to in-memory session if DB row not found.
    """
    user_id = current_user.get("username") or current_user.get("sub", "unknown")

    # Try DB first
    chat_history = get_chat_history()
    db_turns = await chat_history.get_session_history(user_id, session_id, limit=100)
    if db_turns:
        return {
            "session_id": session_id,
            "turns":      db_turns,
            "total":      len(db_turns),
            "source":     "database",
        }

    # Fall back to in-memory
    session = get_session_store().get(user_id, session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired")

    turns = [
        {"role": t.role, "content": t.content, "sql": t.sql,
         "intent": t.intent, "ts": t.ts}
        for t in session.turns
    ]
    return {
        "session_id": session_id,
        "turns":      turns,
        "total":      len(turns),
        "source":     "memory",
    }


@router.get("/api/chat/sessions/history")
async def list_sessions_from_db(
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """
    List recent sessions from the DB (persisted across restarts).
    Returns in-memory list if DB is unavailable.
    """
    user_id = current_user.get("username") or current_user.get("sub", "unknown")
    chat_history = get_chat_history()
    db_sessions = await chat_history.get_recent_sessions(user_id, limit=20)
    if db_sessions:
        return db_sessions
    # Fall back to in-memory
    return get_session_store().list_sessions(user_id)


# ── Analytics endpoint (admin only) ──────────────────────────────────────────

@router.get("/api/chat/analytics")
async def chat_analytics(
    days: int = 7,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Return aggregate query stats for platform optimisation.
    Non-admins see only their department's data.
    """
    is_admin = is_central_admin(current_user)
    dept     = None if is_admin else current_user.get("department_code")

    chat_history = get_chat_history()
    summary  = await chat_history.get_analytics_summary(department_code=dept, days=days)
    failures = await chat_history.get_common_failures(department_code=dept, limit=10)

    return {
        "period_days":     days,
        "department":      dept or "all",
        "summary":         summary,
        "common_failures": failures,
    }


# ── Health / model info ───────────────────────────────────────────────────────

@router.get("/api/health")
async def health(request: Request):
    db_ok = False
    try:
        r = await get_executor().run("SELECT 1 AS ping")
        db_ok = bool(r.rows) and r.rows[0].get("ping") == 1
    except Exception:
        pass
    engine = get_engine(request)
    return {
        "status":      "ok" if db_ok else "degraded",
        "database":    "connected" if db_ok else "error",
        "ai_model":    engine.active_model or "not loaded",
        "model_ready": engine.active_model is not None,
        "rag_enabled": type(engine).__name__ == "RagEngine",
    }


@router.get("/api/model")
async def model_info(request: Request):
    engine = get_engine(request)
    if not engine.active_model:
        try:
            await engine.detect_available_model()
        except Exception as e:
            return {"model": None, "error": str(e)}
    return {
        "model":       engine.active_model,
        "rag_enabled": type(engine).__name__ == "RagEngine",
    }