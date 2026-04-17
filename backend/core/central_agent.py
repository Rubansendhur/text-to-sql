"""
core/central_agent.py
─────────────────────
Central orchestrator for the NL-to-SQL chat pipeline.
Replaces the monolithic if/elif loop in routers/chat.py.

This agent acts as the director, managing the budget of LLM calls
and coordinating the specific tools:
  1. Generator (RAG Engine)
  2. Validator (Schema & Logic rules)
  3. Executor (Database SQLAlchemy)
  4. Formatter (Response generation)
"""

import logging
import asyncio
import os
from typing import Any
from dataclasses import dataclass

from core.rag_engine import RagEngine
from core.sql_validator import validate_sql
from core.sql_executor import SQLExecutor
from core.response_generator import get_response_generator
from core.session_store import SessionStore
from core.chat_helpers import (
    build_semester_batch_sql, 
    build_free_staff_sql,
    build_parent_contact_sql,
    build_faculty_timetable_sql,
    extract_faculty_name_candidate,
    resolve_faculty_name,
    force_department_scope,
    normalize_sql,
    normalize_subject_list_sql,
)

log = logging.getLogger(__name__)

# Fast-fail budget config
MAX_LLM_CALLS = 2   # 1 initial + 1 retry max (no infinite or cascading loops)
# Backend has NO hardcoded timeout — only frontend timeout matters (125s).
# This allows sqlcoder to finish at its own pace without artificial backend cutoff.
MAX_TIMEOUT_S = None  # Disabled; frontend 125s is the real limit
ENABLE_PARENT_CONTACT_SHORTCUT = os.getenv("ENABLE_PARENT_CONTACT_SHORTCUT", "false").lower() == "true"

@dataclass
class AgentResult:
    response: str
    display_type: str = "text"
    display_data: dict | None = None
    sql: str | None = None
    results_json: list | None = None
    columns: list[str] | None = None
    result_count: int = 0
    confidence: str = "low"
    model_used: str = "none"
    error: str | None = None
    execution_ms: int = 0
    validation_errors: list[str] | None = None
    resolved_faculty: str | None = None  # set when deterministic timetable path ran


class CentralAgent:
    def __init__(
        self,
        engine: RagEngine,
        executor: SQLExecutor,
        session_store: SessionStore,
    ):
        self.engine = engine
        self.executor = executor
        self.session_store = session_store

    async def _tool_generate_sql(self, question: str, role: str, extra_hint: str, dept: str | None, is_admin: bool):
        """Tool 1: Generate SQL."""
        log.info(f"[Agent] Generating SQL (hint: {bool(extra_hint)})")
        return await self.engine.generate(
            question=question,
            role=role,
            extra_hint=extra_hint,
            department_code=dept,
            is_central_admin=is_admin
        )

    def _tool_validate_sql(self, sql: str, dept: str | None, is_admin: bool):
        """Tool 2: Schema validation."""
        log.info("[Agent] Validating generated SQL")
        return validate_sql(sql, department_code=dept, is_central_admin=is_admin)

    async def _tool_execute_sql(self, sql: str):
        """Tool 3: Execute in DB."""
        log.info("[Agent] Executing SQL against DB")
        return await self.executor.run(sql)

    async def _tool_format_response(self, question: str, sql: str, rows: list, columns: list):
        """Tool 4: LLM summary (async)."""
        log.info("[Agent] Formatting response via LLM")
        row_count = len(rows) if rows else 0
        return await get_response_generator().generate_async(
            question=question, rows=rows, row_count=row_count, columns=columns
        )

    async def handle_data_query(
        self,
        user_id: str,
        session_id: str,
        question: str,
        role: str,
        department_code: str | None,
        is_central_admin: bool
    ) -> AgentResult:
        """
        Main orchestration entry point.
        Uses a strict LLM budget to prevent 408 Timeouts.
        """
        log.info(
            "[Agent] handle_data_query | user=%s | role=%s | is_admin=%s | dept=%s",
            user_id, role, is_central_admin, department_code
        )

        # --- PRE-CHECK: Deterministic Rules (Cost: 0) ---
        q_lower = question.lower()

        # ── Parent data awareness ─────────────────────────────────────────────
        _parent_keywords = ("parent", "father", "mother", "guardian", "contact number",
                            "phone number", "family", "dad", "mom")
        _student_keywords = ("student", "hostel", "register", "name")
        if ENABLE_PARENT_CONTACT_SHORTCUT and any(k in q_lower for k in _parent_keywords):
            parent_sql = build_parent_contact_sql(question, department_code, is_central_admin)
            if parent_sql:
                log.info("Using deterministic parent-contact shortcut.")
                return await self._execute_and_format(question, parent_sql, 0)

        # ── Timetable shortcut ────────────────────────────────────────────────
        free_staff_sql = build_free_staff_sql(question, department_code, is_central_admin)
        if free_staff_sql:
            log.info("Using deterministic free-staff shortcut.")
            return await self._execute_and_format(question, free_staff_sql, 0)

        if any(k in q_lower for k in ["timetable", "schedule", "free", "hour", "slot", "record", "class", "teach", "period", "when does", "what time"]):
            cand = extract_faculty_name_candidate(question)
            faculty_name = await resolve_faculty_name(self.executor, cand, department_code, is_central_admin, role) if cand else None

            if faculty_name:
                log.info("Using deterministic timetable shortcut for faculty: %s", faculty_name)
                sql = build_faculty_timetable_sql(question, faculty_name, department_code, is_central_admin)
                result = await self._execute_and_format(question, sql, 0)
                result.resolved_faculty = faculty_name
                return result

        sem_batch_sql = build_semester_batch_sql(question, department_code, is_central_admin)
        if sem_batch_sql:
            log.info("Using deterministic semester/batch shortcut.")
            return await self._execute_and_format(question, sem_batch_sql, 0)

        # Context injection
        session = self.session_store.get(user_id, session_id)
        context = session.to_prompt_context() if session else ""
        full_prompt = f"Previous Context: {context}\nQuestion: {question}" if context else question

        # --- BUDGET TRACKER ---
        llm_calls_made = 0
        current_hint = ""
        validation_issues = []

        # No hardcoded backend timeout — sqlcoder takes as long as it needs.
        # Frontend 125s timeout is the effective limit for user perception.
        try:
            if MAX_TIMEOUT_S:
                core_result = await asyncio.wait_for(
                    self._run_agent_loop(
                        full_prompt, role, department_code, is_central_admin,
                        llm_calls_made, current_hint, validation_issues
                    ),
                    timeout=MAX_TIMEOUT_S
                )
            else:
                core_result = await self._run_agent_loop(
                    full_prompt, role, department_code, is_central_admin,
                    llm_calls_made, current_hint, validation_issues
                )
        except asyncio.TimeoutError:
            log.error("[Agent] Budget exceeded (%ds timeout breached).", MAX_TIMEOUT_S)
            return AgentResult(
                response="That query took too long to process. Please try simplifying your question.",
                error="Overall agent timeout",
                validation_errors=validation_issues,
            )

        # If the core loop already formatted (error / empty path), return immediately.
        if core_result.display_type in ("error", "empty") or not core_result.results_json:
            return core_result

        # Format the successful result outside the timeout window.
        try:
            resp_dict = await self._tool_format_response(
                question, core_result.sql or "", core_result.results_json, core_result.columns or []
            )
            core_result.response     = resp_dict.get("summary", core_result.response)
            core_result.display_type = resp_dict.get("display_type", core_result.display_type)
            core_result.display_data = resp_dict.get("data", core_result.display_data)
        except Exception as fmt_err:
            log.warning("[Agent] Prose formatting failed (non-fatal): %s", fmt_err)
            # Keep the fallback summary already in core_result.response

        return core_result

    async def _run_agent_loop(
        self, prompt, role, dept, is_admin, llm_calls, hint, validation_issues
    ) -> AgentResult:
        from core.sql_validator import hint_from_db_error

        final_sql = None
        model = "none"
        nl_res = None

        # ── Phase 1: Generate → Validate (max 2 LLM calls) ───────────────────
        while llm_calls < MAX_LLM_CALLS:
            llm_calls += 1
            log.info("[Agent] LLM call #%d (hint=%s)", llm_calls, bool(hint))
            nl_res = await self._tool_generate_sql(prompt, role, hint, dept, is_admin)
            model = nl_res.model_used

            if nl_res.error:
                return AgentResult(
                    response="I had trouble generating a database query for that. Please try rephrasing.",
                    display_type="error",
                    error=f"Generation Error: {nl_res.error}",
                    model_used=model
                )

            # Apply deterministic SQL normalizations before validation.
            sql = normalize_sql(nl_res.sql)
            sql = normalize_subject_list_sql(sql, question=prompt)

            # ── Validate (zero latency) ───────────────────────────────────────
            val_res = self._tool_validate_sql(sql, dept, is_admin)

            if val_res.is_valid:
                final_sql = sql
                log.info("[Agent] SQL passed validation on attempt #%d", llm_calls)
                break

            if val_res.fixed_sql:
                final_sql = val_res.fixed_sql
                validation_issues.extend(val_res.errors)
                log.info("[Agent] Validation auto-fixed SQL on attempt #%d", llm_calls)
                break

            # Deterministic fallback: if only department scope is missing,
            # inject a safe scope predicate so we don't burn the retry budget.
            if dept and not is_admin and any(
                "Missing mandatory department scope" in e for e in (val_res.errors or [])
            ):
                forced_sql = force_department_scope(sql, dept)
                if forced_sql and forced_sql != sql:
                    forced_val = self._tool_validate_sql(forced_sql, dept, is_admin)
                    if forced_val.is_valid or forced_val.fixed_sql:
                        final_sql = forced_val.fixed_sql or forced_sql
                        validation_issues.extend(val_res.errors)
                        log.info(
                            "[Agent] Injected department scope deterministically on attempt #%d",
                            llm_calls,
                        )
                        break

            # Validation failed — build hint and retry if budget allows
            validation_issues.extend(val_res.errors)
            log.warning("[Agent] Validation failed attempt #%d: %s", llm_calls, val_res.errors)
            hint = val_res.hint

        if not final_sql:
            last_sql = nl_res.sql if nl_res else None
            log.error("[Agent] Exhausted LLM budget without valid SQL. Issues: %s", validation_issues)
            return AgentResult(
                sql=last_sql,
                response=(
                    "I wasn't able to build a valid query for your question. "
                    "Could you try rephrasing it more specifically?"
                ),
                display_type="error",
                error="Max retries reached. Validation blocked query.",
                model_used=model,
                validation_errors=validation_issues,
            )

        # ── Phase 2: Execute ──────────────────────────────────────────────────
        final_sql = normalize_sql(final_sql)
        final_sql = normalize_subject_list_sql(final_sql, question=prompt)
        log.info("[Agent] Executing SQL: %.120s", final_sql)
        db_res = await self._tool_execute_sql(final_sql)

        if db_res.error:
            # If LLM budget remains, do ONE execution-error retry with a DB hint
            if llm_calls < MAX_LLM_CALLS:
                log.warning("[Agent] DB error on first try, retrying with hint: %.80s", db_res.error)
                retry_hint = hint_from_db_error(final_sql, db_res.error)
                llm_calls += 1
                nl_retry = await self._tool_generate_sql(prompt, role, retry_hint, dept, is_admin)

                if not nl_retry.error and nl_retry.sql:
                    retry_candidate = normalize_sql(nl_retry.sql)
                    retry_candidate = normalize_subject_list_sql(retry_candidate, question=prompt)
                    val_retry = self._tool_validate_sql(retry_candidate, dept, is_admin)
                    retry_sql = normalize_sql(val_retry.fixed_sql or retry_candidate)
                    retry_sql = normalize_subject_list_sql(retry_sql, question=prompt)
                    retry_db = await self._tool_execute_sql(retry_sql)

                    if not retry_db.error:
                        log.info("[Agent] DB retry succeeded on attempt #%d", llm_calls)
                        return AgentResult(
                            sql=retry_sql,
                            response="",   # filled in by caller after timeout window
                            display_type="table",
                            display_data={},
                            results_json=retry_db.rows,
                            columns=retry_db.columns,
                            result_count=retry_db.row_count,
                            confidence="medium",
                            model_used=nl_retry.model_used,
                            execution_ms=retry_db.execution_ms,
                            validation_errors=validation_issues,
                        )
                    log.warning("[Agent] DB retry also failed: %.80s", retry_db.error)

            log.error("[Agent] Database error (final): %s", db_res.error)
            return AgentResult(
                sql=final_sql,
                response=(
                    "I built the query but the database returned an error. "
                    "This can happen when the data doesn't exist in that form or "
                    "my understanding of the schema was slightly off."
                ),
                display_type="error",
                error=f"Execution error: {db_res.error}",
                model_used=model,
                execution_ms=db_res.execution_ms,
                validation_errors=validation_issues,
            )

        # ── Phase 3: Natural language response via LLM ────────────────────────
        log.info("[Agent] Query returned %d rows. Generating NL response.", db_res.row_count)
        resp_dict = await self._tool_format_response(prompt, final_sql, db_res.rows, db_res.columns)

        return AgentResult(
            sql=final_sql,
            response=resp_dict.get("summary", ""),
            display_type=resp_dict.get("display_type", "table"),
            display_data=resp_dict.get("data", {}),
            results_json=db_res.rows,
            columns=db_res.columns,
            result_count=db_res.row_count,
            confidence="high" if llm_calls == 1 else "medium",
            model_used=model,
            execution_ms=db_res.execution_ms,
            validation_errors=validation_issues,
        )

    async def _execute_and_format(self, question: str, sql: str, ms_offset: int) -> AgentResult:
        """Helper for deterministic rules that skip generation & validation."""
        sql = normalize_sql(sql)
        db_res = await self._tool_execute_sql(sql)
        if db_res.error:
            log.error("[Agent] Deterministic SQL error: %s", db_res.error)
            return AgentResult(
                sql=sql,
                response="There was a problem running that query. Please try again.",
                display_type="error",
                error=db_res.error,
                model_used="rule-based",
                execution_ms=db_res.execution_ms,
            )
        resp_dict = await self._tool_format_response(question, sql, db_res.rows, db_res.columns)
        return AgentResult(
            sql=sql,
            response=resp_dict.get("summary", ""),
            display_type=resp_dict.get("display_type", "table"),
            display_data=resp_dict.get("data", {}),
            results_json=db_res.rows,
            columns=db_res.columns,
            result_count=db_res.row_count,
            confidence="deterministic",
            model_used="rule-based",
            execution_ms=db_res.execution_ms,
        )