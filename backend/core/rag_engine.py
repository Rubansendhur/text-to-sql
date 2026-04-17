"""
core/rag_engine.py
──────────────────
RAG-powered NL-to-SQL engine.

Uses the dedicated modules instead of duplicating logic:
  • core/embedder.py     — Ollama nomic-embed-text wrapper
  • core/qdrant_store.py — Qdrant collection search
  • data/few_shot.py     — curated Q→SQL training pairs (source of truth)

The examples are seeded into Qdrant once via:
    python scripts/seed_qdrant.py

At query time this engine:
  1. Embeds the user question.
  2. Retrieves top-K similar (question, SQL) pairs from Qdrant.
  3. Substitutes {DEPT} in each retrieved SQL with the actual user department.
  4. Builds a few-shot prompt (schema + context + substituted examples + question).
  5. Sends the prompt to Ollama (sqlcoder → llama3.2 fallback).
  6. Returns a NlResult with the generated SQL.

Department scoping rules:
  - Regular user (HOD / staff): department_code comes from their JWT token via
    require_department_code() in auth.py — only that department's data is visible.
  - Central admin: no department filter — queries span all departments.
"""

import hashlib
import logging
import os
import re

import httpx

from core.embedder     import embed, embed_batch
from core.qdrant_store import (
    search as qdrant_search,
    ensure_collection,
    upsert_examples,
    collection_info,
    filter_new_or_changed_examples,
)
from data.few_shot import FEW_SHOTS

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
OLLAMA_URL     = os.getenv("OLLAMA_URL",     "http://localhost:11434")
SQLCODER_MODEL = os.getenv("SQLCODER_MODEL", "sqlcoder")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "llama3.2")
TOP_K          = int(os.getenv("RAG_TOP_K",  "4"))   # 4 is enough; 5 adds noise
TOP_K_FAST     = int(os.getenv("RAG_TOP_K_FAST", "3"))

# Provider mode switch:
#   MODE=OLLAMA      -> local /api/generate
#   MODE=DATABRICKS  -> Databricks OpenAI-compatible chat/completions
#   MODE=GROQ        -> Groq OpenAI-compatible chat/completions
# Backward compatibility: if MODE is missing, legacy SQL_LLM_PROVIDER is used.
LEGACY_PROVIDER = os.getenv("SQL_LLM_PROVIDER", "").strip().lower()
MODE = os.getenv("MODE", "").strip().upper()
if not MODE:
    MODE = "DATABRICKS" if LEGACY_PROVIDER == "openai_compat" else "OLLAMA"

MODE_FALLBACK_PROVIDER = os.getenv(
    "MODE_FALLBACK_PROVIDER",
    os.getenv("OPENAI_COMPAT_FALLBACK_PROVIDER", "ollama"),
).strip().lower()

# Databricks OpenAI-compatible settings
DATABRICKS_BASE_URL = os.getenv(
    "DATABRICKS_BASE_URL",
    os.getenv("OPENAI_BASE_URL", ""),
).strip().rstrip("/")
DATABRICKS_CHAT_COMPLETIONS_URL = os.getenv("DATABRICKS_CHAT_COMPLETIONS_URL", "").strip()
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
DATABRICKS_MODEL = os.getenv("DATABRICKS_MODEL", os.getenv("OPENAI_MODEL", SQLCODER_MODEL)).strip()

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

# SQL generation latency controls (tunable from .env)
# NOTE: Backend has no hardcoded limit—frontend 125s is the real timeout.
# This allows sqlcoder time to complete without artificial cutoff.
GEN_TIMEOUT_S      = float(os.getenv("RAG_GENERATE_TIMEOUT_S", "120"))
WARMUP_TIMEOUT_S   = float(os.getenv("RAG_WARMUP_TIMEOUT_S", "60"))
MODEL_KEEP_ALIVE   = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
NUM_PREDICT_FAST   = int(os.getenv("RAG_NUM_PREDICT_FAST", "220"))
NUM_PREDICT_REPAIR = int(os.getenv("RAG_NUM_PREDICT_REPAIR", "280"))
NUM_CTX_FAST       = int(os.getenv("RAG_NUM_CTX_FAST", "1800"))
NUM_CTX_REPAIR     = int(os.getenv("RAG_NUM_CTX_REPAIR", "2304"))
 
# ── Concise schema (~30% shorter) ────────────────────────────────────────────
DB_SCHEMA = """\
### PostgreSQL Schema
 
departments(department_id PK, department_code VARCHAR UNIQUE, department_name VARCHAR)
 
students(student_id PK, register_number VARCHAR UNIQUE, name, gender, date_of_birth DATE,
  contact_number, email, department_id FK, admission_year INT, section, status VARCHAR,
  hostel_status VARCHAR,  -- 'Day Scholar' | 'Hosteller'
  cgpa NUMERIC)           -- status: 'Active' | 'Graduated' | 'Dropout'
 
parents(parent_id PK, student_id FK, father_name, mother_name,
  father_contact_number, mother_contact_number, address TEXT)
 
faculty(faculty_id PK, title, full_name, designation, email, phone,
  department_id FK, is_hod BOOLEAN, is_active BOOLEAN)
  -- faculty has NO day_of_week/slot_id/hour_number cols -- those live in faculty_timetable
 
subjects(subject_id PK, subject_code, subject_name, department_id FK, semester_number INT,
  subject_type VARCHAR,  -- 'Theory' | 'Practical' | 'Elective'
  lecture_hrs INT, tutorial_hrs INT, practical_hrs INT, credits INT)
 
student_subject_attempts(attempt_id PK, student_id FK, subject_id FK,
  exam_year INT, exam_month VARCHAR, grade VARCHAR)
  -- grade: 'O','A+','A','B+','B','C' = pass; 'U','AB' = fail
 
student_subject_results(id PK, student_id FK, subject_id FK, semester_number INT,
  grade, exam_year INT, exam_month VARCHAR)
 
student_semester_gpa(student_id FK, semester_number INT, gpa NUMERIC, total_credits INT)
 
faculty_timetable(tt_id PK, faculty_id FK, day_of_week VARCHAR, slot_id FK,
  subject_id FK, activity, sem_batch SMALLINT, department_id FK)
  -- day_of_week: 'Mon','Tue','Wed','Thu','Fri','Sat'
 
class_timetable(id PK, sem_batch INT, department_id FK, section, day_of_week VARCHAR,
  hour_number INT, subject_id FK, faculty_id FK, activity)
    -- use class_timetable.id (not tt_id) and class_timetable.hour_number (not slot_id)
    -- use class_timetable for subject/semester/section teaching assignments
 
time_slots(slot_id PK, hour_number INT, start_time TIME, end_time TIME, label)
 
vw_arrear_count(register_number, name, status, active_arrear_count)
 
current_semester = (EXTRACT(YEAR FROM CURRENT_DATE)::int - admission_year)*2
                   + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE)>=7 THEN 1 ELSE 0 END\
"""
 
# ── Result type ───────────────────────────────────────────────────────────────
class NlResult:
    def __init__(self, sql=None, model_used="none", confidence="low", error=None):
        self.sql        = sql
        self.model_used = model_used
        self.confidence = confidence
        self.error      = error
 
 
# ── Embedding cache (in-process, capped at 256 entries) ──────────────────────
_EMBED_CACHE: dict[str, list[float]] = {}
_EMBED_CACHE_MAX = 256
 
async def _cached_embed(text: str) -> list[float]:
    key = hashlib.md5(text.encode()).hexdigest()
    if key in _EMBED_CACHE:
        return _EMBED_CACHE[key]
    vec = await embed(text)
    if len(_EMBED_CACHE) >= _EMBED_CACHE_MAX:
        _EMBED_CACHE.pop(next(iter(_EMBED_CACHE)))
    _EMBED_CACHE[key] = vec
    return vec
 
 
# ── Department substitution ───────────────────────────────────────────────────
def _substitute_dept(text: str, department_code: str) -> str:
    return text.replace("{DEPT}", department_code)
 
 
def _resolve_examples(
    raw_examples: list[dict],
    department_code: str | None,
    is_central_admin: bool,
) -> list[dict]:
    if is_central_admin or not department_code:
        return raw_examples
    resolved = []
    for ex in raw_examples:
        resolved.append({
            "question": ex["question"],
            "sql":      _substitute_dept(ex["sql"], department_code),
            "tags":     ex.get("tags", []),
            "score":    ex.get("score"),
        })
    return resolved
 
 
# ── Post-generation safety: strip literal {DEPT} for admin users ─────────────
def _strip_dept_placeholder(sql: str, is_central_admin: bool) -> str:
    """
    If the model still emitted WHERE/AND department_code = '{DEPT}' for a
    central-admin query, remove it so the query actually runs correctly.
    """
    if not is_central_admin:
        return sql
    patterns = [
        r"\s*AND\s+d\.department_code\s*=\s*'?\{DEPT\}'?",
        r"\s*WHERE\s+d\.department_code\s*=\s*'?\{DEPT\}'?",
        r"\s*AND\s+department_code\s*=\s*'?\{DEPT\}'?",
        r"\s*WHERE\s+department_code\s*=\s*'?\{DEPT\}'?",
    ]
    for pat in patterns:
        sql = re.sub(pat, "", sql, flags=re.IGNORECASE)
    return sql.strip()
 
 
# ── Prompt builder ────────────────────────────────────────────────────────────
def _build_prompt(
    question:         str,
    examples:         list[dict],
    department_code:  str | None,
    is_central_admin: bool,
    extra_hint:       str = "",
    max_examples:     int | None = None,
) -> str:
    # Scope instruction
    if is_central_admin or not department_code:
        scope_block = (
            "\n-- ROLE: central administrator.\n"
            "-- Write queries spanning ALL departments.\n"
            "-- Do NOT add WHERE department_code = anything unless the question asks for a specific dept.\n"
        )
    else:
        scope_block = (
            f"\n-- ROLE: department user, dept='{department_code}'.\n"
            f"-- EVERY query MUST filter:\n"
            f"--   JOIN departments d ON <table>.department_id = d.department_id\n"
            f"--   WHERE d.department_code = '{department_code}'\n"
        )
 
    # Few-shot examples
    few_shot_block = ""
    if examples:
        few_shot_block = "\n### Examples\n"
        k = max_examples if max_examples is not None else TOP_K
        for ex in examples[:k]:
            few_shot_block += f"-- Q: {ex['question']}\n{ex['sql']}\n\n"
 
    hint_block = f"\n-- HINT: {extra_hint}\n" if extra_hint else ""
 
    rules = (
        "\n-- RULES: output ONE valid SELECT only, no explanation.\n"
        "-- day_of_week: 'Mon' 'Tue' 'Wed' 'Thu' 'Fri' 'Sat'.\n"
        "-- faculty_timetable ft is for faculty schedules/free periods; it uses slot_id, not hour_number.\n"
        "-- class_timetable ct is for subject/semester/section teaching assignments.\n"
        "-- if asking who teaches a subject for a semester/section, use class_timetable ct.\n"
        "-- class_timetable uses id and hour_number; never use tt_id or slot_id there.\n"
        "-- for class_timetable + time_slots, join ts.hour_number = ct.hour_number.\n"
        "-- for 'who is free' questions, DO NOT filter ft.activity='Free Period'; use NOT IN/NOT EXISTS over assigned ft slot rows.\n"
        "-- current_semester is derived from admission_year; use the formula, not a stored column.\n"
        "-- for 'relevant information regarding <person name>' queries, default to student profile lookup (students s) unless faculty-specific words appear.\n"
        "-- sem_batch is INTEGER, never ILIKE.\n"
    )
 
    return (
        f"{DB_SCHEMA}\n"
        f"{scope_block}"
        f"{few_shot_block}"
        f"{rules}"
        f"{hint_block}"
        f"-- Question: {question}\n"
        f"SELECT"   # primer — model continues from here
    )
 
 
# ── SQL cleaner ───────────────────────────────────────────────────────────────
def _clean_sql(raw: str) -> str:
    raw = re.sub(r"```(?:sql)?", "", raw, flags=re.IGNORECASE).strip("`").strip()
    lines = []
    for line in raw.splitlines():
        lines.append(line)
        if line.strip().endswith(";"):
            break
    sql = " ".join(lines).strip().rstrip(";").strip()
    match = re.search(r"\bSELECT\b", sql, re.IGNORECASE)
    if match:
        sql = sql[match.start():]
        sql = re.sub(r"^\s*SELECT\s+SELECT\b", "SELECT", sql, flags=re.IGNORECASE)
        return sql.strip()
    return ""
 
 
# ── Main RAG Engine ───────────────────────────────────────────────────────────
class RagEngine:
    """Role-aware NL-to-SQL engine with embedding cache and model warm-up."""
 
    def __init__(self):
        self.active_model: str | None = None
        self._admin_questions = [ex["question"] for ex in FEW_SHOTS]
        self._admin_vecs: list[list[float]] | None = None  # lazy-initialised
 
    # ── Model detection ───────────────────────────────────────────────────────
    async def _pick_model(self, client: httpx.AsyncClient) -> str | None:
        try:
            resp = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if resp.status_code == 200:
                available = [m["name"] for m in resp.json().get("models", [])]
                for preferred in [SQLCODER_MODEL, FALLBACK_MODEL, "llama3.2:1b"]:
                    for m in available:
                        if preferred.lower() in m.lower():
                            return m
                if available:
                    return available[0]
        except Exception as e:
            log.warning("Model detection failed: %s", e)
        return None
 
    async def detect_available_model(self) -> str | None:
        if MODE == "DATABRICKS":
            if not _databricks_chat_url():
                raise RuntimeError(
                    "Set DATABRICKS_CHAT_COMPLETIONS_URL or DATABRICKS_BASE_URL when MODE=DATABRICKS"
                )
            if not DATABRICKS_MODEL:
                raise RuntimeError("DATABRICKS_MODEL is required when MODE=DATABRICKS")
            self.active_model = DATABRICKS_MODEL
            log.info("Active model (databricks): %s", self.active_model)
            return self.active_model

        if MODE == "GROQ":
            if not _groq_chat_url():
                raise RuntimeError("Set GROQ_BASE_URL or GROQ_CHAT_COMPLETIONS_URL when MODE=GROQ")
            if not GROQ_MODEL:
                raise RuntimeError("GROQ_MODEL is required when MODE=GROQ")
            self.active_model = GROQ_MODEL
            log.info("Active model (groq): %s", self.active_model)
            return self.active_model

        async with httpx.AsyncClient() as client:
            model = await self._pick_model(client)
        if not model:
            raise RuntimeError(
                "No Ollama models found. Run: ollama pull sqlcoder  (or llama3.2)"
            )
        self.active_model = model
        log.info("Active model: %s", model)
        return model
 
    async def warm_up(self):
        """Pre-load model into VRAM so first real query is fast."""
        if not self.active_model:
            return
        if MODE in {"DATABRICKS", "GROQ"}:
            # External hosted models don't need local VRAM warm-up.
            log.info("Skipping warm-up for hosted provider mode=%s.", MODE)
            return
        try:
            async with httpx.AsyncClient(timeout=WARMUP_TIMEOUT_S) as client:
                await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model":      self.active_model,
                        "prompt":     "SELECT 1;",
                        "stream":     False,
                        "keep_alive": MODEL_KEEP_ALIVE,
                        "options": {"num_predict": 5},
                    },
                )
            log.info("Model warm-up complete.")
        except Exception as e:
            log.warning("Warm-up failed (non-fatal): %s", e)
 
    # ── Index ─────────────────────────────────────────────────────────────────
    async def index_examples(self):
        ensure_collection(recreate=False)
        info = collection_info()
        existing = int(info.get("points_count") or 0)

        delta = filter_new_or_changed_examples(FEW_SHOTS)
        if not delta:
            log.info("RAG index is up to date (%d points).", existing)
            return

        log.info(
            "RAG sync: %d total points, %d changed/new example(s) to upsert.",
            existing,
            len(delta),
        )
        questions = [ex["question"] for ex in delta]
        vectors = await embed_batch(questions)
        upsert_examples(delta, vectors)
        log.info("RAG sync complete — %d points.", collection_info()["points_count"])
 
    # ── Admin example retrieval (in-process cosine, no Qdrant call) ──────────
    async def _retrieve_admin_examples(self, query_vec: list[float]) -> list[dict]:
        if self._admin_vecs is None:
            self._admin_vecs = await embed_batch(self._admin_questions)
 
        import math
 
        def cosine(a: list[float], b: list[float]) -> float:
            dot  = sum(x * y for x, y in zip(a, b))
            norm = (
                math.sqrt(sum(x * x for x in a))
                * math.sqrt(sum(x * x for x in b))
            )
            return dot / norm if norm else 0.0
 
        scored = [
            (cosine(query_vec, vec), ex)
            for vec, ex in zip(self._admin_vecs, FEW_SHOTS)
        ]
        scored.sort(key=lambda t: t[0], reverse=True)
        return [ex for _, ex in scored[:TOP_K]]
 
    # ── Core generate ─────────────────────────────────────────────────────────
    async def generate(
        self,
        question:         str,
        role:             str  = "hod",
        extra_hint:       str  = "",
        department_code:  str | None = None,
        is_central_admin: bool = False,
    ) -> NlResult:
        if not self.active_model:
            try:
                await self.detect_available_model()
            except Exception as e:
                return NlResult(error=str(e))
 
        # 1. Embed (cached)
        query_vec = None
        try:
            query_vec = await _cached_embed(question)
        except Exception as e:
            log.warning("Embedding failed, skipping retrieval: %s", e)
 
        # 2. Retrieve examples — role-aware
        raw_examples: list[dict] = []
        if query_vec is not None:
            try:
                if is_central_admin:
                    raw_examples = await self._retrieve_admin_examples(query_vec)
                    log.info("RAG [admin]: %d admin examples retrieved", len(raw_examples))
                else:
                    raw_examples = qdrant_search(query_vec, top_k=TOP_K)
                    log.info("RAG [dept=%s]: %d examples", department_code, len(raw_examples))
            except Exception as e:
                log.warning("Example retrieval failed: %s", e)
 
        # 3. Substitute {DEPT} for dept users
        examples = _resolve_examples(raw_examples, department_code, is_central_admin)
 
        # 4. Build prompt
        is_retry = bool((extra_hint or "").strip())
        prompt = _build_prompt(
            question=question,
            examples=examples,
            department_code=department_code,
            is_central_admin=is_central_admin,
            extra_hint=extra_hint,
            max_examples=TOP_K if is_retry else min(TOP_K_FAST, TOP_K),
        )

        # 5. Generate via selected provider
        try:
            # Fast first pass keeps latency low; retry gets a larger budget for repairs.
            num_predict = NUM_PREDICT_REPAIR if is_retry else NUM_PREDICT_FAST
            num_ctx = NUM_CTX_REPAIR if is_retry else NUM_CTX_FAST

            async with httpx.AsyncClient(timeout=GEN_TIMEOUT_S) as client:
                async def _call_ollama() -> httpx.Response:
                    return await client.post(
                        f"{OLLAMA_URL}/api/generate",
                        json={
                            "model":      self.active_model,
                            "prompt":     prompt,
                            "stream":     False,
                            "keep_alive": MODEL_KEEP_ALIVE,
                            "options": {
                                "temperature":    0.0,
                                "num_predict":    num_predict,
                                "num_ctx":        num_ctx,
                                "stop":           ["--", "\n\n\n", "###", "Question:"],
                                "repeat_penalty": 1.1,
                            },
                        },
                    )

                if MODE in {"DATABRICKS", "GROQ"}:
                    if MODE == "DATABRICKS":
                        chat_url = _databricks_chat_url()
                        api_key = DATABRICKS_TOKEN
                    else:
                        chat_url = _groq_chat_url()
                        api_key = GROQ_API_KEY

                    headers = {"Content-Type": "application/json"}
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"

                    resp = await client.post(
                        chat_url,
                        headers=headers,
                        json={
                            "model": self.active_model,
                            "temperature": 0.0,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": (
                                        "You are a PostgreSQL SQL generator. "
                                        "Return exactly one valid SELECT query and nothing else."
                                    ),
                                },
                                {"role": "user", "content": prompt},
                            ],
                        },
                    )
                    if resp.status_code != 200:
                        openai_status = resp.status_code
                        body_text = (resp.text or "")[:500]
                        body_l = body_text.lower()
                        should_fallback = (
                            MODE_FALLBACK_PROVIDER == "ollama"
                            and (
                                openai_status == 404
                                or (
                                    openai_status == 403
                                    and ("rate limit" in body_l or "temporarily disabled" in body_l)
                                )
                            )
                        )

                        if should_fallback:
                            log.warning(
                                "%s provider returned %s for model '%s'. Falling back to Ollama provider.",
                                MODE,
                                resp.status_code,
                                self.active_model,
                            )
                            # For fallback, prefer locally configured SQL model.
                            local_model = SQLCODER_MODEL or self.active_model
                            if local_model and local_model != self.active_model:
                                self.active_model = local_model
                            resp = await _call_ollama()
                            if resp.status_code != 200:
                                return NlResult(
                                    error=(
                                        f"OpenAI-compatible {openai_status} and Ollama fallback failed "
                                        f"with {resp.status_code}: {resp.text[:200]}"
                                    )
                                )
                            raw = resp.json().get("response", "").strip()
                        elif openai_status == 403 and ("rate limit" in body_l or "temporarily disabled" in body_l):
                            return NlResult(
                                error=(
                                    f"{MODE} endpoint is temporarily disabled by provider policy: {body_text}. "
                                    "Ask platform admin to raise endpoint limits or switch MODE=OLLAMA."
                                )
                            )
                        else:
                            return NlResult(
                                error=(
                                    f"{MODE} OpenAI-compatible error {resp.status_code}: {body_text}. "
                                    "Verify model endpoint name and token permissions for the configured workspace."
                                )
                            )
                    else:
                        payload = resp.json()
                        raw = (
                            ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
                            or ""
                        ).strip()
                else:
                    resp = await _call_ollama()
                    if resp.status_code != 200:
                        return NlResult(
                            error=f"Ollama error {resp.status_code}: {resp.text[:200]}"
                        )

                    raw = resp.json().get("response", "").strip()
 
                # The prompt already ends with "SELECT", prepend if the model
                # omitted it (some models strip it back off)
                if not re.match(r"^\s*SELECT\b", raw, re.IGNORECASE):
                    raw = "SELECT " + raw
 
                clean = _clean_sql(raw)
 
                if not clean:
                    return NlResult(error="Model returned empty SQL")
 
                # Safety net: remove any lingering {DEPT} for admin users
                clean = _strip_dept_placeholder(clean, is_central_admin)
 
                confidence = "high" if clean.upper().startswith("SELECT") else "low"
                return NlResult(
                    sql=clean,
                    model_used=self.active_model,
                    confidence=confidence,
                )
 
        except httpx.TimeoutException:
            return NlResult(error="Request timed out — try a shorter question")
        except Exception as e:
            log.error("RAG generate error: %s", e)
            return NlResult(error=str(e))
 
    async def close(self):
        pass
 
 
# ── Singleton ─────────────────────────────────────────────────────────────────
_rag_engine = RagEngine()
 
 
def get_rag_engine() -> RagEngine:
    return _rag_engine
 