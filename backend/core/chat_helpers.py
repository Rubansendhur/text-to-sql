"""
core/chat_helpers.py
Utility helpers used by routers/chat.py.
"""

import os
import re
from datetime import date
from fastapi import Request
from core.rag_engine import get_rag_engine

import logging
logger = logging.getLogger(__name__)

USE_RULE_SQL_FALLBACK = os.getenv("USE_RULE_SQL_FALLBACK", "false").lower() == "true"

_TIMETABLE_COL_ERR = {"day_of_week", "slot_id", "hour_number", "activity", "sem_batch"}


def is_timetable_col_error(error_str: str) -> bool:
    if "UndefinedColumn" not in error_str and "undefined_column" not in error_str.lower():
        return False
    return any(col in error_str for col in _TIMETABLE_COL_ERR)


def has_department_scope(sql: str, department_code: str) -> bool:
    txt = (sql or "").lower()
    return "department_code" in txt and department_code.lower() in txt


def get_legacy_engine():
    """Fallback to the shared RAG engine when app state has no cached engine."""
    return get_rag_engine()


def get_engine(request: Request):
    """Return the NL engine stored on app state (RAG or legacy)."""
    return getattr(request.app.state, "nl_engine", None) or get_legacy_engine()


def inject_scope_predicate(sql: str, predicate: str) -> str:
    """Inject predicate into main query before GROUP/ORDER/LIMIT/OFFSET at top-level only.
    
    Respects parentheses depth to avoid inserting inside window functions or subqueries.
    Only matches keywords at depth 0 (outside all parentheses).
    """
    if not sql or not predicate:
        return sql

    # Scan for top-level (depth=0) clause keywords
    depth = 0
    in_string = False
    string_char = None
    first_clause_pos = None
    
    i = 0
    while i < len(sql):
        ch = sql[i]
        
        # Track quoted strings to avoid matching keywords inside them
        if ch in ("'", '"') and (i == 0 or sql[i-1] != "\\"):
            if not in_string:
                in_string = True
                string_char = ch
            elif ch == string_char:
                in_string = False
                string_char = None
        
        if in_string:
            i += 1
            continue
        
        # Track parentheses depth (only outside strings)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        
        # At top level (depth 0), look for clause keywords
        if depth == 0:
            rest_upper = sql[i:i+10].upper()
            for kw in ["GROUP BY", "ORDER BY", "LIMIT", "OFFSET"]:
                if rest_upper.startswith(kw):
                    # Verify word boundary
                    before_ok = i == 0 or (sql[i-1] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
                    after_ok = i + len(kw) >= len(sql) or (sql[i+len(kw)] not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
                    if before_ok and after_ok:
                        first_clause_pos = i
                        break
            
            if first_clause_pos is not None:
                break
        
        i += 1
    
    # Split and build result
    if first_clause_pos is not None:
        body = sql[:first_clause_pos].rstrip()
        tail = sql[first_clause_pos:]
    else:
        body = sql.rstrip()
        tail = ""
    
    # Add WHERE or AND
    if re.search(r"\bWHERE\b", body, flags=re.IGNORECASE):
        body = f"{body} AND {predicate}"
    else:
        body = f"{body} WHERE {predicate}"
    
    return (f"{body} {tail}" if tail else body).strip()


def force_department_scope(sql: str, department_code: str) -> str:
    """
    Add deterministic department scope for common table aliases when model forgets it.
    Uses EXISTS to avoid changing SELECT/GROUP BY columns.
    """
    if not sql or not department_code:
        return sql

    alias_map: dict[str, str] = {}
    sql_keywords = {
        "where", "join", "left", "right", "inner", "outer", "full",
        "on", "group", "order", "limit", "offset", "having", "union",
    }

    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][\w]*)(?:\s+(?:AS\s+)?([a-zA-Z_][\w]*))?\b",
        sql,
        flags=re.IGNORECASE,
    ):
        table = m.group(1).lower()
        raw_alias = (m.group(2) or "").strip()
        alias = raw_alias if raw_alias and raw_alias.lower() not in sql_keywords else table
        alias_map[table] = alias

    anchor_alias = (
        alias_map.get("students")
        or alias_map.get("faculty")
        or alias_map.get("subjects")
        or alias_map.get("class_timetable")
        or alias_map.get("faculty_timetable")
    )
    if not anchor_alias:
        return sql

    predicate = (
        "EXISTS ("
        "SELECT 1 FROM departments d_scope "
        f"WHERE d_scope.department_id = {anchor_alias}.department_id "
        f"AND d_scope.department_code = '{department_code}'"
        ")"
    )
    return inject_scope_predicate(sql, predicate)


def normalize_sql(sql: str) -> str:
    """Apply lightweight SQL normalization before execution."""
    if not sql:
        return sql
    sql = re.sub(r"^\s*SELECT\s+SELECT\b", "SELECT", sql, flags=re.IGNORECASE).strip()

    alias_map: dict[str, str] = {}
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][\w]*)\s+(?:AS\s+)?([a-zA-Z_][\w]*)\b",
        sql,
        flags=re.IGNORECASE,
    ):
        table = m.group(1).lower()
        alias = m.group(2)
        alias_map[alias] = table

    # In this schema, day_of_week lives on faculty_timetable (ft), not time_slots (ts).
    if re.search(r"\bfaculty_timetable\s+(?:AS\s+)?ft\b", sql, flags=re.IGNORECASE):
        sql = re.sub(r"\bts\s*\.\s*day_of_week\b", "ft.day_of_week", sql, flags=re.IGNORECASE)

    # current_semester is derived from admission_year, not a stored column.
    semester_expr_template = (
        "(EXTRACT(YEAR FROM CURRENT_DATE)::int - {alias}.admission_year) * 2 "
        "+ CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END"
    )
    for alias, table in alias_map.items():
        if table == "students":
            sql = re.sub(
                rf"\b{re.escape(alias)}\s*\.\s*current_semester\b",
                semester_expr_template.format(alias=alias),
                sql,
                flags=re.IGNORECASE,
            )

    # class_timetable uses id + hour_number, not tt_id/slot_id.
    class_timetable_aliases = [alias for alias, table in alias_map.items() if table == "class_timetable"]
    time_slots_aliases = [alias for alias, table in alias_map.items() if table == "time_slots"]
    for ct_alias in class_timetable_aliases:
        sql = re.sub(rf"\b{re.escape(ct_alias)}\s*\.\s*tt_id\b", f"{ct_alias}.id", sql, flags=re.IGNORECASE)
        sql = re.sub(rf"\b{re.escape(ct_alias)}\s*\.\s*slot_id\b", f"{ct_alias}.hour_number", sql, flags=re.IGNORECASE)
        for ts_alias in time_slots_aliases:
            sql = re.sub(
                rf"\b{re.escape(ts_alias)}\s*\.\s*slot_id\s*=\s*{re.escape(ct_alias)}\s*\.\s*slot_id\b",
                f"{ts_alias}.hour_number = {ct_alias}.hour_number",
                sql,
                flags=re.IGNORECASE,
            )
            sql = re.sub(
                rf"\b{re.escape(ct_alias)}\s*\.\s*slot_id\s*=\s*{re.escape(ts_alias)}\s*\.\s*slot_id\b",
                f"{ct_alias}.hour_number = {ts_alias}.hour_number",
                sql,
                flags=re.IGNORECASE,
            )

    # If query references ts.* but time_slots is not joined, inject the LEFT JOIN.
    # This catches LLM SQL that uses ts.hour_number/ts.start_time in SELECT/ORDER BY
    # but forgets to include LEFT JOIN time_slots ts ON ft.slot_id = ts.slot_id.
    if re.search(r"\bts\s*\.\s*\w+\b", sql, flags=re.IGNORECASE):
        if not re.search(r"\btime_slots\b", sql, flags=re.IGNORECASE):
            if re.search(r"\bfaculty_timetable\b", sql, flags=re.IGNORECASE):
                # Inject after the faculty JOIN if present, else after faculty_timetable
                injected = " LEFT JOIN time_slots ts ON ft.slot_id = ts.slot_id"
                # Try to insert after "JOIN faculty f ON ft.faculty_id = f.faculty_id"
                faculty_join_pat = re.compile(
                    r"(JOIN\s+faculty\s+(?:AS\s+)?f\s+ON\s+ft\.faculty_id\s*=\s*f\.faculty_id)",
                    re.IGNORECASE
                )
                if faculty_join_pat.search(sql):
                    sql = faculty_join_pat.sub(r"\1" + injected, sql, count=1)
                else:
                    # Fallback: inject before WHERE
                    where_match = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
                    if where_match:
                        sql = sql[:where_match.start()] + injected + " " + sql[where_match.start():]

    alias_map: dict[str, str] = {}
    for m in re.finditer(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][\w]*)\s+(?:AS\s+)?([a-zA-Z_][\w]*)\b",
        sql,
        flags=re.IGNORECASE,
    ):
        table = m.group(1).lower()
        alias = m.group(2)
        alias_map[alias] = table

    pk_map = {
        "students": "student_id",
        "faculty": "faculty_id",
        "subjects": "subject_id",
        "departments": "department_id",
        "student_subject_attempts": "attempt_id",
        "faculty_timetable": "tt_id",
        "class_timetable": "id",
        "time_slots": "slot_id",
    }

    def _count_fix(match: re.Match) -> str:
        alias = match.group(1)
        table = alias_map.get(alias)
        if not table:
            return match.group(0)
        pk = pk_map.get(table)
        if not pk:
            return match.group(0)
        return f"COUNT({alias}.{pk})"

    sql = re.sub(r"COUNT\(\s*([a-zA-Z_][\w]*)\s*\.\s*id\s*\)", _count_fix, sql, flags=re.IGNORECASE)

    # Free-faculty queries must use occupancy logic, not activity literal checks.
    # Some generated SQL incorrectly assumes ft.activity='Free Period'.
    if re.search(r"\bft\s*\.\s*activity\s*=\s*'\s*free\s*period\s*'", sql, flags=re.IGNORECASE):
        day_match = re.search(r"\bft\s*\.\s*day_of_week\s*=\s*'([A-Za-z]{3})'", sql, flags=re.IGNORECASE)
        hour_match = re.search(r"\bts\s*\.\s*hour_number\s*=\s*(\d{1,2})", sql, flags=re.IGNORECASE)
        dept_match = re.search(r"\b[a-zA-Z_][\w]*\s*\.\s*department_code\s*=\s*'([^']+)'", sql, flags=re.IGNORECASE)

        if day_match and hour_match:
            day = day_match.group(1)
            hour = int(hour_match.group(1))
            dept = dept_match.group(1) if dept_match else None

            where_parts = ["f.is_active = TRUE"]
            if dept:
                where_parts.insert(0, f"d.department_code = '{sql_quote(dept)}'")

            sql = (
                "SELECT f.full_name, f.designation "
                "FROM faculty f "
                "JOIN departments d ON f.department_id = d.department_id "
                f"WHERE {' AND '.join(where_parts)} "
                "AND f.faculty_id NOT IN ("
                "SELECT ft.faculty_id "
                "FROM faculty_timetable ft "
                "JOIN time_slots ts ON ft.slot_id = ts.slot_id "
                f"WHERE ft.day_of_week = '{day}' "
                f"AND ts.hour_number = {hour}"
                ") "
                "ORDER BY f.full_name"
            )

    # Make person-name searches resilient to minor spelling variations.
    # Handles repeated letters and vowel drift (e.g., bhavatharaini vs bhavatharini).
    def _name_expr(col_sql: str) -> str:
        return (
            "regexp_replace(" 
            "regexp_replace(" 
            f"lower({col_sql}), "
            "'(.)\\1+', '\\1', 'g'"
            "), "
            "'[^a-z]', '', 'g'"
            ")"
        )

    def _expand_name_clause(col_sql: str, raw_name: str) -> str:
        safe_name = raw_name.replace("'", "''")
        name_expr = _name_expr(col_sql)
        query_expr = _name_expr(f"'{safe_name}'")
        novowel_col = f"regexp_replace({name_expr}, '[aeiou]', '', 'g')"
        novowel_query = f"regexp_replace({query_expr}, '[aeiou]', '', 'g')"
        return (
            "("
            f"{col_sql} ILIKE '%{safe_name}%' "
            "OR "
            f"{name_expr} LIKE '%' || {query_expr} || '%' "
            "OR "
            f"{novowel_col} LIKE '%' || {novowel_query} || '%'"
            ")"
        )

    # Expand faculty name matches: f.full_name ILIKE '%...%'
    for alias, table in alias_map.items():
        if table == "faculty":
            sql = re.sub(
                rf"\b{re.escape(alias)}\s*\.\s*full_name\s+ILIKE\s+'%([^']+)%'",
                lambda m, a=alias: _expand_name_clause(f"{a}.full_name", m.group(1)),
                sql,
                flags=re.IGNORECASE,
            )

    # Expand student name matches in both ILIKE and LOWER(... ) LIKE LOWER(... ) forms.
    for alias, table in alias_map.items():
        if table == "students":
            sql = re.sub(
                rf"\b{re.escape(alias)}\s*\.\s*name\s+ILIKE\s+'%([^']+)%'",
                lambda m, a=alias: _expand_name_clause(f"{a}.name", m.group(1)),
                sql,
                flags=re.IGNORECASE,
            )
            sql = re.sub(
                rf"LOWER\(\s*{re.escape(alias)}\s*\.\s*name\s*\)\s+LIKE\s+LOWER\(\s*'%([^']+)%'\s*\)",
                lambda m, a=alias: _expand_name_clause(f"{a}.name", m.group(1)),
                sql,
                flags=re.IGNORECASE,
            )

    # Expand strict equality comparisons as well (common in follow-up generations).
    for alias, table in alias_map.items():
        if table == "faculty":
            sql = re.sub(
                rf"\b{re.escape(alias)}\s*\.\s*full_name\s*=\s*'([^']+)'",
                lambda m, a=alias: _expand_name_clause(f"{a}.full_name", m.group(1)),
                sql,
                flags=re.IGNORECASE,
            )
        if table == "students":
            sql = re.sub(
                rf"\b{re.escape(alias)}\s*\.\s*name\s*=\s*'([^']+)'",
                lambda m, a=alias: _expand_name_clause(f"{a}.name", m.group(1)),
                sql,
                flags=re.IGNORECASE,
            )

    return sql.strip()


def normalize_subject_list_sql(sql: str, question: str) -> str:
    """Normalize faculty subject-list questions to unique subject-level SQL output."""
    if not sql:
        return sql

    q = (question or "").lower()
    subject_list_markers = [
        "what are all the subjects",
        "which subjects",
        "currently handling",
        "currently handle",
        "subjects does",
    ]
    if not any(m in q for m in subject_list_markers):
        return sql

    lower_sql = sql.lower()
    if "faculty_timetable" not in lower_sql or "subjects" not in lower_sql or "faculty" not in lower_sql:
        return sql

    # Preserve the original WHERE filters (faculty name / department / optional semester filters).
    where_clause = ""
    where_match = re.search(r"\bWHERE\b(.*?)(?:\bORDER\s+BY\b|\bGROUP\s+BY\b|\bLIMIT\b|\bOFFSET\b|$)", sql, re.IGNORECASE | re.DOTALL)
    if where_match:
        where_clause = where_match.group(1).strip()

    normalized = (
        "SELECT DISTINCT sub.subject_code, sub.subject_name, "
        "sub.semester_number, sub.subject_type "
        "FROM faculty_timetable ft "
        "JOIN faculty f ON ft.faculty_id = f.faculty_id "
        "JOIN departments d ON f.department_id = d.department_id "
        "JOIN subjects sub ON ft.subject_id = sub.subject_id "
        + (f"WHERE {where_clause} " if where_clause else "")
        + "ORDER BY sub.semester_number, sub.subject_code"
    )
    return normalized.strip()


def is_safe_select_sql(sql: str) -> bool:
    """Allow only SELECT queries generated by the NL engine."""
    if not sql:
        return False
    return bool(re.match(r"^\s*SELECT\b", sql, flags=re.IGNORECASE))


def smalltalk_reply(question: str, department_code: str | None) -> str | None:
    """Return a direct chatbot reply for greetings/small-talk; otherwise None."""
    q = (question or "").strip().lower()
    if not q:
        return None

    if re.fullmatch(r"(hi|hello|hey|hii+|helo+|good\s*(morning|afternoon|evening))\W*", q):
        dept_txt = f" for {department_code}" if department_code else ""
        return (
            f"Hi! I can help with student, faculty, arrear, and timetable insights{dept_txt}. "
            "You can ask things like: 'show active students', 'free faculty on Monday 2nd hour', or 'arrears by batch'."
        )

    if "who are you" in q or "what can you do" in q or q in {"help", "help me"}:
        return (
            "I am your college data assistant. I can answer questions from your academic database, "
            "show tabular results, and give a short summary of what the data means. "
            "Try: 'Show 8th semester students from 2022 batch' or 'Which faculty are free on Monday 2nd hour?'."
        )

    if q in {"thanks", "thank you", "thx", "ok thanks", "great thanks"}:
        return "You’re welcome. Ask me any academic data question whenever you need."

    return None


def is_repairable_sql_error(error_str: str | None) -> bool:
    """Classify SQL errors that are usually recoverable by regeneration."""
    if not error_str:
        return False
    txt = error_str.lower()
    patterns = [
        "syntaxerror",
        "undefinedcolumn",
        "undefined column",
        "undefinedtable",
        "undefined table",
        "ambiguouscolumn",
        "missing from-clause",
        "operator does not exist",
    ]
    return any(p in txt for p in patterns)


def looks_like_join_duplication(rows: list[dict]) -> bool:
    """Heuristic: detect obvious row multiplication from unnecessary joins."""
    if not rows or len(rows) < 8:
        return False

    key_fields = ["register_number", "student_id", "faculty_id", "subject_id", "name"]
    present = [k for k in key_fields if k in rows[0]]

    if present:
        keys = [tuple(str(r.get(k, "")) for k in present) for r in rows]
    else:
        keys = [tuple(sorted((k, str(v)) for k, v in r.items())) for r in rows]

    freq: dict[tuple, int] = {}
    for k in keys:
        freq[k] = freq.get(k, 0) + 1

    most_common = max(freq.values()) if freq else 0
    duplicate_ratio = 1 - (len(freq) / len(keys))
    return most_common >= 5 or duplicate_ratio >= 0.5


def build_semester_batch_sql(question: str, department_code: str | None, is_central_admin: bool) -> str | None:
    """Deterministic SQL for prompts like: 'Show me 8th semester students from the 2022 batch'."""
    q = (question or "").lower()
    if "student" not in q:
        return None

    m_sem = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*semester\b", q)
    m_batch = re.search(r"\b(20\d{2})\s*batch\b", q)
    if not (m_sem and m_batch):
        return None

    semester = int(m_sem.group(1))
    batch = int(m_batch.group(1))

    semester_expr = (
        "(EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2 "
        "+ CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END"
    )

    where_parts = [
        f"s.admission_year = {batch}",
        f"{semester_expr} = {semester}",
        "s.status = 'Active'",
    ]
    if not is_central_admin and department_code:
        where_parts.append(f"d.department_code = '{department_code}'")

    return (
        "SELECT DISTINCT "
        "s.register_number, s.name, s.admission_year, "
        f"{semester_expr} AS current_semester "
        "FROM students s "
        "JOIN departments d ON s.department_id = d.department_id "
        f"WHERE {' AND '.join(where_parts)} "
        "ORDER BY s.register_number"
    )


def build_active_arrears_sql(question: str, department_code: str | None, is_central_admin: bool) -> str | None:
    """Deterministic SQL for queries asking which students have active arrears."""
    q = (question or "").lower()
    if "arrear" not in q and "backlog" not in q:
        return None

    sem_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:sem|semester)\b", q)
    semester = int(sem_match.group(1)) if sem_match else None

    semester_expr = (
        "(EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2 "
        "+ CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END"
    )

    sem_filter = f"AND {semester_expr} = {semester}" if semester is not None else ""
    dept_filter = "" if is_central_admin or not department_code else f"AND d.department_code = '{sql_quote(department_code)}'"

    return (
        "WITH latest_attempts AS ("
        "    SELECT student_id, subject_id, exam_year, exam_month, grade,"
        "           ROW_NUMBER() OVER("
        "               PARTITION BY student_id, subject_id "
        "               ORDER BY exam_year DESC, "
        "                        CASE WHEN exam_month = 'NOV' THEN 11 WHEN exam_month = 'MAY' THEN 5 ELSE 1 END DESC,"
        "                        attempt_id DESC"
        "           ) AS rn"
        "    FROM student_subject_attempts"
        "), active_arrears AS ("
        "    SELECT student_id, subject_id, exam_year, exam_month, grade"
        "    FROM latest_attempts"
        "    WHERE rn = 1 AND grade IN ('U', 'AB')"
        ") "
        "SELECT s.register_number, s.name, s.admission_year, "
        f"{semester_expr} AS current_semester, "
        "COUNT(DISTINCT aa.subject_id) AS active_arrear_count "
        "FROM students s "
        "JOIN departments d ON s.department_id = d.department_id "
        "JOIN active_arrears aa ON aa.student_id = s.student_id "
        f"WHERE s.status = 'Active' {dept_filter} {sem_filter} "
        "GROUP BY s.register_number, s.name, s.admission_year "
        "ORDER BY active_arrear_count DESC, s.register_number"
    )


def build_parent_contact_sql(
    question: str,
    department_code: str | None,
    is_central_admin: bool,
) -> str | None:
    """Deterministic SQL for parent/guardian phone queries tied to a student."""
    q = (question or "").strip()
    ql = q.lower()

    parent_kw = ("parent", "father", "mother", "guardian", "phone", "contact")
    student_kw = ("student", "register", "reg no", "roll")
    if not any(k in ql for k in parent_kw):
        return None

    # Extract semester if user included it (e.g. 8th sem / 8th semester)
    sem_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:sem|semester)\b", ql)
    semester = int(sem_match.group(1)) if sem_match else None

    # Prefer explicit register number when present; else use a likely student name span.
    reg_match = re.search(r"\b\d{10,14}\b", q)
    register_number = reg_match.group(0) if reg_match else None

    name_candidates: list[str] = []
    if not register_number:
        patterns = [
            r"(?:of|for)\s+([A-Za-z\.,\s]{2,120})\s+(?:student|stud)",
            r"(?:of|for)\s+([A-Za-z\.,\s]{2,120})",
        ]
        strip_tail = re.compile(
            r"\s+(?:\d+(?:st|nd|rd|th)?\s*(?:sem|semester)|dcs|cse|ece|it|ai&ds|student).*",
            re.IGNORECASE,
        )
        for pat in patterns:
            matches = list(re.finditer(pat, q, flags=re.IGNORECASE))
            if matches:
                # Follow-up expansion can contain previous and current prompts.
                # Use the latest "for/of ..." phrase so newest names win.
                m = matches[-1]
                blob = m.group(1).strip(" .,:;-?")
                blob = strip_tail.sub("", blob).strip(" .,:;-?")
                parts = [p.strip(" .,:;-?") for p in re.split(r",|\band\b", blob, flags=re.IGNORECASE)]
                parts = [re.sub(r"\s+", " ", p) for p in parts if len(p.strip()) >= 2]

                # Drop common non-name words while preserving initials like "S" only
                cleaned_parts: list[str] = []
                for p in parts:
                    p = re.sub(r"\b(?:dr|mr|mrs|ms|professor|prof)\.?\b", "", p, flags=re.IGNORECASE).strip()
                    if p:
                        cleaned_parts.append(p)

                if cleaned_parts:
                    name_candidates = cleaned_parts
                    break

    if not register_number and not name_candidates and not any(k in ql for k in student_kw):
        return None

    semester_expr = (
        "(EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2 "
        "+ CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END"
    )

    where_parts = []
    if not is_central_admin and department_code:
        where_parts.append(f"d.department_code = '{sql_quote(department_code)}'")
    if register_number:
        where_parts.append(f"s.register_number = '{sql_quote(register_number)}'")
    elif name_candidates:
        name_clauses = [f"LOWER(s.name) LIKE LOWER('%{sql_quote(c)}%')" for c in name_candidates]
        where_parts.append("(" + " OR ".join(name_clauses) + ")")
    if semester is not None:
        where_parts.append(f"{semester_expr} = {semester}")

    if not where_parts:
        return None

    return (
        "SELECT "
        "s.register_number, s.name, "
        "p.father_name, p.father_contact_number, "
        "p.mother_name, p.mother_contact_number "
        "FROM students s "
        "JOIN parents p ON p.student_id = s.student_id "
        "JOIN departments d ON s.department_id = d.department_id "
        f"WHERE {' AND '.join(where_parts)} "
        "ORDER BY s.register_number "
        "LIMIT 20"
    )


def normalize_day_token(question: str) -> str | None:
    """Extract and normalize weekday token to DB format (Mon/Tue/...)."""
    q = (question or "").lower()
    day_map = {
        "monday": "Mon", "mon": "Mon",
        "tuesday": "Tue", "tue": "Tue", "tues": "Tue", "tuesady": "Tue", "teusday": "Tue",
        "wednesday": "Wed", "wed": "Wed", "wednesady": "Wed", "wednsday": "Wed", "wensday": "Wed",
        "thursday": "Thu", "thu": "Thu", "thur": "Thu", "thurs": "Thu", "thrusday": "Thu", "thurday": "Thu",
        "friday": "Fri", "fri": "Fri",
        "saturday": "Sat", "sat": "Sat", "satuday": "Sat",
        "sunday": "Sun", "sun": "Sun",
    }
    for k, v in day_map.items():
        if re.search(rf"\b{k}\b", q):
            return v

    # Relative day helpers for follow-up prompts like "tomorrow?"
    if re.search(r"\btoday(?:'s|s)?\b", q, flags=re.IGNORECASE):
        return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][date.today().weekday()]
    if re.search(r"\b(?:tomorrow|tommorow|tomoorow|tommorrow|tommmoorw|tmr|tmrw)(?:'s|s)?\b", q, flags=re.IGNORECASE):
        idx = (date.today().weekday() + 1) % 7
        return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][idx]

    return None


def extract_hour_token(question: str) -> int | None:
    """Extract hour/period number from natural language (e.g., 2nd hour)."""
    q = (question or "").lower()
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:hour|hr|period|slot)\b", q)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def sql_quote(value: str) -> str:
    """Simple SQL string quoting for deterministic SQL construction."""
    return (value or "").replace("'", "''")


def build_faculty_timetable_sql(
    question: str,
    faculty_name: str,
    department_code: str | None,
    is_central_admin: bool,
) -> str:
    """Deterministic SQL for faculty timetable queries after name resolution."""
    day = normalize_day_token(question)
    hour = extract_hour_token(question)
    q = (question or "").lower()
    is_free_query = any(k in q for k in ["free", "free period", "free slot", "available", "not occupied"])

    # Institution policy: no regular timetable/free-slot results on Sundays.
    if day == "Sun":
        if is_free_query:
            return (
                "SELECT "
                "NULL::text AS day_of_week, NULL::int AS hour_number, "
                "NULL::time AS start_time, NULL::time AS end_time, "
                "NULL::text AS subject_code, NULL::text AS subject_name, "
                "NULL::smallint AS sem_batch, NULL::text AS activity "
                "WHERE FALSE"
            )
        return (
            "SELECT "
            "NULL::text AS day_of_week, NULL::int AS hour_number, "
            "NULL::time AS start_time, NULL::time AS end_time, "
            "NULL::text AS subject_code, NULL::text AS subject_name, "
            "NULL::smallint AS sem_batch, NULL::text AS activity "
            "WHERE FALSE"
        )

    if is_free_query:
        where_parts = [
            f"LOWER(f.full_name) = LOWER('{sql_quote(faculty_name)}')",
        ]
        if not is_central_admin and department_code:
            where_parts.append(f"d.department_code = '{sql_quote(department_code)}'")
        if day:
            where_parts.append(f"ft.day_of_week = '{day}'")
        if hour is not None:
            where_parts.append(f"ts.hour_number = {hour}")

        # Return slots that are NOT assigned to the faculty on the requested day/hour.
        # If no day is provided, show free slots across the standard teaching days.
        day_expr = f"'{day}'" if day else "days.day_of_week"
        day_source = (
            "(VALUES ('Mon'),('Tue'),('Wed'),('Thu'),('Fri'),('Sat')) AS days(day_of_week)"
            if not day else "(SELECT 1) AS days(dummy)"
        )
        day_predicate = "ft.day_of_week = days.day_of_week" if not day else "1=1"

        return (
            "SELECT "
            f"{day_expr} AS day_of_week, ts.hour_number, ts.start_time, ts.end_time, "
            "NULL::text AS subject_code, NULL::text AS subject_name, NULL::smallint AS sem_batch, "
            "'FREE'::text AS activity "
            "FROM time_slots ts "
            f"CROSS JOIN {day_source} "
            "WHERE NOT EXISTS ("
            "SELECT 1 "
            "FROM faculty_timetable ft "
            "JOIN faculty f ON ft.faculty_id = f.faculty_id "
            "JOIN departments d ON f.department_id = d.department_id "
            f"WHERE {' AND '.join(where_parts)} "
            f"AND {day_predicate} "
            "AND ft.slot_id = ts.slot_id"
            ") "
            "ORDER BY "
            "CASE "
            f"WHEN {day_expr} = 'Mon' THEN 1 WHEN {day_expr} = 'Tue' THEN 2 WHEN {day_expr} = 'Wed' THEN 3 "
            f"WHEN {day_expr} = 'Thu' THEN 4 WHEN {day_expr} = 'Fri' THEN 5 WHEN {day_expr} = 'Sat' THEN 6 ELSE 7 END, "
            "ts.hour_number"
        )

    where_parts = [f"LOWER(f.full_name) = LOWER('{sql_quote(faculty_name)}')"]
    if not is_central_admin and department_code:
        where_parts.append(f"d.department_code = '{sql_quote(department_code)}'")
    if day:
        where_parts.append(f"ft.day_of_week = '{day}'")
    if hour is not None:
        where_parts.append(f"ts.hour_number = {hour}")

    return (
        "SELECT "
        "ft.day_of_week, ts.hour_number, ts.start_time, ts.end_time, "
        "s.subject_code, s.subject_name, ft.sem_batch, COALESCE(ft.activity, '-') AS activity "
        "FROM faculty_timetable ft "
        "JOIN faculty f ON ft.faculty_id = f.faculty_id "
        "JOIN departments d ON f.department_id = d.department_id "
        "LEFT JOIN subjects s ON ft.subject_id = s.subject_id "
        "LEFT JOIN time_slots ts ON ft.slot_id = ts.slot_id "
        f"WHERE {' AND '.join(where_parts)} "
        "ORDER BY "
        "CASE ft.day_of_week "
        "WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3 "
        "WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 WHEN 'Sat' THEN 6 ELSE 7 END, "
        "ts.hour_number"
    )


def build_free_staff_sql(
    question: str,
    department_code: str | None,
    is_central_admin: bool,
) -> str | None:
    """
    Deterministic SQL for queries like:
      - "Which staff are free on Monday 2nd hour?"
      - "Who is available on Tue 4th period?"

    To avoid false positives, this shortcut only triggers when BOTH day and hour
    are present in the question.
    """
    q = (question or "").lower()
    is_free_query = any(k in q for k in ["free", "available", "not occupied"])
    targets_staff = any(k in q for k in ["staff", "faculty", "teacher", "who"])
    if not (is_free_query and targets_staff):
        return None

    day = normalize_day_token(question)
    hour = extract_hour_token(question)
    if not day or hour is None:
        return None

    # Institution policy: Sunday is a non-working day for timetable/free-staff lookups.
    if day == "Sun":
        return (
            "SELECT "
            "NULL::text AS full_name, NULL::text AS designation, "
            "NULL::text AS day_of_week, NULL::int AS hour_number "
            "WHERE FALSE"
        )

    where_parts = ["f.is_active = TRUE"]
    if not is_central_admin and department_code:
        where_parts.append(f"d.department_code = '{sql_quote(department_code)}'")

    return (
        "SELECT "
        "f.full_name, f.designation, "
        f"'{day}'::text AS day_of_week, "
        f"{hour}::int AS hour_number "
        "FROM faculty f "
        "JOIN departments d ON f.department_id = d.department_id "
        f"WHERE {' AND '.join(where_parts)} "
        "AND NOT EXISTS ("
        "SELECT 1 "
        "FROM faculty_timetable ft "
        "JOIN time_slots ts ON ft.slot_id = ts.slot_id "
        "WHERE ft.faculty_id = f.faculty_id "
        f"AND ft.day_of_week = '{day}' "
        f"AND ts.hour_number = {hour}"
        ") "
        "ORDER BY f.full_name"
    )


def extract_faculty_name_candidate(question: str) -> str | None:
    """Extract likely faculty name mention from timetable-related questions."""
    q = (question or "").strip()
    if not q:
        return None

    # Support either "quoted" or 'quoted' names.
    quoted = re.search(r'"([^"]{2,80})"|\'([^\']{2,80})\'', q)
    if quoted:
        return (quoted.group(1) or quoted.group(2) or "").strip()

    patterns = [
        r"(?:free\s*(?:period|slot)?|available)\s+(?:for\s+)?([A-Za-z\.\s]{2,80})",
        r"when\s+is\s+([A-Za-z\.\s]{2,80})\s+free",
        r"for\s+([A-Za-z\.\s]{2,80})\s+on\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"timetable\s+(?:of|for|about)\s+([A-Za-z\.\s]{2,80})",
        r"about\s+([A-Za-z\.\s]{2,80})\s+timetable",
        r"for\s+([A-Za-z\.\s]{2,80})\s+timetable",
        r"same\s+for\s+([A-Za-z\.\s]{2,80})",
        r"show\s+timetable\s+for\s+([A-Za-z\.\s]{2,80})",
        r"([A-Za-z\.\s]{2,80})\s+timetable",
    ]
    _DAY_STRIP = re.compile(
        r"\s+(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
        r"(?:\s+\d+(?:st|nd|rd|th)?\s*(?:hour|hr|period|slot))?.*",
        re.IGNORECASE,
    )
    for pat in patterns:
        m = re.search(pat, q, flags=re.IGNORECASE)
        if m:
            cand = m.group(1).strip(" .,:;-?")
            # Strip trailing day/hour qualifiers so "manju on tuesday" → "manju"
            cand = _DAY_STRIP.sub("", cand).strip(" .,:;-?")
            if len(cand) >= 2:
                return cand
    return None


def expand_followup_question(question: str, history_msgs: list[dict]) -> str:
    """
    Expand short follow-up messages using previous question context.

    Handles:
      - Name swap: "for kannamal?" → "Show timetable for kannamal on Tuesday"
                   (preserves day/hour from previous question)
      - Day/hour injection: "friday" → "<prev question> on friday"
      - "same for X" shorthand
    """
    q = (question or "").strip()
    if not q or not history_msgs:
        return q

    ql = q.lower()
    full_intent_keywords = [
        "student", "faculty", "timetable", "schedule", "arrear", "subject",
        "semester", "batch", "free", "hour", "slot", "department",
    ]
    if any(k in ql for k in full_intent_keywords) and len(ql.split()) > 4:
        if not re.search(r"\b(?:same|also)\b", ql):
            return q

    previous_q = ""
    for m in reversed(history_msgs):
        pq = (m.get("question") or "").strip()
        if pq and pq.lower() != ql:
            if any(k in pq.lower() for k in full_intent_keywords):
                previous_q = pq
                break
            if not previous_q:
                previous_q = pq

    if not previous_q:
        return q

    # ── Day/hour follow-up for free-staff style questions ───────────────────
    prev_is_free_staff = bool(re.search(
        r"\b(?:free|available|not\s+occupied)\b", previous_q, flags=re.IGNORECASE
    )) and bool(re.search(
        r"\b(?:staff|faculty|teacher|who)\b", previous_q, flags=re.IGNORECASE
    ))

    cur_day = normalize_day_token(q)
    cur_hour = extract_hour_token(q)
    if "same" in ql and prev_is_free_staff and (cur_day or cur_hour):
        prev_day = normalize_day_token(previous_q)
        prev_hour = extract_hour_token(previous_q)
        day = cur_day or prev_day
        hour = cur_hour or prev_hour

        day_full = {
            "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
            "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday"
        }.get(day, day) if day else None

        if day_full and hour:
            return f"Which staff will be free on {day_full} {hour}th hour?"
        if day_full:
            return f"Which staff will be free on {day_full}?"
        if hour:
            return f"Which staff will be free on {hour}th hour?"

    # ── Date-only follow-up: "on 22nd?" (inherit month/hour from previous) ──
    dom_match = re.search(r"\b(?:on\s+)?([0-3]?\d)(?:st|nd|rd|th)\b", q, flags=re.IGNORECASE)
    if dom_match:
        # Capture month token from previous explicit-date question (e.g., "21st arpil").
        month_match = re.search(
            r"\b(?:[0-3]?\d(?:st|nd|rd|th)?\s*(?:of\s+)?([A-Za-z]{3,10})|([A-Za-z]{3,10})\s*[0-3]?\d(?:st|nd|rd|th)?)\b",
            previous_q,
            flags=re.IGNORECASE,
        )
        month_token = (month_match.group(1) or month_match.group(2)).strip() if month_match else None
        prev_hour = extract_hour_token(previous_q)
        day_num = int(dom_match.group(1))

        if month_token and prev_is_free_staff:
            if prev_hour is not None:
                return f"Which staff will be free on {day_num} {month_token} {prev_hour}th hour?"
            return f"Which staff will be free on {day_num} {month_token}?"

        if month_token and re.search(r"\b(?:timetable|schedule)\b", previous_q, flags=re.IGNORECASE):
            if prev_hour is not None:
                return f"Show timetable on {day_num} {month_token} {prev_hour}th hour"
            return f"Show timetable on {day_num} {month_token}"

    # ── Name-swap: "for kannamal?" / "same for manju" ────────────────────────
    target_match = re.search(
        r"(?:same\s+for|also\s+for|for|same\b)\s*([A-Za-z\.\s]{2,80})",
        q, flags=re.IGNORECASE
    )
    if target_match:
        target = target_match.group(1).strip(" .,:;-?")
        target = re.sub(r"^(?:the\s+faculty\s+|dr\.?\s*)", "", target, flags=re.IGNORECASE).strip()

        # Guardrail: if the captured token is day/hour-like text, this is
        # parameter update follow-up, not a person-name swap.
        if normalize_day_token(target) or re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s*(?:hour|hr|period|slot)\b", target, re.IGNORECASE):
            target = ""

        if target:
            is_timetable_ctx = re.search(
                r"\b(?:timetable|schedule)\b", previous_q, flags=re.IGNORECASE
            )
            if is_timetable_ctx:
                # Preserve day/hour from previous question so the filter isn't lost
                prev_day  = normalize_day_token(previous_q)
                prev_hour = extract_hour_token(previous_q)
                # Also check if current follow-up itself specifies a day/hour
                cur_day  = normalize_day_token(q)
                cur_hour = extract_hour_token(q)
                day  = cur_day  or prev_day
                hour = cur_hour or prev_hour

                expanded = f"Show timetable for {target}"
                if day:
                    day_full = {
                        "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
                        "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday"
                    }.get(day, day)
                    expanded += f" on {day_full}"
                if hour:
                    expanded += f" {hour}th hour"
                return expanded

            # Prefer replacing prior entity target over appending, so follow-up
            # keeps the same intent/template (e.g., "relevant information regarding X").
            replaced = previous_q
            replacement_patterns = [
                (r"(regarding\s+)([A-Za-z\.'\s]{2,120})", r"\1" + target),
                (r"(about\s+)([A-Za-z\.'\s]{2,120})", r"\1" + target),
                (r"(for\s+)([A-Za-z\.'\s]{2,120})", r"\1" + target),
                (r"(of\s+)([A-Za-z\.'\s]{2,120})", r"\1" + target),
            ]
            for pat, repl in replacement_patterns:
                if re.search(pat, replaced, flags=re.IGNORECASE):
                    replaced = re.sub(pat, repl, replaced, flags=re.IGNORECASE)
                    return replaced.strip()

            # If no clear replacement slot exists, keep intent explicit for names.
            return f"Can you retrieve all the relevant information regarding {target}?"

            # Non-timetable: just append the target to previous question
            return f"{previous_q} For {target}."

    # ── Isolated day/hour parameter ──────────────────────────────────────────
    if len(q.split()) <= 4 and (normalize_day_token(q) or extract_hour_token(q)):
        return f"{previous_q} {q}"

    # ── Bare "same" with no target ────────────────────────────────────────────
    if "same" in ql:
        return f"{previous_q} {q}"

    return q


async def resolve_faculty_name(
    executor,
    candidate: str | None,
    department_code: str | None,
    is_central_admin: bool,
    role: str,
) -> str | None:
    """
    Resolve a partial/misspelled faculty name to the best DB full_name.

    Strategy (two-pass):
      Pass 1 — DB-side ILIKE token match (fast, exact enough for clear names).
      Pass 2 — If pass 1 returns nothing, fetch ALL faculty in the dept and
               score by token-overlap in Python (handles initials like DR.A.Kannammal
               matched by just "kannamal").
    """
    if not candidate:
        return None

    STOP = {"dr", "mr", "mrs", "ms", "prof", "professor", "the", "faculty",
            "staff", "teacher", "sir", "madam", "mam", "a", "b", "c", "d"}

    tokens = [
        t for t in re.findall(r"[A-Za-z]+", candidate.lower())
        if len(t) >= 2 and t not in STOP
    ]
    if not tokens:
        return None

    dept_clause = ""
    params: dict = {"exact": candidate.lower(), "prefix": f"%{candidate.lower()}%"}
    if not is_central_admin and department_code:
        dept_clause = "AND d.department_code = :dept"
        params["dept"] = department_code

    # ── Pass 1: token AND match (all tokens must appear in name) ─────────────
    where_parts = []
    for i, tok in enumerate(tokens):
        key = f"t{i}"
        where_parts.append(f"LOWER(f.full_name) LIKE :{key}")
        params[key] = f"%{tok}%"

    sql_p1 = f"""
        SELECT f.full_name
        FROM faculty f
        JOIN departments d ON f.department_id = d.department_id
        WHERE {' AND '.join(where_parts)}
        {dept_clause}
        ORDER BY
            CASE
                WHEN LOWER(f.full_name) = :exact THEN 0
                WHEN LOWER(f.full_name) LIKE :prefix THEN 1
                ELSE 2
            END,
            LENGTH(f.full_name)
        LIMIT 1
    """
    res1 = await executor.run(sql_p1, params=params, role=role)
    if not res1.error and res1.rows:
        return res1.rows[0].get("full_name")

    # ── Pass 2: fetch all faculty in dept, score by token overlap ────────────
    # This handles "kannamal" matching "DR.A.Kannammal" even though the
    # initial "A" causes the AND match to fail.
    sql_p2 = f"""
        SELECT f.full_name
        FROM faculty f
        JOIN departments d ON f.department_id = d.department_id
        WHERE f.is_active = TRUE
        {dept_clause.replace('AND', 'AND', 1) if dept_clause else ''}
        ORDER BY f.full_name
        LIMIT 200
    """
    params2 = {}
    if not is_central_admin and department_code:
        params2["dept"] = department_code
        sql_p2 = f"""
            SELECT f.full_name
            FROM faculty f
            JOIN departments d ON f.department_id = d.department_id
            WHERE f.is_active = TRUE AND d.department_code = :dept
            ORDER BY f.full_name
            LIMIT 200
        """
    res2 = await executor.run(sql_p2, params=params2 if params2 else None, role=role)
    if res2.error or not res2.rows:
        return None

    # Score each name by how many query tokens appear in it
    def score(full_name: str) -> int:
        fn_lower = full_name.lower()
        # Replace dots/initials so "DR.A.Kannammal" becomes "dr a kannammal"
        fn_norm = re.sub(r"[.\-_]", " ", fn_lower)
        fn_tokens = set(re.findall(r"[a-z]+", fn_norm))
        return sum(1 for t in tokens if t in fn_norm or any(
            ft.startswith(t) or t.startswith(ft)
            for ft in fn_tokens if len(ft) >= 3 and len(t) >= 3
        ))

    scored = [(score(r["full_name"]), r["full_name"]) for r in res2.rows]
    scored = [(s, n) for s, n in scored if s > 0]
    if not scored:
        return None

    # Return the highest-scored name; tie-break by shortest name (most specific)
    best = max(scored, key=lambda x: (x[0], -len(x[1])))
    logger.info("[resolve_faculty_name] Fuzzy match: %r → %r (score=%d)", candidate, best[1], best[0])
    return best[1]