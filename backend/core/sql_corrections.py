"""
core/sql_corrections.py
─────────────────────────
Deterministic, 1:1 schema-drift corrections applied to LLM-generated SQL
before validation/execution. Each rule is a pure AST rewrite (see
core/sql_ast.py) driven by known facts from core/schema_catalog.py.

These are NOT heuristics or guesses — every rule here corrects a SQL
construct that is unconditionally wrong given the fixed database schema
(e.g. day_of_week never exists on time_slots; class_timetable's PK is always
`id`, never `tt_id`). That determinism is what makes it safe to apply
automatically without an LLM round-trip — same justification as the
regex-based rules in chat_helpers.normalize_sql this module replaces.

Replaces (from chat_helpers.py): the schema-drift block inside
normalize_sql(), force_department_scope(), inject_scope_predicate().
Also absorbs sql_validator._fix_timetable_on_faculty (validator becomes pure
detect+hint, no mutation).

Fire-and-forget correction logging (core.sql_correction_log) records every
rule that actually fired, for the eventual sqlcoder/llama3.2 fine-tuning
dataset.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlglot import exp, parse_one, to_identifier

from core.sql_ast import (
    try_parse,
    render,
    iter_selects,
    get_table_aliases,
    substitute_column_ref,
    substitute_column_expr,
    add_predicate,
    add_join,
    find_anchor_alias,
)
from core.schema_catalog import get_primary_key, DEPARTMENT_SCOPE_ANCHOR_TABLES

log = logging.getLogger(__name__)

# current_semester is NOT a stored column anywhere — it's derived from
# admission_year. TODO: if a Postgres VIEW/generated column for
# current_semester is ever added to the schema, this rule (and rule 3 below)
# can be deleted entirely in favor of the model just querying the real column.
SEMESTER_EXPR_SQL = (
    "(EXTRACT(YEAR FROM CURRENT_DATE)::int - {alias}.admission_year) * 2 "
    "+ CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END"
)
YEAR_EXPR_SQL = "EXTRACT(YEAR FROM CURRENT_DATE)::int"


@dataclass
class CorrectionOutcome:
    sql: str
    applied_rules: list[str] = field(default_factory=list)
    parsed: bool = False


def _literal_str(node: exp.Expression | None) -> str | None:
    if isinstance(node, exp.Literal) and node.is_string:
        return node.this
    return None


def _literal_int(node: exp.Expression | None) -> int | None:
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return int(node.this)
        except (TypeError, ValueError):
            return None
    return None


def apply_schema_corrections(sql: str) -> CorrectionOutcome:
    """AST-based replacement for chat_helpers.normalize_sql's schema-drift
    rules. Returns the input SQL unchanged (parsed=False) if sqlglot cannot
    parse it — callers fall back to running validate_sql on the raw string,
    which surfaces a 'could not parse SQL' error via its own AST-parse-first
    check."""
    # Strip a duplicated leading "SELECT SELECT" (a common LLM artifact) —
    # this must happen before parsing since sqlglot cannot parse it at all.
    sql = re.sub(r"^\s*SELECT\s+SELECT\b", "SELECT", sql, flags=re.IGNORECASE).strip()

    tree = try_parse(sql)
    if tree is None:
        return CorrectionOutcome(sql=sql, parsed=False)

    applied: list[str] = []

    for select in iter_selects(tree):
        refs = {r.alias: r.name for r in get_table_aliases(select)}

        # Rule 1: ts.day_of_week -> ft.day_of_week (day_of_week lives on
        # faculty_timetable, not time_slots).
        ft_alias = next((a for a, t in refs.items() if t == "faculty_timetable"), None)
        ts_alias = next((a for a, t in refs.items() if t == "time_slots"), None)
        if ft_alias and ts_alias:
            if substitute_column_ref(
                select, old_alias=ts_alias, old_col="day_of_week",
                new_alias=ft_alias, new_col="day_of_week",
            ):
                applied.append("day_of_week_ts_to_ft")

        # Rule 2: alias.current_semester -> derived expression (students only).
        for alias, table in refs.items():
            if table == "students":
                expr_sql = SEMESTER_EXPR_SQL.format(alias=alias)
                if substitute_column_expr(select, alias=alias, col="current_semester", replacement_sql=expr_sql):
                    applied.append("current_semester_derived")

        # Rule 4: class_timetable.tt_id -> .id ; class_timetable.slot_id -> .hour_number
        # (class_timetable's real PK is `id`, and it stores hour_number
        # directly — unlike faculty_timetable which has slot_id -> time_slots.hour_number).
        for alias, table in refs.items():
            if table == "class_timetable":
                if substitute_column_ref(select, old_alias=alias, old_col="tt_id", new_alias=alias, new_col="id"):
                    applied.append("class_timetable_tt_id_to_id")
                if substitute_column_ref(select, old_alias=alias, old_col="slot_id", new_alias=alias, new_col="hour_number"):
                    applied.append("class_timetable_slot_id_to_hour_number")

        # Rule 6: COUNT(alias.id) -> COUNT(alias.<real_pk>) — 'id' is not the
        # real PK on most tables here.
        for count_fn in select.find_all(exp.Count):
            for col in count_fn.find_all(exp.Column):
                if col.name.lower() == "id" and col.table:
                    table = refs.get(col.table.lower())
                    pk = get_primary_key(table) if table else None
                    if pk and pk != "id":
                        col.set("this", to_identifier(pk))
                        applied.append("count_id_to_real_pk")

        # Rule 7 (moved from sql_validator._fix_timetable_on_faculty):
        # timetable-only columns placed on the faculty alias instead of
        # faculty_timetable. Only auto-fixable when faculty_timetable is
        # already joined in this branch — otherwise sql_validator still
        # flags it as an error with a retry hint (adding a whole new FROM
        # table here would be a much larger structural guess than the other
        # rules are comfortable making).
        faculty_alias = next((a for a, t in refs.items() if t == "faculty"), None)
        if faculty_alias and ft_alias:
            for col_name in ("day_of_week", "slot_id", "hour_number", "activity", "sem_batch"):
                if substitute_column_ref(
                    select, old_alias=faculty_alias, old_col=col_name,
                    new_alias=ft_alias, new_col=col_name,
                ):
                    applied.append("timetable_col_on_faculty_alias")

        # Rule 5: inject missing `time_slots ts` join when ts.* is
        # referenced but time_slots isn't joined in this branch. Catches
        # generated SQL that uses ts.hour_number/ts.start_time in
        # SELECT/ORDER BY but forgets the LEFT JOIN.
        ts_referenced = any(
            c.table and c.table.lower() == "ts" for c in select.find_all(exp.Column)
        )
        if ts_referenced and "time_slots" not in refs.values() and ft_alias:
            add_join(select, f"SELECT 1 FROM x LEFT JOIN time_slots ts ON {ft_alias}.slot_id = ts.slot_id")
            applied.append("inject_missing_time_slots_join")

    # Rule 3: exam_year = current_semester (both directions) — repair of an
    # invalid predicate against student_subject_attempts. Runs on the whole
    # tree (not per-branch) since it's a simple expression swap.
    for eq in tree.find_all(exp.EQ):
        left, right = eq.this, eq.expression
        if isinstance(left, exp.Column) and left.name.lower() == "exam_year" and \
           isinstance(right, exp.Column) and right.name.lower() == "current_semester":
            right.replace(parse_one(YEAR_EXPR_SQL, read="postgres"))
            applied.append("exam_year_eq_current_semester")
        elif isinstance(right, exp.Column) and right.name.lower() == "exam_year" and \
                isinstance(left, exp.Column) and left.name.lower() == "current_semester":
            left.replace(parse_one(YEAR_EXPR_SQL, read="postgres"))
            applied.append("current_semester_eq_exam_year")

    # Rule 8: LLM hallucinates `ft.activity = 'Free Period'` (a literal-value
    # check) instead of the correct NOT-EXISTS occupancy check. Detected via
    # AST inspection (not regex on raw text) — replaces the whole query with
    # the correct free-faculty occupancy query when we can recover a day and
    # an hour literal from the original SQL.
    #
    # NOTE: this is a safety net for the fallthrough case where a "who is
    # free" question doesn't trigger chat_helpers.build_free_staff_sql's
    # pre-LLM shortcut (e.g. no explicit staff/faculty keyword). Keeping it
    # here — as a tested rule instead of an untested regex block — rather
    # than deleting it outright.
    fixed_free_query = _fix_free_period_literal(tree)
    if fixed_free_query is not None:
        return CorrectionOutcome(sql=fixed_free_query, applied_rules=["free_period_literal_to_occupancy_query"], parsed=True)

    result_sql = render(tree)
    return CorrectionOutcome(sql=result_sql, applied_rules=applied, parsed=True)


def _fix_free_period_literal(tree: exp.Expression) -> str | None:
    """If the query checks ft.activity = 'Free Period' with a day and hour
    literal present, rebuild it as the correct occupancy-based query.
    Returns None if the pattern isn't present."""
    day = None
    hour = None
    dept = None

    for eq in tree.find_all(exp.EQ):
        left, right = eq.this, eq.expression
        if isinstance(left, exp.Column) and left.name.lower() == "day_of_week":
            val = _literal_str(right)
            if val:
                day = val
        if isinstance(left, exp.Column) and left.name.lower() == "hour_number":
            val = _literal_int(right)
            if val is not None:
                hour = val
        if isinstance(left, exp.Column) and left.name.lower() == "department_code":
            val = _literal_str(right)
            if val:
                dept = val

    has_free_period_literal = any(
        isinstance(eq.this, exp.Column) and eq.this.name.lower() == "activity"
        and (_literal_str(eq.expression) or "").strip().lower() == "free period"
        for eq in tree.find_all(exp.EQ)
    )
    if not (has_free_period_literal and day and hour is not None):
        return None

    safe_day = day.replace("'", "''")
    where_parts = ["f.is_active = TRUE"]
    if dept:
        safe_dept = dept.replace("'", "''")
        where_parts.insert(0, f"d.department_code = '{safe_dept}'")

    query = (
        "SELECT f.full_name, f.designation "
        "FROM faculty f "
        "JOIN departments d ON f.department_id = d.department_id "
        f"WHERE {' AND '.join(where_parts)} "
        "AND f.faculty_id NOT IN ("
        "SELECT ft.faculty_id "
        "FROM faculty_timetable ft "
        "JOIN time_slots ts ON ft.slot_id = ts.slot_id "
        f"WHERE ft.day_of_week = '{safe_day}' "
        f"AND ts.hour_number = {hour}"
        ") "
        "ORDER BY f.full_name"
    )
    return query


def apply_department_scope(sql: str, department_code: str) -> tuple[str, bool]:
    """Inject a deterministic department-scope EXISTS predicate for common
    table aliases when the model forgets it. Replaces
    chat_helpers.force_department_scope/inject_scope_predicate — uses AST
    manipulation instead of a hand-rolled paren-depth string scanner.
    Correctly scopes every branch of a UNION query (see sql_ast.add_predicate)."""
    tree = try_parse(sql)
    if tree is None or not department_code:
        return sql, False

    anchor_alias = find_anchor_alias(tree, DEPARTMENT_SCOPE_ANCHOR_TABLES)
    if not anchor_alias:
        return sql, False

    safe_dept = department_code.replace("'", "''")
    predicate_sql = (
        "EXISTS (SELECT 1 FROM departments d_scope "
        f"WHERE d_scope.department_id = {anchor_alias}.department_id "
        f"AND d_scope.department_code = '{safe_dept}')"
    )
    add_predicate(tree, predicate_sql, anchor_alias=anchor_alias)
    return render(tree), True
