"""
core/intent.py
──────────────
Lightweight intent classifier and conversation state machine.

Runs entirely in-process — no LLM call needed for greetings, chitchat,
clarification loops, or obviously non-data questions.

Intent categories
─────────────────
  GREETING       hello / hi / good morning
  CHITCHAT       who are you / what can you do / thanks
  DATA_QUERY     anything that needs a DB lookup
  CLARIFY_DAY    user asked about "today's timetable" or "today" without a day
  CLARIFY_REPLY  user is replying to a clarification question (e.g. "tuesday")
  UNSAFE         model tried to generate DELETE/UPDATE/DROP/etc.

Conversation state (kept in the in-memory session store)
─────────────────────────────────────────────────────────
  pending_clarification: dict | None
    - type: "day"
    - original_question: str   — the question that needs a day
    - asked: str               — what we asked the user
"""

import re
from datetime import date
from typing import Optional

# ── Day helpers ───────────────────────────────────────────────────────────────
_DAY_MAP = {
    "monday": "Mon", "mon": "Mon",
    "tuesday": "Tue", "tue": "Tue", "tues": "Tue", "tuesady": "Tue", "teusday": "Tue",
    "wednesday": "Wed", "wed": "Wed", "wednesady": "Wed", "wednsday": "Wed", "wensday": "Wed",
    "thursday": "Thu", "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thrusday": "Thu", "thurday": "Thu",
    "friday": "Fri", "fri": "Fri",
    "saturday": "Sat", "sat": "Sat", "satuday": "Sat",
    "sunday": "Sun", "sun": "Sun",
}

_TODAY_WORDS = re.compile(r"\btoday(?:'s|s)?\b", re.IGNORECASE)
_TOMORROW_WORDS = re.compile(r"\btomorrow(?:'s|s)?\b", re.IGNORECASE)
_DAY_PATTERN = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|tuesady|teusday|wednesady|wednsday|wensday|thrusday|thurday|satuday"
    r"|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
    re.IGNORECASE,
)
_TIMETABLE_WORDS = re.compile(
    r"\b(timetable|schedule|class(?:es)?|period|slot|hour)\b", re.IGNORECASE
)

_DATA_CUES = re.compile(
    r"\b(show|list|get|fetch|find|how many|count|which|who|what|students?|faculty|arrear|subject|"
    r"timetable|schedule|semester|batch|hostel|cgpa|gpa|department|phone|contact|email)\b",
    re.IGNORECASE,
)

# Likely entity lookup without explicit verbs, e.g. "ruban s" or a register number.
_ENTITY_LOOKUP = re.compile(
    # register number OR at least two name-like tokens; single words are ambiguous
    r"^\s*(?:\d{8,14}|[A-Za-z]+(?:\s+[A-Za-z\.]+){1,3})\s*[?.!]*\s*$",
    re.IGNORECASE,
)

# words that signal the user is JUST giving a day as a reply
_BARE_DAY_REPLY = re.compile(
    r"^\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|tuesady|teusday|wednesady|wednsday|wensday|thrusday|thurday|satuday"
    r"|mon|tue|tues|wed|thu|thur|thurs|fri|sat)\s*$",
    re.IGNORECASE,
)

# unsafe DML patterns
_UNSAFE_SQL = re.compile(
    r"\b(DELETE|UPDATE|INSERT|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE)\b",
    re.IGNORECASE,
)

# greeting patterns
_GREETING = re.compile(
    r"^\s*(hi+|hello+|hey+|hii+|good\s*(morning|afternoon|evening|day)|howdy)\s*[!.?]?\s*$",
    re.IGNORECASE,
)

# Allow compound greeting-only phrases like: "hello hey there", "hey hi"
_GREETING_COMPOUND = re.compile(
    r"^\s*(?:"
    r"hi+|hello+|hey+|hey\s+there|hii+|howdy|"
    r"good\s*(?:morning|afternoon|evening|day)|"
    r"there|yo|sup"
    r")(?:[\s,!.?]+(?:"
    r"hi+|hello+|hey+|hey\s+there|hii+|howdy|"
    r"good\s*(?:morning|afternoon|evening|day)|"
    r"there|yo|sup"
    r"))*\s*$",
    re.IGNORECASE,
)

# chitchat patterns
_CHITCHAT_WHO = re.compile(r"\b(who are you|what (are|can) you|help me?|what do you do)\b", re.IGNORECASE)
_CHITCHAT_THANKS = re.compile(
    r"^\s*"
    r"(?:(?:cool|ok(?:ay)?|great|awesome|nice|fine|alright)\s+)?"
    r"(?:thank(?:s|\s+you)|thx|cheers|got\s+it|perfect)"
    r"(?:\s+(?:bro|sir|mate|man|dear|thanks))?"
    r"\s*[!.?]*\s*$",
    re.IGNORECASE,
)
_CHITCHAT_ACK = re.compile(
    r"^\s*(welcome|ok(?:ay)?|sure|fine|alright|noted|cool|great|nice|yes|no|yep|nope)\s*[!.?]*\s*$",
    re.IGNORECASE,
)
_CHITCHAT_FEATURES = re.compile(
    r"\b(explain|tell me|what are|describe)\b.*\b(features?|website|web\s*app|application|system|portal)\b"
    r"|\b(features?\s+of\s+the\s+(?:website|app|application|system|portal))\b",
    re.IGNORECASE,
)

_DEPARTMENT_MISMATCH = re.compile(
    r"\b(all\s+departments?|entire\s+college|all\s+branches?|whole\s+college|every\s+department)\b",
    re.IGNORECASE,
)

_KNOWN_DEPARTMENTS = {
    "AIML": re.compile(r"\b(ai\s*&\s*ml|aiml|a i m l|artificial\s+intelligence\s+and\s+machine\s+learning)\b", re.IGNORECASE),
    "DCS": re.compile(r"\b(dcs|decision\s+and\s+computing\s+sciences|decision\s+computing\s+sciences)\b", re.IGNORECASE),
    "CSE": re.compile(r"\b(cse|computer\s+science)\b", re.IGNORECASE),
    "ECE": re.compile(r"\b(ece|electronics\s+and\s+communication)\b", re.IGNORECASE),
    "IT": re.compile(r"\b(it|information\s+technology)\b", re.IGNORECASE),
    "EEE": re.compile(r"\b(eee|electrical\s+and\s+electronics)\b", re.IGNORECASE),
    "MECH": re.compile(r"\b(mech|mechanical)\b", re.IGNORECASE),
    "CIVIL": re.compile(r"\b(civil)\b", re.IGNORECASE),
    "AIDS": re.compile(r"\b(ai\s*&\s*ds|aids|artificial\s+intelligence\s+and\s+data\s+science)\b", re.IGNORECASE),
}

# Responsible-usage guardrail: refuse bulk personal data, secrets, or abusive requests.
_RESPONSIBLE_USAGE_BLOCKED = re.compile(
    r"\b(" 
    r"passwords?|passcodes?|passwd|passwrd|passw?d|pswd|psswd|pwd|otp|one\s*time\s*password|secret|api\s*key|token|private\s*key|"
    r"personal\s*data|pii|sensitive\s*data|private\s*info|confidential|leak|dump|exfiltrate|"
    r"all\s+(?:students?|faculty|parents?)\s+(?:contact|phone|mobile|email|address)s?|"
    r"(?:contact|phone|mobile|email|address)s?\s+of\s+all\s+(?:students?|faculty|parents?)|"
    r"parent\s+contact\s+details|father\s+contact\s+numbers?|mother\s+contact\s+numbers?"
    r")\b",
    re.IGNORECASE,
)


def today_day_code() -> str:
    """Return today's DB day code (Mon/Tue/...)."""
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][date.today().weekday()]


def normalize_day(text: str) -> Optional[str]:
    """Extract the first weekday mention and return its DB code (Mon/Tue/...)."""
    m = _DAY_PATTERN.search(text)
    if m:
        return _DAY_MAP.get(m.group(1).lower())
    return None


def resolve_relative_days(question: str) -> str:
    """
    Resolve relative day words to concrete weekday names using system date.
    e.g. "... today" -> "... on Monday", "... tomorrow" -> "... on Tuesday"
    """
    if not (_TODAY_WORDS.search(question) or _TOMORROW_WORDS.search(question)):
        return question
    # don't substitute if an explicit day already appears
    if _DAY_PATTERN.search(question):
        return question

    offset = 1 if _TOMORROW_WORDS.search(question) else 0
    day_idx = (date.today().weekday() + offset) % 7
    day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day_idx]
    full_names = {
        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
        "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
    }
    full = full_names[day]
    text = _TODAY_WORDS.sub(f"on {full}", question)
    text = _TOMORROW_WORDS.sub(f"on {full}", text)
    return text


# ── Intent classification ─────────────────────────────────────────────────────

class Intent:
    GREETING       = "greeting"
    CHITCHAT       = "chitchat"
    DATA_QUERY     = "data_query"
    CLARIFY_DAY    = "clarify_day"        # we need to ask what day
    CLARIFY_REPLY  = "clarify_reply"      # user replied with a day
    UNSAFE         = "unsafe"


def is_responsible_usage_blocked(question: str) -> bool:
    q = (question or "").strip()
    return bool(q and _RESPONSIBLE_USAGE_BLOCKED.search(q))


def responsible_usage_reply(question: str) -> str:
    ql = (question or "").lower()
    if any(k in ql for k in ["password", "passwd", "passwrd", "pswd", "psswd", "pwd", "otp", "secret", "token", "api key", "private key"]):
        return (
            "I can’t help retrieve secrets, passwords, OTPs, API keys, or private tokens. "
            "For safety, keep those out of chat and use your official access controls instead."
        )

    if _DEPARTMENT_MISMATCH.search(question or ""):
        return (
            "I can’t provide cross-department or whole-college data for a department-scoped login. "
            "Please ask about your own department or use an admin account for broader access."
        )

    for code, pattern in _KNOWN_DEPARTMENTS.items():
        if pattern.search(question or ""):
            return (
                f"I can’t provide {code} data from this login because it is scoped to your department. "
                "Please ask about your own department or use an admin account for other department data."
            )

    return (
        "I can help with academic data, but I won’t assist with bulk personal-data exports or sensitive details "
        "unless the request is clearly authorized and narrowly scoped. Try a safer request like: "
        '"How many students are in 8th semester?" or "Show the timetable for Tuesday 3rd hour."'
    )


def classify(
    question: str,
    pending: Optional[dict],
    department_code: Optional[str] = None,
    is_central_admin: bool = False,
) -> dict:
    """
    Classify the user's intent.

    Returns a dict:
      {
        "intent":   Intent.*,
        "question": str,    # possibly modified (today resolved, day injected)
        "day":      str | None,
        "pending":  dict | None,  # new pending clarification state (if any)
      }
    """
    q = (question or "").strip()
    ql = q.lower()

    if is_responsible_usage_blocked(q):
        return {"intent": Intent.UNSAFE, "question": q, "day": None, "pending": None}

    if not is_central_admin and department_code:
        dept = department_code.strip().lower()
        if _DEPARTMENT_MISMATCH.search(q):
            return {"intent": Intent.UNSAFE, "question": q, "day": None, "pending": None}
        for code, pattern in _KNOWN_DEPARTMENTS.items():
            if code.lower() != dept and pattern.search(q):
                return {"intent": Intent.UNSAFE, "question": q, "day": None, "pending": None}

    # ── Check if user is replying to a pending clarification ─────────────────
    if pending and pending.get("type") == "day":
        # bare day reply like "tuesday" or "on tuesday"
        bare = _BARE_DAY_REPLY.match(q)
        day_in_text = normalize_day(q)
        if bare or day_in_text:
            day = day_in_text or normalize_day(bare.group(1)) if bare else None
            if day is None:
                day = today_day_code()
            # reconstruct the full question
            orig = pending["original_question"]
            full_q = _inject_day(orig, day)
            return {
                "intent":   Intent.CLARIFY_REPLY,
                "question": full_q,
                "day":      day,
                "pending":  None,
            }

    # ── Greeting ─────────────────────────────────────────────────────────────
    if (_GREETING.match(q) or _GREETING_COMPOUND.match(q)) and not _DATA_CUES.search(q):
        return {"intent": Intent.GREETING, "question": q, "day": None, "pending": None}

    # ── Chitchat ─────────────────────────────────────────────────────────────
    if _CHITCHAT_WHO.search(ql) or _CHITCHAT_THANKS.match(q) or _CHITCHAT_ACK.match(q) or _CHITCHAT_FEATURES.search(ql):
        return {"intent": Intent.CHITCHAT, "question": q, "day": None, "pending": None}

    # ── Resolve relative days (today/tomorrow) → weekday ──────────────────────
    resolved_q = resolve_relative_days(q)

    # ── Timetable question with no day mentioned at all ───────────────────────
    if _TIMETABLE_WORDS.search(resolved_q) and not _DAY_PATTERN.search(resolved_q):
        # needs clarification
        new_pending = {"type": "day", "original_question": resolved_q}
        return {
            "intent":   Intent.CLARIFY_DAY,
            "question": resolved_q,
            "day":      None,
            "pending":  new_pending,
        }

    # If no clear data cue exists, avoid blind SQL generation that can drift
    # to broad default lists (often full student tables).
    if not _DATA_CUES.search(resolved_q) and not _ENTITY_LOOKUP.match(resolved_q):
        return {
            "intent": Intent.CHITCHAT,
            "question": q,
            "day": None,
            "pending": None,
        }

    return {
        "intent":   Intent.DATA_QUERY,
        "question": resolved_q,
        "day":      normalize_day(resolved_q),
        "pending":  None,
    }


def is_safe_sql(sql: str) -> bool:
    """Return True if the SQL is a pure SELECT (no DML)."""
    if not sql:
        return False
    stripped = sql.strip()
    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        return False
    if _UNSAFE_SQL.search(stripped):
        return False
    return True


def unsafe_sql_reply() -> str:
    return (
        "I'm only allowed to read data, not make changes. "
        "It looks like my attempt to answer that question generated a write command. "
        "Please try rephrasing — for example: 'Show me students with arrears' instead of an update request."
    )


# ── Greeting / chitchat replies ───────────────────────────────────────────────
def greeting_reply(department_code: Optional[str]) -> str:
    dept_txt = f" for the **{department_code}** department" if department_code else ""
    return (
        f"Hi there! 👋 I'm your college data assistant{dept_txt}.\n\n"
        "I can help you with:\n"
        "- 📊 **Student info** — active students, batch lists, CGPA, hostellers\n"
        "- 📅 **Timetables** — class schedules, faculty timetables, free slots\n"
        "- ⚠️ **Arrears** — who has backlogs, subject-wise arrear counts\n"
        "- 👩‍🏫 **Faculty** — designations, workload, who teaches what\n\n"
        "Try asking: *\"Show 7th semester students\"* or *\"Which faculty are free on Monday 3rd hour?\"*"
    )


def chitchat_reply(question: str, department_code: Optional[str]) -> str:
    ql = question.lower()
    if _CHITCHAT_THANKS.match(question):
        return "You're welcome! 😊 Feel free to ask anything else about the department data."
    if _CHITCHAT_ACK.match(question):
        return "Happy to help. Ask me anything about students, faculty, arrears, or timetables when you're ready."
    if _CHITCHAT_FEATURES.search(ql):
        return (
            "This portal supports key academic workflows:\n\n"
            "- Dashboard overview of department insights\n"
            "- Student records with semester, CGPA, hostel and status filters\n"
            "- Faculty details and timetable/free-slot lookups\n"
            "- Subject and arrear analytics\n"
            "- Timetable and data upload modules\n"
            "- Ask AI for natural-language queries over your department data\n\n"
            "You can also rate AI responses with 👍/👎 to help improve future results."
        )
    if "who are you" in ql:
        return (
            "I'm your college academic data assistant — connected directly to your department's database. "
            "I can look up student records, timetables, arrear reports, faculty schedules, and more. "
            "Just ask naturally and I'll fetch the data for you."
        )
    return (
        "I can help you explore your college database. Here are some things you can ask:\n\n"
        "- *\"List active students in 6th semester\"*\n"
        "- *\"Show today's timetable for 4th semester\"*\n"
        "- *\"Which students have more than 2 arrears?\"*\n"
        "- *\"Who teaches on Thursday 2nd hour?\"*\n\n"
        "What would you like to know?"
    )


def clarify_day_reply(question: str) -> str:
    # try to extract the semester from the question for a friendlier ask
    sem_match = re.search(r"(\d+)(?:st|nd|rd|th)?\s+sem", question, re.IGNORECASE)
    sem_txt = f" for {sem_match.group(1)}th semester" if sem_match else ""
    return (
        f"Sure! Which day would you like the timetable{sem_txt} for? "
        f"*(e.g. Monday, Tuesday, … or just say \"today\")*"
    )


# ── Internal helpers ──────────────────────────────────────────────────────────
def _inject_day(question: str, day_code: str) -> str:
    """Append 'on <DayName>' to a question that has no day mention."""
    full_names = {
        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
        "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
    }
    day_name = full_names.get(day_code, day_code)
    # remove any leftover relative-day references
    q = _TODAY_WORDS.sub("", question)
    q = _TOMORROW_WORDS.sub("", q).strip()
    return f"{q} on {day_name}"