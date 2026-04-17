"""
response_generator.py
─────────────────────
LLM-powered natural language response generator.

Uses the Ollama model to produce conversational, context-aware summaries
from SQL query results instead of rigid template strings.

The model receives: question + column names + first few rows + row count.
It returns a concise, friendly natural-language summary.

Template fallback is used only when Ollama is unavailable.
"""

import json
import logging
import os
import re
from typing import Optional

import httpx

log = logging.getLogger(__name__)

OLLAMA_URL     = os.getenv("OLLAMA_URL",     "http://localhost:11434")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "llama3.2")
SQLCODER_MODEL = os.getenv("SQLCODER_MODEL", "sqlcoder")

# Provider mode switch must mirror SQL generation mode in rag_engine.py.
LEGACY_PROVIDER = os.getenv("SQL_LLM_PROVIDER", "").strip().lower()
MODE = os.getenv("MODE", "").strip().upper()
if not MODE:
    MODE = "DATABRICKS" if LEGACY_PROVIDER == "openai_compat" else "OLLAMA"

# Databricks OpenAI-compatible settings
DATABRICKS_BASE_URL = os.getenv(
    "DATABRICKS_BASE_URL",
    os.getenv("OPENAI_BASE_URL", ""),
).strip().rstrip("/")
DATABRICKS_CHAT_COMPLETIONS_URL = os.getenv("DATABRICKS_CHAT_COMPLETIONS_URL", "").strip()
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
DATABRICKS_MODEL = os.getenv("DATABRICKS_MODEL", os.getenv("OPENAI_MODEL", FALLBACK_MODEL)).strip()

# Groq OpenAI-compatible settings
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip().rstrip("/")
GROQ_CHAT_COMPLETIONS_URL = os.getenv("GROQ_CHAT_COMPLETIONS_URL", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()


def _databricks_chat_url() -> str:
    if DATABRICKS_CHAT_COMPLETIONS_URL:
        return DATABRICKS_CHAT_COMPLETIONS_URL
    if DATABRICKS_BASE_URL:
        return f"{DATABRICKS_BASE_URL}/chat/completions"
    return ""


def _groq_chat_url() -> str:
    if GROQ_CHAT_COMPLETIONS_URL:
        return GROQ_CHAT_COMPLETIONS_URL
    return f"{GROQ_BASE_URL}/chat/completions" if GROQ_BASE_URL else ""

# Cached model name for prose generation
_PROSE_MODEL: str | None = None


async def _get_prose_model() -> str:
    """Pick the best available model for prose generation."""
    global _PROSE_MODEL
    if _PROSE_MODEL:
        return _PROSE_MODEL

    if MODE == "DATABRICKS":
        _PROSE_MODEL = DATABRICKS_MODEL or FALLBACK_MODEL
        return _PROSE_MODEL

    if MODE == "GROQ":
        _PROSE_MODEL = GROQ_MODEL or FALLBACK_MODEL
        return _PROSE_MODEL

    try:
        async with httpx.AsyncClient(timeout=4) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                available = [m["name"] for m in resp.json().get("models", [])]
                # Prefer llama3.2 for natural language over sqlcoder
                for preferred in [FALLBACK_MODEL, "llama3.2:1b", SQLCODER_MODEL]:
                    for m in available:
                        if preferred.lower() in m.lower():
                            _PROSE_MODEL = m
                            return m
                if available:
                    _PROSE_MODEL = available[0]
                    return _PROSE_MODEL
    except Exception as e:
        log.warning("Prose model detection failed: %s", e)
    return FALLBACK_MODEL


def _build_summary_prompt(question: str, rows: list, row_count: int, columns: list) -> str:
    """Build a tight prompt for the model to summarise query results."""
    sample = rows[:8] if rows else []
    sample_json = json.dumps(sample, default=str)
    truncated_note = f" (showing first 8 of {row_count})" if row_count > 8 else ""

    timetable_cols = {"day_of_week", "hour_number", "start_time", "end_time"}
    is_timetable   = timetable_cols.issubset(set(columns))

    if is_timetable:
        extra = (
            "This is a timetable result. Mention which days are covered and "
            "highlight 1-2 specific slots (day + hour + subject). Keep it concise."
        )
    elif any(k in question.lower() for k in ["what are all the subjects", "which subjects", "currently handling", "currently handle", "teach"]):
        extra = (
            "This is a faculty-subject list result. Summarize the unique subjects being handled, "
            "mention the count only once, and do not repeat the count in later sentences. "
            "Do not describe timetable slots unless the user explicitly asked for day/hour details."
        )
    elif row_count == 1 and len(columns) == 1:
        extra = "This is a single aggregate value. State it clearly and naturally."
    elif row_count > 50:
        extra = f"There are {row_count} rows — give a high-level summary, not a list."
    else:
        extra = "Give a short, friendly summary of what was found."

    return (
        f"You are a helpful college data assistant. A user asked: \"{question}\"\n"
        f"The database returned {row_count} row(s){truncated_note} "
        f"with columns: {', '.join(columns)}.\n"
        f"Sample data: {sample_json}\n\n"
        f"Write a concise, natural, conversational response (2-3 sentences max). "
        f"Use **bold** for key numbers or names. {extra}\n"
        f"IMPORTANT: Reply with ONLY the summary text. No SQL, no JSON, no preamble."
    )


async def _llm_summarise(question: str, rows: list, row_count: int, columns: list) -> str | None:
    """Call the LLM to generate a natural language summary. Returns None on failure."""
    try:
        model = await _get_prose_model()
        prompt = _build_summary_prompt(question, rows, row_count, columns)

        async with httpx.AsyncClient(timeout=18) as client:
            if MODE == "DATABRICKS":
                chat_url = _databricks_chat_url()
                if not chat_url:
                    return None
                headers = {"Content-Type": "application/json"}
                if DATABRICKS_TOKEN:
                    headers["Authorization"] = f"Bearer {DATABRICKS_TOKEN}"

                resp = await client.post(
                    chat_url,
                    headers=headers,
                    json={
                        "model": model,
                        "temperature": 0.2,
                        "max_tokens": 180,
                        "messages": [
                            {"role": "system", "content": "You summarize SQL query results accurately and concisely."},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if resp.status_code != 200:
                    return None
                payload = resp.json()
                text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            elif MODE == "GROQ":
                chat_url = _groq_chat_url()
                if not chat_url:
                    return None
                headers = {"Content-Type": "application/json"}
                if GROQ_API_KEY:
                    headers["Authorization"] = f"Bearer {GROQ_API_KEY}"

                resp = await client.post(
                    chat_url,
                    headers=headers,
                    json={
                        "model": model,
                        "temperature": 0.2,
                        "max_tokens": 180,
                        "messages": [
                            {"role": "system", "content": "You summarize SQL query results accurately and concisely."},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if resp.status_code != 200:
                    return None
                payload = resp.json()
                text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            else:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model":  model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature":    0.3,
                            "num_predict":    120,
                            "num_ctx":        1024,
                            "stop":           ["###", "Question:", "SQL:", "```", "SELECT"],
                            "repeat_penalty": 1.1,
                        },
                    },
                )
                if resp.status_code != 200:
                    return None
                text = resp.json().get("response", "").strip()

        if text:
            # Sanitise: strip any accidental SQL/code leakage
            text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
            # Reject if model returned SQL instead of prose
            if text and len(text) > 10 and not re.match(r"^\s*SELECT\b", text, re.IGNORECASE):
                log.info("[ResponseGen] LLM summary: %d chars", len(text))
                return text
    except Exception as e:
        log.warning("[ResponseGen] LLM summarise failed: %s", e)
    return None


# ─── Fallback template helpers ────────────────────────────────────────────────

def _fallback_summary(question: str, rows: list, row_count: int, columns: list) -> str:
    """Fast template-based fallback when LLM is unavailable."""
    q = question.lower()

    if row_count == 0:
        return "No results found. Try rephrasing or adjusting your filters."

    timetable_cols = {"day_of_week", "hour_number", "start_time", "end_time"}
    if timetable_cols.issubset(set(columns)) and rows:
        days = sorted(
            {str(r.get("day_of_week", "")) for r in rows if r.get("day_of_week")},
            key=lambda d: {"Mon":1,"Tue":2,"Wed":3,"Thu":4,"Fri":5,"Sat":6}.get(d, 9)
        )
        days_txt = ", ".join(days) if days else "multiple days"
        sample = rows[0]
        subj    = sample.get("subject_name") or sample.get("subject_code") or "an activity"
        start   = sample.get("start_time", "")
        end     = sample.get("end_time", "")
        time_txt = f" ({start}–{end})" if start and end else ""
        return (
            f"Found **{row_count}** timetable entr{'y' if row_count==1 else 'ies'} "
            f"across {days_txt}. "
            f"First slot: {sample.get('day_of_week','?')} hour {sample.get('hour_number','?')}"
            f"{time_txt} — {subj}."
        )

    if row_count == 1 and len(columns) == 1:
        val = list(rows[0].values())[0]
        return f"The answer is **{val}**."

    entity_map = {
        "student": "student", "faculty": "faculty member",
        "arrear": "arrear record", "subject": "subject",
        "department": "department",
    }
    entity = next((v for k, v in entity_map.items() if k in q), "result")
    s = "s" if row_count != 1 else ""

    preview_key = next(
        (k for k in ["name", "full_name", "register_number", "subject_code", "department_code"]
         if rows and k in rows[0]), None
    )
    if preview_key and rows:
        names = [str(r.get(preview_key, "")).strip() for r in rows[:3] if r.get(preview_key)]
        names = [n for n in names if n]
        if names:
            sample_txt = f" including **{names[0]}**" + (f" and **{names[1]}**" if len(names) > 1 else "")
            return f"Found **{row_count}** {entity}{s}{sample_txt}."

    return f"Found **{row_count}** {entity}{s}."


def _is_free_period_question(question: str) -> bool:
    q = (question or "").lower()
    markers = ["free period", "free slot", "free", "available", "is free", "not occupied"]
    return any(m in q for m in markers)


def _build_free_period_summary(rows: list) -> str:
    if not rows:
        return "No free periods found for the requested filters."

    day_order = {"Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6}

    sorted_rows = sorted(
        rows,
        key=lambda r: (
            day_order.get(str(r.get("day_of_week", "")), 9),
            int(r.get("hour_number") or 999),
        ),
    )

    parts = []
    for r in sorted_rows[:8]:
        day = str(r.get("day_of_week", "?") or "?")
        hour = r.get("hour_number", "?")
        start = str(r.get("start_time", "") or "").strip()
        end = str(r.get("end_time", "") or "").strip()
        time_txt = f" ({start}-{end})" if start and end else ""
        parts.append(f"{day} hour {hour}{time_txt}")

    extra = "" if len(rows) <= 8 else f" and {len(rows) - 8} more"
    return f"Found **{len(rows)}** free period(s): " + ", ".join(parts) + extra + "."


def _is_parent_contact_question(question: str) -> bool:
    q = (question or "").lower()
    return any(k in q for k in ["parent", "father", "mother", "guardian", "phone", "contact"])


def _is_parent_contact_result(columns: list) -> bool:
    col_set = set(columns or [])
    return (
        "father_contact_number" in col_set
        or "mother_contact_number" in col_set
        or "father_name" in col_set
        or "mother_name" in col_set
    )


def _extract_requested_names(question: str) -> list[str]:
    q = (question or "").strip()
    if not q:
        return []

    patterns = [
        r"(?:of|for)\s+([A-Za-z\.,\s]{2,120})\s+(?:student|students|stud)",
        r"(?:of|for)\s+([A-Za-z\.,\s]{2,120})",
    ]
    strip_tail = re.compile(
        r"\s+(?:\d+(?:st|nd|rd|th)?\s*(?:sem|semester)|dcs|cse|ece|it|ai&ds|student|students).*",
        re.IGNORECASE,
    )

    for pat in patterns:
        matches = list(re.finditer(pat, q, flags=re.IGNORECASE))
        if not matches:
            continue

        blob = matches[-1].group(1).strip(" .,:;-?")
        blob = strip_tail.sub("", blob).strip(" .,:;-?")
        parts = [p.strip(" .,:;-?") for p in re.split(r",|\band\b", blob, flags=re.IGNORECASE)]
        cleaned = []
        for p in parts:
            p = re.sub(r"\b(?:dr|mr|mrs|ms|professor|prof)\.?\b", "", p, flags=re.IGNORECASE).strip()
            if len(p) >= 2:
                cleaned.append(p)
        if cleaned:
            return cleaned

    return []


def _build_parent_contact_summary(rows: list) -> str:
    if not rows:
        return "No parent contact details found for the requested student filters."

    requested = _extract_requested_names(rows[0].get("_question", "")) if rows and isinstance(rows[0], dict) else []
    row_names = [str(r.get("name", "")).strip() for r in rows if str(r.get("name", "")).strip()]

    snippets = []
    for r in rows[:6]:
        name = str(r.get("name", "Student")).strip() or "Student"
        father = str(r.get("father_contact_number", "-")).strip() or "-"
        mother = str(r.get("mother_contact_number", "-")).strip() or "-"
        snippets.append(f"**{name}** (Father: {father}, Mother: {mother})")

    extra = "" if len(rows) <= 6 else f" and {len(rows) - 6} more"

    summary = "Parent contact details: " + "; ".join(snippets) + extra + "."

    if requested and row_names:
        lowered_rows = [n.lower() for n in row_names]
        not_found = []
        for req in requested:
            token = req.lower().strip()
            if not token:
                continue
            if not any(token in rn for rn in lowered_rows):
                not_found.append(req)
        if not_found:
            summary += " No matching data found for: " + ", ".join(not_found) + "."

    return summary


def _enforce_summary_count(summary: str, row_count: int, display_type: str) -> str:
    """Ensure summary count aligns with actual result row_count for list-like outputs."""
    if not summary or display_type not in {"table", "timetable"}:
        return summary

    # Normalize common phrasing mismatches: "8 faculty members", "12 rows", etc.
    patt = re.compile(
        r"\b(\d+)\s+"
        r"(faculty(?:\s+members?)?|students?|subjects?|rows?|records?|results?|entries?)\b",
        flags=re.IGNORECASE,
    )

    # Replace ALL count phrases so mixed summaries don't remain inconsistent.
    found_any = False

    def _replace_count(match: re.Match) -> str:
        nonlocal found_any
        found_any = True
        noun = match.group(2)
        return f"{row_count} {noun}"

    summary = patt.sub(_replace_count, summary)
    if found_any:
        return summary

    # If no explicit count phrase exists, prepend one for consistency.
    return f"Found **{row_count}** result(s). {summary}"


# ─── Public API ────────────────────────────────────────────────────────────────

class ResponseGenerator:
    """LLM-powered response generator with fast template fallback."""

    async def generate_async(
        self,
        question: str,
        rows: list,
        row_count: int,
        columns: list,
        error: Optional[str] = None,
    ) -> dict:
        """
        Generate a natural language response asynchronously.
        Uses LLM when available, falls back to templates otherwise.

        Returns:
            {
                "summary":      str,
                "display_type": str,   # text | table | timetable | metric | empty | error
                "data":         dict,
            }
        """
        if error:
            return {
                "summary":      f"I ran into a problem processing that query: {error[:120]}",
                "display_type": "error",
                "data":         {"error": error},
            }

        if row_count == 0:
            return {
                "summary":      "No results found for that query. Try adjusting your filters or rephrasing.",
                "display_type": "empty",
                "data":         {"message": "No data available"},
            }

        # Determine display type (fast, deterministic)
        timetable_cols = {"day_of_week", "hour_number", "start_time", "end_time"}
        col_set = set(columns)

        if timetable_cols.issubset(col_set):
            display_type = "timetable"
        elif row_count == 1 and len(columns) == 1 and isinstance(
            rows[0].get(columns[0]), (int, float)
        ):
            display_type = "metric"
        else:
            display_type = "table"

        # Hybrid guardrail: deterministic summaries for high-risk intents.
        if _is_parent_contact_question(question) and _is_parent_contact_result(columns):
            enriched_rows = [dict(r, _question=question) if isinstance(r, dict) else r for r in rows]
            summary = _build_parent_contact_summary(enriched_rows)
        elif display_type == "timetable" and _is_free_period_question(question):
            summary = _build_free_period_summary(rows)
        else:
            # LLM summary (best effort, async)
            summary = await _llm_summarise(question, rows, row_count, columns)
            if not summary:
                summary = _fallback_summary(question, rows, row_count, columns)

        summary = _enforce_summary_count(summary, row_count, display_type)

        if display_type == "metric":
            val = rows[0].get(columns[0])
            data = {"value": val, "label": columns[0]}
        else:
            data = {"rows": rows, "columns": columns, "row_count": row_count}

        return {"summary": summary, "display_type": display_type, "data": data}

    def generate(
        self,
        question: str,
        rows: list,
        row_count: int,
        columns: list,
        error: Optional[str] = None,
    ) -> dict:
        """
        Sync shim — used by legacy callers.
        When inside an async event loop (FastAPI), uses the fast fallback.
        Callers should prefer _tool_format_response which calls generate_async.
        """
        if error:
            return {"summary": f"I ran into a problem: {error[:120]}", "display_type": "error", "data": {}}
        if not rows or row_count == 0:
            return {"summary": "No results found.", "display_type": "empty", "data": {}}

        timetable_cols = {"day_of_week", "hour_number", "start_time", "end_time"}
        col_set = set(columns)
        if timetable_cols.issubset(col_set):
            display_type = "timetable"
        elif row_count == 1 and len(columns) == 1 and isinstance(rows[0].get(columns[0]), (int, float)):
            display_type = "metric"
        else:
            display_type = "table"

        if _is_parent_contact_question(question) and _is_parent_contact_result(columns):
            enriched_rows = [dict(r, _question=question) if isinstance(r, dict) else r for r in rows]
            summary = _build_parent_contact_summary(enriched_rows)
        elif display_type == "timetable" and _is_free_period_question(question):
            summary = _build_free_period_summary(rows)
        else:
            summary = _fallback_summary(question, rows, row_count, columns)

        summary = _enforce_summary_count(summary, row_count, display_type)
        return {
            "summary":      summary,
            "display_type": display_type,
            "data":         {"rows": rows, "columns": columns, "row_count": row_count},
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_generator: ResponseGenerator | None = None


def get_response_generator() -> ResponseGenerator:
    global _generator
    if _generator is None:
        _generator = ResponseGenerator()
    return _generator