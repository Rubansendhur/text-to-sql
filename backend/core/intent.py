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
from difflib import get_close_matches
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
_TOMORROW_WORDS = re.compile(
    r"\b(?:tomorrow|tommorow|tomoorow|tommorrow|tommorow|tommorrow|tommmoorw|tmrw|tmr)\b",
    re.IGNORECASE,
)
_DAY_PATTERN = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|tuesady|teusday|wednesady|wednsday|wensday|thrusday|thurday|satuday"
    r"|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
    re.IGNORECASE,
)
_TIMETABLE_WORDS = re.compile(
    r"\b(timetable|schedule|class(?:es)?|period|slot|hour)\b", re.IGNORECASE
)

_MONTH_TO_NUM = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
# Accept broad month tokens and normalize with typo tolerance (e.g., "arpil" -> "april").
_DATE_DMY = re.compile(r"\b([0-3]?\d)\s*(?:st|nd|rd|th)?\s*(?:of\s+)?([A-Za-z]{3,10})\b", re.IGNORECASE)
_DATE_MDY = re.compile(r"\b([A-Za-z]{3,10})\s*([0-3]?\d)\s*(?:st|nd|rd|th)?\b", re.IGNORECASE)

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
_YES_REPLY = re.compile(r"^\s*(yes|yep|yeah|ya|ok|okay|sure|continue|proceed)\s*[!.?]*\s*$", re.IGNORECASE)
_NO_REPLY = re.compile(r"^\s*(no|nope|nah|not now|cancel)\s*[!.?]*\s*$", re.IGNORECASE)

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
_CHITCHAT_WORKING_DAY = re.compile(
    r"\b(working\s*day|non-?working|holiday|weekend|off\s*day)\b"
    r"|\b(is|are)\b.*\b(saturday|sunday|sat|sun|today|tomorrow|tmr|tmrw)\b.*\b(working|holiday|off)\b"
    r"|\b(saturday|sunday|sat|sun|today|tomorrow|tmr|tmrw)\b.*\bworking\s*day\b",
    re.IGNORECASE,
)
_CHITCHAT_DAY_STATEMENT = re.compile(
    r"\b(today|tomorrow|tmr|tmrw)\b\s+\b(is|=)\b\s+"
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b",
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


def _remove_day_mentions(text: str) -> str:
    """Remove explicit weekday mentions so a clarified day can be injected cleanly."""
    if not text:
        return text
    cleaned = re.sub(
        r"\b(?:on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        r"|tuesady|teusday|wednesady|wednsday|wensday|thrusday|thurday|satuday"
        r"|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
    return cleaned or text


def _extract_day_code(text: str) -> Optional[str]:
    """Resolve weekday token from direct/relative/explicit-date text."""
    if not text:
        return None
    direct = normalize_day(text)
    if direct:
        return direct
    resolved = resolve_relative_days(text)
    return normalize_day(resolved)


def resolve_relative_days(question: str) -> str:
    """
    Resolve relative day words to concrete weekday names using system date.
    e.g. "... today" -> "... on Monday", "... tomorrow" -> "... on Tuesday"
    """
    has_relative = bool(_TODAY_WORDS.search(question) or _TOMORROW_WORDS.search(question))
    has_explicit_date = bool(_DATE_DMY.search(question) or _DATE_MDY.search(question))
    if not (has_relative or has_explicit_date):
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

    # Resolve explicit date mentions like "18th Apr" or "Apr 18th" using system year.
    # If an explicit weekday is already present, we leave the question unchanged.
    if _DAY_PATTERN.search(text):
        return text

    def _normalize_month(month_str: str) -> str | None:
        token = (month_str or "").strip().lower()
        if not token:
            return None
        if token in _MONTH_TO_NUM:
            return token
        # Common misspellings/shorthand for robustness.
        alias = {
            "janurary": "january", "febuary": "february", "fabruary": "february",
            "marhc": "march", "april": "april", "arpil": "april", "aprill": "april",
            "agust": "august", "auguest": "august", "setp": "sept", "sepember": "september",
            "octomber": "october", "novembar": "november", "decembar": "december",
        }
        if token in alias:
            return alias[token]
        close = get_close_matches(token, list(_MONTH_TO_NUM.keys()), n=1, cutoff=0.78)
        return close[0] if close else None

    def _weekday_for(day_str: str, month_str: str) -> str | None:
        try:
            day_num = int(day_str)
        except Exception:
            return None
        month_key = _normalize_month(month_str)
        month_num = _MONTH_TO_NUM.get(month_key) if month_key else None
        if not month_num:
            return None
        try:
            d = date(date.today().year, month_num, day_num)
        except ValueError:
            return None
        return d.strftime("%A")

    m = _DATE_DMY.search(text)
    if m:
        weekday = _weekday_for(m.group(1), m.group(2))
        if weekday:
            return text[:m.start()] + f"on {weekday}" + text[m.end():]

    m = _DATE_MDY.search(text)
    if m:
        weekday = _weekday_for(m.group(2), m.group(1))
        if weekday:
            return text[:m.start()] + f"on {weekday}" + text[m.end():]

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
        orig = pending.get("original_question") or q
        reason = (pending.get("reason") or "").strip().lower()

        # Weekend follow-up acknowledgements.
        if reason == "weekend" and _YES_REPLY.match(q):
            weekend_day = pending.get("weekend_day") or "Sat"
            full_q = _inject_day(orig, weekend_day)
            return {
                "intent": Intent.CLARIFY_REPLY,
                "question": full_q,
                "day": weekend_day,
                "pending": None,
            }

        if reason == "weekend" and _NO_REPLY.match(q):
            return {
                "intent": Intent.CLARIFY_DAY,
                "question": orig,
                "day": None,
                "pending": {
                    "type": "day",
                    "original_question": orig,
                    "reason": "weekend_need_working_day",
                },
            }

        # Accept explicit weekday, today/tomorrow, or explicit date replies.
        day = _extract_day_code(q)
        if day:
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
    if (
        _CHITCHAT_WHO.search(ql)
        or _CHITCHAT_THANKS.match(q)
        or _CHITCHAT_ACK.match(q)
        or _CHITCHAT_FEATURES.search(ql)
        or _CHITCHAT_WORKING_DAY.search(ql)
        or _CHITCHAT_DAY_STATEMENT.search(ql)
    ):
        return {"intent": Intent.CHITCHAT, "question": q, "day": None, "pending": None}

    # ── Resolve relative days (today/tomorrow) → weekday ──────────────────────
    resolved_q = resolve_relative_days(q)

    # ── Timetable-day handling ───────────────────────────────────────────────
    if _TIMETABLE_WORDS.search(resolved_q):
        day_code = normalize_day(resolved_q)

        # Weekend query: ask user to confirm weekend classes / provide working day.
        if day_code in {"Sat", "Sun"}:
            base_q = _remove_day_mentions(resolved_q)
            new_pending = {
                "type": "day",
                "original_question": base_q,
                "reason": "weekend",
                "weekend_day": day_code,
            }
            return {
                "intent":   Intent.CLARIFY_DAY,
                "question": base_q,
                "day":      None,
                "pending":  new_pending,
            }

        # No day at all: ask normal clarification.
        if not _DAY_PATTERN.search(resolved_q):
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
    if _CHITCHAT_WORKING_DAY.search(ql):
        day = _extract_day_code(question)
        if day == "Sun":
            return (
                "In this setup, **Sunday is treated as a non-working day**, "
                "so timetable/free-slot results are not available for Sunday."
            )
        if day == "Sat":
            return (
                "**Saturday can vary by timetable policy**. "
                "If your department runs Saturday classes, share the exact hour/day query and I will fetch it; "
                "otherwise we can use a working weekday."
            )
        if day in {"Mon", "Tue", "Wed", "Thu", "Fri"}:
            return "Yes, that is treated as a **working day** in this timetable flow."
        return (
            "Working-day policy here is: **Sunday is non-working**, "
            "and weekday queries are supported directly. "
            "For Saturday, it depends on your department timetable policy."
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