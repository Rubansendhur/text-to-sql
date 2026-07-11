"""
core/schema_catalog.py
───────────────────────
Single source of truth for machine-checkable schema facts: table -> column
set, primary keys, and department-scope anchor tables. Consumed by
sql_validator.py and sql_corrections.py so table/column/PK knowledge is
defined exactly once instead of being duplicated across sql_validator.SCHEMA,
chat_helpers.pk_map, and ad-hoc alias regexes.

Does NOT replace core/rag_engine.py's DB_SCHEMA prompt-prose constant — that
is a separate, hand-tuned concern (prompt engineering for the LLM) and is out
of scope for this module.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSchema:
    columns: frozenset[str]
    primary_key: str | None = None   # None for tables/views with no single-col PK
    timetable_only: bool = False


# Table name -> TableSchema. Ported 1:1 from sql_validator.SCHEMA plus the
# pk_map previously duplicated in chat_helpers.py.
SCHEMA: dict[str, TableSchema] = {
    "departments": TableSchema(
        columns=frozenset({"department_id", "department_code", "department_name", "created_at"}),
        primary_key="department_id",
    ),
    "students": TableSchema(
        columns=frozenset({
            "student_id", "register_number", "name", "gender", "date_of_birth",
            "contact_number", "email", "department_id", "admission_year", "section",
            "hostel_status", "status", "cgpa", "created_at",
        }),
        primary_key="student_id",
    ),
    "faculty": TableSchema(
        columns=frozenset({
            "faculty_id", "title", "full_name", "designation", "email", "phone",
            "department_id", "is_hod", "is_active", "created_at",
            # Common mistake: these do NOT exist on faculty
            # day_of_week, slot_id, hour_number, activity, sem_batch → faculty_timetable
        }),
        primary_key="faculty_id",
    ),
    "subjects": TableSchema(
        columns=frozenset({
            "subject_id", "subject_code", "subject_name", "department_id",
            "semester_number", "subject_type", "lecture_hrs", "tutorial_hrs",
            "practical_hrs", "credits", "created_at",
        }),
        primary_key="subject_id",
    ),
    "parents": TableSchema(
        columns=frozenset({
            "parent_id", "student_id", "father_name", "mother_name",
            "father_contact_number", "mother_contact_number", "address",
        }),
        primary_key="parent_id",
    ),
    "student_subject_attempts": TableSchema(
        columns=frozenset({
            "attempt_id", "student_id", "subject_id", "exam_year", "exam_month",
            "grade", "created_at",
        }),
        primary_key="attempt_id",
    ),
    "student_subject_results": TableSchema(
        columns=frozenset({
            "id", "student_id", "subject_id", "semester_number", "grade",
            "exam_year", "exam_month", "created_at",
        }),
        primary_key="id",
    ),
    "student_semester_gpa": TableSchema(
        columns=frozenset({"student_id", "semester_number", "gpa", "total_credits"}),
        primary_key=None,   # composite key (student_id, semester_number)
    ),
    "faculty_timetable": TableSchema(
        columns=frozenset({
            "tt_id", "faculty_id", "day_of_week", "slot_id", "subject_id",
            "activity", "sem_batch", "department_id", "updated_at",
        }),
        primary_key="tt_id",
        timetable_only=True,
    ),
    "class_timetable": TableSchema(
        columns=frozenset({
            "id", "sem_batch", "department_id", "section", "day_of_week",
            "hour_number", "subject_id", "faculty_id", "activity",
        }),
        primary_key="id",
        timetable_only=True,
    ),
    "time_slots": TableSchema(
        columns=frozenset({"slot_id", "hour_number", "start_time", "end_time", "label"}),
        primary_key="slot_id",
    ),
    "users": TableSchema(
        columns=frozenset({"user_id", "username", "password", "role", "department_code"}),
        primary_key="user_id",
    ),
    # Views
    "vw_arrear_count": TableSchema(
        columns=frozenset({"register_number", "name", "status", "active_arrear_count"}),
        primary_key=None,
    ),
    "vw_timetable": TableSchema(
        columns=frozenset({
            "day_of_week", "hour_number", "time_range", "code", "subject",
            "subject_type", "faculty_name", "lecture_hall", "notes", "semester_number",
        }),
        primary_key=None,
    ),
}

# Columns that only ever live on timetable tables — used to flag "col on wrong alias" errors.
TIMETABLE_ONLY_COLS: frozenset[str] = frozenset({
    "day_of_week", "slot_id", "hour_number", "activity", "sem_batch",
})

# Common schema rules surfaced to the LLM in retry hints.
COMMON_PROBLEMS: list[str] = [
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

# Tables treated as anchors for department-scope injection, in priority order.
DEPARTMENT_SCOPE_ANCHOR_TABLES: tuple[str, ...] = (
    "students", "faculty", "subjects", "class_timetable", "faculty_timetable",
)


def get_table_names() -> frozenset[str]:
    return frozenset(SCHEMA.keys())


def get_primary_key(table: str) -> str | None:
    t = SCHEMA.get(table.lower())
    return t.primary_key if t else None


def get_columns(table: str) -> frozenset[str]:
    t = SCHEMA.get(table.lower())
    return t.columns if t else frozenset()


def table_exists(table: str) -> bool:
    return table.lower() in SCHEMA
