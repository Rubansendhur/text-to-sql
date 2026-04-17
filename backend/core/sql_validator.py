"""
core/sql_validator.py
─────────────────────
SQL Validator Agent — validates generated SQL against the known schema BEFORE
running it against the database.

Why this exists
───────────────
The LLM sometimes generates SQL that references:
  • Columns that don't exist on a table (e.g. f.day_of_week)
  • Wrong table aliases
  • Missing JOINs for required columns
  • Columns from one table placed on another table alias

This agent catches those errors cheaply (no DB round-trip) and either
auto-fixes them or returns a structured error so the pipeline can retry
with a targeted hint.

Usage
─────
    from core.sql_validator import validate_sql, ValidationResult

    result = validate_sql(sql, department_code="DCS", is_central_admin=False)
    if not result.is_valid:
        # result.errors  → list of human-readable issues
        # result.fixed_sql → auto-fixed SQL if fixable, else None
        # result.hint    → targeted hint string for LLM retry
"""

import re
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# ── Schema: table → set of valid column names ─────────────────────────────────
SCHEMA: dict[str, set[str]] = {
    "departments": {
        "department_id", "department_code", "department_name", "created_at",
    },
    "students": {
        "student_id", "register_number", "name", "gender", "date_of_birth",
        "contact_number", "email", "department_id", "admission_year", "section",
        "hostel_status", "status", "cgpa", "created_at",
    },
    "faculty": {
        "faculty_id", "title", "full_name", "designation", "email", "phone",
        "department_id", "is_hod", "is_active", "created_at",
        # Common mistake: these do NOT exist on faculty
        # day_of_week, slot_id, hour_number, activity, sem_batch → faculty_timetable
    },
    "subjects": {
        "subject_id", "subject_code", "subject_name", "department_id",
        "semester_number", "subject_type", "lecture_hrs", "tutorial_hrs",
        "practical_hrs", "credits", "created_at",
    },
    "parents": {
        "parent_id", "student_id", "father_name", "mother_name",
        "father_contact_number", "mother_contact_number", "address",
    },
    "student_subject_attempts": {
        "attempt_id", "student_id", "subject_id", "exam_year", "exam_month", "grade", "created_at",
    },
    "student_subject_results": {
        "id", "student_id", "subject_id", "semester_number", "grade", "exam_year", "exam_month", "created_at",
    },
    "student_semester_gpa": {
        "student_id", "semester_number", "gpa", "total_credits",
    },
    "faculty_timetable": {
        "tt_id", "faculty_id", "day_of_week", "slot_id", "subject_id",
        "activity", "sem_batch", "department_id", "updated_at",
    },
    "class_timetable": {
        "id", "sem_batch", "department_id", "section", "day_of_week",
        "hour_number", "subject_id", "faculty_id", "activity",
    },
    "time_slots": {
        "slot_id", "hour_number", "start_time", "end_time", "label",
    },
    "users": {
        "user_id", "username", "password", "role", "department_code",
    },
    # Views
    "vw_arrear_count": {
        "register_number", "name", "status", "active_arrear_count",
    },
    "vw_timetable": {
        "day_of_week", "hour_number", "time_range", "code", "subject",
        "subject_type", "faculty_name", "lecture_hall", "notes", "semester_number",
    },
}

# Columns that ONLY belong to faculty_timetable, never on faculty/departments
_TIMETABLE_ONLY_COLS = {"day_of_week", "slot_id", "hour_number", "activity", "sem_batch"}

# Pattern: alias.column  (e.g.  f.day_of_week  or  faculty.slot_id)
_ALIAS_COL_PAT = re.compile(
    r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\b'
)

# Detect which real table an alias refers to inside FROM/JOIN clauses
_FROM_ALIAS_PAT = re.compile(
    r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)',
    re.IGNORECASE,
)

COMMON_PROBLEMS = [
    "sem_batch is INTEGER — never use ILIKE or string comparisons",
    "day_of_week uses 3-letter codes: 'Mon','Tue','Wed','Thu','Fri','Sat'",
    "faculty table has NO day_of_week/slot_id/hour_number — use faculty_timetable",
    "faculty_timetable uses slot_id, not hour_number",
    "class_timetable uses id and hour_number — never use tt_id or slot_id there",
    "current_semester is derived from admission_year — do not query it as a stored column",
    "Use time_slots.hour_number when user says 'Nth hour', not slot_id directly",
    "student_subject_attempts PK is attempt_id, not id",
    "faculty_timetable PK is tt_id, not id",
    "student_semester_gpa has no cgpa_upto column. Use gpa or total_credits.",
]

# Detect timetable column on faculty alias specifically
_FACULTY_TT_COL_PAT = re.compile(
    r'\b(?:f|faculty)\s*\.\s*(day_of_week|slot_id|hour_number|activity|sem_batch)\b',
    re.IGNORECASE,
)

# Detect sem mention ("8th sem", "8 sem", "8th semester")
_SEM_MENTION_PAT = re.compile(
    r'\b(\d+)(?:st|nd|rd|th)?\s*(?:sem(?:ester)?)\b', re.IGNORECASE
)

# Detect "8th SEM" used as a WHERE clause against faculty timetable sem_batch
_SEM_BATCH_IN_FACULTY_WHERE = re.compile(
    r'\b(?:ft|faculty_timetable)\s*\.\s*sem_batch\s*=\s*(\d+)', re.IGNORECASE
)


def _split_top_level_csv(expr: str) -> list[str]:
    """Split a comma-separated SQL expression list at top-level only."""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    string_char = None

    i = 0
    while i < len(expr):
        ch = expr[i]

        if ch in ("'", '"') and (i == 0 or expr[i - 1] != "\\"):
            if not in_string:
                in_string = True
                string_char = ch
            elif ch == string_char:
                in_string = False
                string_char = None

        if not in_string:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)

            if ch == "," and depth == 0:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                i += 1
                continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _select_expressions(sql: str) -> list[str]:
    """Extract top-level expressions from the SELECT list."""
    m = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    return _split_top_level_csv(m.group(1))


def _is_non_aggregated_expression(expr: str) -> bool:
    """
    Return True when expression contributes a non-aggregated selected value.
    Examples treated as non-aggregated: plain columns, CASE expressions, arithmetic.
    Constants/literals are treated as aggregated-safe.
    """
    e = re.sub(r"\s+AS\s+[a-zA-Z_][a-zA-Z0-9_]*\s*$", "", expr, flags=re.IGNORECASE).strip()

    # Pure constants are safe without GROUP BY
    if re.fullmatch(r"\d+(?:\.\d+)?", e):
        return False
    if re.fullmatch(r"'(?:''|[^'])*'", e):
        return False
    if re.fullmatch(r"NULL", e, flags=re.IGNORECASE):
        return False

    # Any aggregate/window expression is not counted as non-aggregated.
    if re.search(r"\b(COUNT|SUM|AVG|MIN|MAX|STRING_AGG|ARRAY_AGG)\s*\(", e, re.IGNORECASE):
        return False

    return True


def _has_required_department_scope(sql: str, department_code: str) -> bool:
    """Return True when SQL clearly scopes rows to the given department code."""
    if not sql or not department_code:
        return False

    dept = department_code.strip().lower()
    if not dept:
        return False

    # Match direct predicates like:
    #   d.department_code = 'DCS'
    #   LOWER(d.department_code) = 'dcs'
    #   department_code ILIKE 'dcs'
    eq_or_like = re.compile(
        r"(?:LOWER\s*\(\s*)?\b[a-zA-Z_][a-zA-Z0-9_]*\.?department_code\b\s*\)?\s*"
        r"(?:=|LIKE|ILIKE)\s*'([^']+)'",
        re.IGNORECASE,
    )
    for m in eq_or_like.finditer(sql):
        if m.group(1).strip().lower() == dept:
            return True

    # Match IN lists like: department_code IN ('DCS', 'ECE')
    in_pat = re.compile(
        r"\b[a-zA-Z_][a-zA-Z0-9_]*\.?department_code\b\s+IN\s*\(([^)]*)\)",
        re.IGNORECASE,
    )
    for m in in_pat.finditer(sql):
        values = [v.strip().strip("'\"").lower() for v in m.group(1).split(",")]
        if dept in values:
            return True

    return False


# ── Result ────────────────────────────────────────────────────────────────────
@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixed_sql: str | None = None   # auto-repaired SQL when fixable
    hint: str = ""                  # targeted LLM retry hint


# ── Public API ────────────────────────────────────────────────────────────────
def validate_sql(
    sql: str,
    department_code: str | None = None,
    is_central_admin: bool = False,
    original_question: str = "",
) -> ValidationResult:
    """
    Validate SQL against the known schema.

    Checks performed (in order):
      1. Must be a SELECT statement
      2. Faculty timetable columns must not appear on the faculty alias
      3. Department scope for non-admin users
      4. sem_batch values make sense (1-8 for standard programs)
      5. Alias resolution: detect columns on wrong table aliases

    Returns a ValidationResult with is_valid, errors, fixed_sql, and hint.
    """
    result = ValidationResult()

    if not sql or not sql.strip():
        result.is_valid = False
        result.errors.append("Empty SQL")
        result.hint = "Generate a valid SELECT SQL query."
        return result

    sql = sql.strip()

    # ── Check 1: Must be SELECT ───────────────────────────────────────────────
    if not re.match(r'^\s*SELECT\b', sql, re.IGNORECASE):
        result.is_valid = False
        result.errors.append("SQL does not start with SELECT")
        result.hint = "Return only a SELECT statement. No DML (INSERT/UPDATE/DELETE/DROP)."
        return result

    # ── Check 2: Timetable cols on faculty alias ──────────────────────────────
    tt_on_faculty = _FACULTY_TT_COL_PAT.findall(sql)
    if tt_on_faculty:
        bad_cols = ", ".join(set(tt_on_faculty))
        result.errors.append(
            f"Columns [{bad_cols}] are on faculty_timetable, NOT on faculty. "
            "Use ft.{col} with FROM faculty_timetable ft JOIN faculty f ..."
        )
        # Attempt auto-fix
        fixed = _fix_timetable_on_faculty(sql)
        if fixed and fixed != sql:
            result.fixed_sql = fixed
            result.warnings.append("Auto-fixed: moved timetable columns to faculty_timetable alias.")
            log.info("Auto-fixed timetable column misplacement. Fixed SQL: %s", fixed[:200])
        else:
            result.is_valid = False
            result.hint = (
                "CRITICAL FIX NEEDED: columns day_of_week/slot_id/hour_number/activity/sem_batch "
                "belong to faculty_timetable (alias ft), NOT to faculty (alias f).\n"
                "CORRECT pattern:\n"
                "  FROM faculty_timetable ft\n"
                "  JOIN faculty f ON ft.faculty_id = f.faculty_id\n"
                "  JOIN time_slots ts ON ft.slot_id = ts.slot_id\n"
                "  WHERE ft.day_of_week = '...' AND ts.hour_number = ...\n"
                "NEVER use f.day_of_week or f.slot_id."
            )

    # ── Check 3a: Strip/fix leftover {DEPT} placeholder for central admins ────
    if is_central_admin and "{DEPT}" in sql:
        # Auto-fix: remove the literal placeholder clauses
        import re as _re
        fixed_admin = sql
        for pat in [
            r"\s*AND\s+d\.department_code\s*=\s*'?\{DEPT\}'?",
            r"\s*WHERE\s+d\.department_code\s*=\s*'?\{DEPT\}'?",
            r"\s*AND\s+department_code\s*=\s*'?\{DEPT\}'?",
            r"\s*WHERE\s+department_code\s*=\s*'?\{DEPT\}'?",
        ]:
            fixed_admin = _re.sub(pat, "", fixed_admin, flags=_re.IGNORECASE)
        fixed_admin = fixed_admin.strip()
        if "{DEPT}" not in fixed_admin:
            result.fixed_sql = fixed_admin
            result.warnings.append("Auto-fixed: removed literal {DEPT} placeholder for central admin query.")
            log.info("Auto-stripped {DEPT} placeholder from admin query.")
        else:
            result.is_valid = False
            result.errors.append("SQL still contains literal {DEPT} placeholder — cannot execute.")
            result.hint = (
                "You are a central administrator. Do NOT include any department_code filter. "
                "Remove 'WHERE department_code = ...' entirely and query all departments."
            )

    # ── Check 3b: Department scope for non-admins (hard requirement) ─────────
    if not is_central_admin and department_code:
        if not _has_required_department_scope(sql, department_code):
            result.is_valid = False
            result.errors.append(
                f"Missing mandatory department scope '{department_code}'."
            )
            result.hint = (
                f"MANDATORY: Restrict results to department '{department_code}' only. "
                "Always include a department filter in SQL, e.g.\n"
                "JOIN departments d ON <table>.department_id = d.department_id\n"
                f"WHERE d.department_code = '{department_code}'\n"
                "Do not return cross-department data."
            )

    # ── Check 4: Validate sem_batch / semester values ─────────────────────────
    sem_batch_vals = re.findall(r'\bsem_batch\s*=\s*(\d+)', sql, re.IGNORECASE)
    for val in sem_batch_vals:
        if not (1 <= int(val) <= 8):
            result.warnings.append(
                f"sem_batch = {val} looks unusual (expected 1-8 for standard programs)."
            )

    # ── Check 5: Detect ILIKE on sem_batch (string filter on int column) ──────
    if re.search(r'sem_batch\s+ILIKE', sql, re.IGNORECASE):
        result.is_valid = False
        result.errors.append("sem_batch is an INTEGER column — cannot use ILIKE. Use = integer.")
        result.hint = (
            "sem_batch is an integer column. "
            "Use: WHERE ft.sem_batch = 8  (not ILIKE '%8%')"
        )

    # ── Check 5.1: Detect missing GROUP BY with aggregate functions ──────────
    has_agg = bool(re.search(r'\b(COUNT|SUM|AVG|MIN|MAX|STRING_AGG|ARRAY_AGG)\s*\(', sql, re.IGNORECASE))
    has_group_by = bool(re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE))

    # Only require GROUP BY when non-window aggregates are mixed with non-aggregated
    # selected expressions. COUNT(*) alone is valid without GROUP BY.
    has_windowed_agg = bool(re.search(
        r'\b(COUNT|SUM|AVG|MIN|MAX|STRING_AGG|ARRAY_AGG)\s*\([^)]*\)\s*OVER\s*\(',
        sql,
        re.IGNORECASE
    ))
    select_exprs = _select_expressions(sql)
    has_non_agg_selected_expr = any(_is_non_aggregated_expression(e) for e in select_exprs)

    if has_agg and has_non_agg_selected_expr and not has_group_by and not has_windowed_agg:
        result.errors.append("Query uses aggregate function (COUNT/SUM/AVG) but missing GROUP BY clause.")
        result.hint = (
            "When using aggregate functions like COUNT(*), SUM(), AVG(), etc., "
            "you must include a GROUP BY clause listing all non-aggregated columns in SELECT.\n"
            "Example: SELECT column1, column2, COUNT(*) FROM table "
            "GROUP BY column1, column2"
        )
        if result.is_valid:
            result.is_valid = False

    # ── Check 5.5: Explicitly validate table names ────────────────────────────
    invalid_tables = []
    # Collect CTE names to allow them as valid tables
    cte_names = [cte.lower() for cte in re.findall(r'\bWITH\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(', sql, re.IGNORECASE)]
    valid_tables = set(SCHEMA.keys()).union(set(cte_names))

    for match in _FROM_ALIAS_PAT.finditer(sql):
        table = match.group(1).lower()
        if table not in valid_tables:
            invalid_tables.append(table)
            
    if invalid_tables:
        result.is_valid = False
        result.errors.append(f"Unknown table(s): {', '.join(invalid_tables)}")
        result.hint = (
            f"The following tables DO NOT EXIST: {', '.join(invalid_tables)}. "
            "Check for typos or missing spaces (e.g. 'table_namealias'). "
            "Only use tables from the provided schema."
        )

    # ── Check 5.6: Hallucinated 'id' column ───────────────────────────────────
    sql_no_strings = re.sub(r"'[^']*'", "''", sql)
    if re.search(r'\bid\b', sql_no_strings, re.IGNORECASE):
        # The query uses 'id'. Do ANY of the queried tables actually have 'id'?
        has_id_table = False
        queried_tables = [match.group(1).lower() for match in _FROM_ALIAS_PAT.finditer(sql)]
        for t in queried_tables:
            if t in SCHEMA and "id" in SCHEMA[t]:
                has_id_table = True
                break
        
        if not has_id_table:
            result.is_valid = False
            result.errors.append("Column 'id' does not exist on any queried tables.")
            result.hint = (
                "You used the column 'id', but none of the queried tables have an 'id' column. "
                "Use the correct primary/foreign keys (e.g., student_id, faculty_id, department_id, tt_id, attempt_id)."
            )

    # ── Check 6: Alias-to-table mapping conflicts ─────────────────────────────
    alias_map = _build_alias_map(sql)
    alias_errors = _check_alias_columns(sql, alias_map)
    if alias_errors:
        result.errors.extend(alias_errors)
        if result.is_valid:
            result.is_valid = False
        result.hint = (
            "Column/table mismatch detected. Check the schema:\n"
            + "\n".join(f"  • {e}" for e in alias_errors)
            + "\n\nImportant timetable rules:\n"
            + "  • class_timetable uses id and hour_number.\n"
            + "  • Do not use class_timetable.tt_id or class_timetable.slot_id.\n"
            + "  • Join time_slots with ts.hour_number = ct.hour_number for class timetables."
        )

    # Final validity determination
    if result.errors and result.fixed_sql is None:
        result.is_valid = False
        if not result.hint:
            common_rules = "\n".join(f"  - {rule}" for rule in COMMON_PROBLEMS)
            result.hint = (
                "Previous SQL had schema errors: " + "; ".join(result.errors) + ".\n\n"
                "COMMON SCHEMA RULES TO FOLLOW:\n" + common_rules
            )
    elif result.fixed_sql:
        # We have a fix — treat original as invalid but provide fix
        result.is_valid = False   # caller should use fixed_sql instead

    return result


# ── Auto-fixer ────────────────────────────────────────────────────────────────
def _fix_timetable_on_faculty(sql: str) -> str:
    """
    Rewrite SQL where timetable columns (day_of_week, slot_id, etc.) are
    incorrectly placed on the faculty table/alias.

    Strategy:
      1. Extract SELECT and WHERE columns.
      2. Move timetable columns from faculty alias → ft alias.
      3. Ensure FROM clause uses faculty_timetable ft as base.
    """
    # Move alias references: f.day_of_week → ft.day_of_week (etc.)
    fixed = _FACULTY_TT_COL_PAT.sub(
        lambda m: f"ft.{m.group(1).lower()}", sql
    )

    # Ensure faculty_timetable is in FROM clause
    has_ft = bool(re.search(r'\bfaculty_timetable\b', fixed, re.IGNORECASE))
    has_faculty_from = bool(re.search(
        r'\bFROM\s+faculty\b|\bFROM\s+faculty\s+(?:AS\s+)?f\b', fixed, re.IGNORECASE
    ))

    if not has_ft and has_faculty_from:
        # Replace "FROM faculty [AS] f" with proper timetable join
        fixed = re.sub(
            r'\bFROM\s+faculty\s+(?:AS\s+)?f?\b',
            'FROM faculty_timetable ft JOIN faculty f ON ft.faculty_id = f.faculty_id',
            fixed,
            flags=re.IGNORECASE,
        )
        # Add time_slots join if hour_number is referenced
        if 'ts.hour_number' in fixed and 'time_slots' not in fixed:
            fixed = re.sub(
                r'(JOIN faculty f ON ft\.faculty_id = f\.faculty_id)',
                r'\1 JOIN time_slots ts ON ft.slot_id = ts.slot_id',
                fixed,
                flags=re.IGNORECASE,
            )

    return fixed.strip()


def _build_alias_map(sql: str) -> dict[str, str]:
    """
    Parse FROM and JOIN clauses to build alias → table_name mapping.
    e.g.  "FROM faculty f JOIN time_slots ts" → {"f": "faculty", "ts": "time_slots"}
    """
    alias_map: dict[str, str] = {}
    for match in _FROM_ALIAS_PAT.finditer(sql):
        table, alias = match.group(1).lower(), match.group(2).lower()
        if table in SCHEMA:
            alias_map[alias] = table
            # Also map bare table name to itself
            alias_map[table] = table
    return alias_map


def _check_alias_columns(sql: str, alias_map: dict[str, str]) -> list[str]:
    """
    For each alias.column reference in the SQL, check that the column
    actually exists on the resolved table.

    Skips aliases not found in alias_map (subquery aliases, CTEs, etc.)
    """
    errors: list[str] = []
    seen: set[tuple] = set()

    for match in _ALIAS_COL_PAT.finditer(sql):
        alias = match.group(1).lower()
        col   = match.group(2).lower()

        if (alias, col) in seen:
            continue
        seen.add((alias, col))

        if alias not in alias_map:
            continue   # unknown alias — could be subquery/CTE, skip

        table = alias_map[alias]
        if table not in SCHEMA:
            continue   # unknown table — skip

        if col not in SCHEMA[table]:
            # Is it a timetable column on faculty?
            if table == "faculty" and col in _TIMETABLE_ONLY_COLS:
                errors.append(
                    f"'{alias}.{col}' — column '{col}' belongs to "
                    f"faculty_timetable, NOT faculty."
                )
            elif table == "faculty_timetable" and col == "hour_number":
                errors.append(
                    f"'{alias}.{col}' — column 'hour_number' does not exist on table 'faculty_timetable'. "
                    f"Use '{alias}.slot_id' and join time_slots on slot_id."
                )
            elif table == "class_timetable" and col == "tt_id":
                errors.append(
                    f"'{alias}.{col}' — column 'tt_id' does not exist on table 'class_timetable'. "
                    f"Use '{alias}.id' instead."
                )
            elif table == "class_timetable" and col == "slot_id":
                errors.append(
                    f"'{alias}.{col}' — column 'slot_id' does not exist on table 'class_timetable'. "
                    f"Use '{alias}.hour_number' and join time_slots on hour_number."
                )
            else:
                errors.append(
                    f"'{alias}.{col}' — column '{col}' does not exist on table '{table}'."
                )

    return errors


# ── Convenience: build a retry hint from a DB execution error ─────────────────
def hint_from_db_error(sql: str, db_error: str) -> str:
    """
    Given a PostgreSQL error message from a failed query, generate a targeted
    hint string for the LLM to use when regenerating the SQL.
    """
    err = db_error.lower()

    if "column" in err and "does not exist" in err:
        # Extract column name from error
        col_match = re.search(r'column "([^"]+)" does not exist', db_error, re.IGNORECASE)
        col = col_match.group(1) if col_match else "unknown"
        return (
            f"PostgreSQL error: column '{col}' does not exist. "
            f"Check the schema and use only valid column names. "
            f"Bad SQL: {sql[:300]}"
        )

    if "relation" in err and "does not exist" in err:
        rel_match = re.search(r'relation "([^"]+)" does not exist', db_error, re.IGNORECASE)
        rel = rel_match.group(1) if rel_match else "unknown"
        return (
            f"PostgreSQL error: table/view '{rel}' does not exist. "
            f"Valid tables: departments, students, faculty, subjects, "
            f"faculty_timetable, class_timetable, time_slots, student_subject_attempts, "
            f"vw_arrear_count. Bad SQL: {sql[:300]}"
        )

    if "syntax error" in err:
        return (
            f"PostgreSQL syntax error: {db_error[:200]}. "
            f"Regenerate a syntactically valid SELECT. Bad SQL: {sql[:300]}"
        )

    if "ambiguous" in err:
        col_match = re.search(r'column "([^"]+)" is ambiguous', db_error, re.IGNORECASE)
        col = col_match.group(1) if col_match else "unknown"
        return (
            f"Column '{col}' is ambiguous — qualify it with the table alias "
            f"(e.g. f.{col} or ft.{col}). Bad SQL: {sql[:300]}"
        )

    if "grouping error" in err or "group by" in err:
        return (
            "PostgreSQL grouping error: When using COUNT(), SUM(), AVG(), MIN(), MAX() or other aggregate functions, "
            "you MUST include a GROUP BY clause that lists ALL non-aggregated columns in the SELECT list. "
            "Example: SELECT student_id, COUNT(*) FROM students GROUP BY student_id. "
            f"Bad SQL: {sql[:300]}"
        )

    # Generic fallback
    return (
        f"PostgreSQL error: {db_error[:300]}. "
        f"Fix the SQL and return only a corrected SELECT. Previous SQL: {sql[:300]}"
    )