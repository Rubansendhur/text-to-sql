"""
core/sql_ast.py
─────────────────
Thin wrapper around sqlglot for AST-based SQL manipulation, replacing the
paren-depth string scanner and per-module alias regex previously duplicated
in chat_helpers.py and sql_validator.py.

Dialect: all parsing/rendering uses dialect="postgres" (matches the
asyncpg/psycopg2 target and Postgres-specific syntax already in use:
EXTRACT(...)::int, ILIKE, etc).

Design principle: every function here is a pure function over an AST or SQL
string. No DB access, no LLM calls — fully unit-testable offline. Nothing
else in the codebase should `import sqlglot` directly; that keeps the blast
radius of a future sqlglot version bump (or a decision to rip it out) to
this one file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

log = logging.getLogger(__name__)

DIALECT = "postgres"


@dataclass(frozen=True)
class TableRef:
    name: str            # lowercased real table/CTE name
    alias: str           # lowercased alias (== name if unaliased)
    is_cte: bool = False


def try_parse(sql: str) -> exp.Expression | None:
    """Parse SQL into a sqlglot AST. Never raises — returns None on parse
    failure. Callers must treat None as 'could not verify structurally',
    not as a crash."""
    if not sql or not sql.strip():
        return None
    try:
        return sqlglot.parse_one(sql, read=DIALECT)
    except Exception as e:
        log.warning("sql_ast.try_parse: parse failed (%s): %.200s", e, sql)
        return None


def render(node: exp.Expression) -> str:
    """Render an AST back to SQL text (postgres dialect)."""
    return node.sql(dialect=DIALECT)


def iter_selects(node: exp.Expression):
    """Yield every exp.Select branch reachable through set operations
    (UNION/INTERSECT/EXCEPT) so callers can apply a rewrite to ALL branches
    instead of just the outermost node. Plain single-SELECT trees yield
    themselves. Subquery/CTE-internal SELECTs are NOT yielded — corrections
    only target the query's own top-level result set(s)."""
    if isinstance(node, exp.Select):
        yield node
    elif isinstance(node, (exp.Union, exp.Intersect, exp.Except)):
        yield from iter_selects(node.this)
        yield from iter_selects(node.expression)


def get_cte_names(node: exp.Expression) -> set[str]:
    return {cte.alias_or_name.lower() for cte in node.find_all(exp.CTE)}


def get_table_aliases(node: exp.Expression) -> list[TableRef]:
    """Return every FROM/JOIN table reference with its (lowercased) alias.
    Includes CTE references (is_cte=True) so callers can exclude them from
    'unknown table' checks without a separate regex pass."""
    cte_names = get_cte_names(node)
    refs: list[TableRef] = []
    for t in node.find_all(exp.Table):
        name = t.name.lower()
        alias = (t.alias_or_name or name).lower()
        refs.append(TableRef(name=name, alias=alias, is_cte=name in cte_names))
    return refs


def get_column_refs(node: exp.Expression) -> list[tuple[str | None, str]]:
    """Return (table_qualifier_or_None, column_name) for every column
    reference, lowercased. table_qualifier is None for unqualified columns."""
    out = []
    for c in node.find_all(exp.Column):
        tbl = c.table.lower() if c.table else None
        out.append((tbl, c.name.lower()))
    return out


def rename_column(node: exp.Expression, *, alias: str, old_col: str, new_col: str) -> exp.Expression:
    """Rename alias.old_col -> alias.new_col everywhere (in place, returns
    node for chaining). Keeps the same table qualifier — for changing both
    the alias AND the column name, use substitute_column_ref instead."""
    for c in node.find_all(exp.Column):
        if c.table.lower() == alias.lower() and c.name.lower() == old_col.lower():
            c.set("this", exp.to_identifier(new_col))
    return node


def substitute_column_ref(
    node: exp.Expression, *, old_alias: str, old_col: str, new_alias: str, new_col: str
) -> bool:
    """Replace old_alias.old_col with new_alias.new_col everywhere (in
    place). Returns True if any replacement was made. Covers cases like
    ts.day_of_week -> ft.day_of_week, and column-only renames where
    old_alias == new_alias (e.g. class_timetable.tt_id -> .id)."""
    changed = False
    for c in node.find_all(exp.Column):
        if c.table.lower() == old_alias.lower() and c.name.lower() == old_col.lower():
            c.set("table", exp.to_identifier(new_alias))
            c.set("this", exp.to_identifier(new_col))
            changed = True
    return changed


def substitute_column_expr(node: exp.Expression, *, alias: str, col: str, replacement_sql: str) -> bool:
    """Replace every occurrence of alias.col with a parsed SQL expression
    (e.g. the current_semester derived-year expression). Returns True if any
    replacement was made. Mutates node in place."""
    replacement = sqlglot.parse_one(replacement_sql, read=DIALECT)
    changed = False
    for c in list(node.find_all(exp.Column)):
        if c.table.lower() == alias.lower() and c.name.lower() == col.lower():
            c.replace(replacement.copy())
            changed = True
    return changed


def add_predicate(node: exp.Expression, predicate_sql: str, *, anchor_alias: str) -> exp.Expression:
    """AND `predicate_sql` into the WHERE clause of every top-level SELECT
    branch (handles UNION/INTERSECT/EXCEPT) that actually contains a
    FROM/JOIN reference to `anchor_alias`. Uses sqlglot's Select.where(),
    which already inserts before GROUP BY/ORDER BY/LIMIT/HAVING regardless
    of source clause order — replaces the hand-rolled paren-depth scanner
    entirely.

    IMPORTANT: calling .where() directly on a top-level exp.Union only
    patches the last branch (verified experimentally) — silently leaving
    earlier branches unscoped. This function walks every branch via
    iter_selects() instead. Subqueries/derived tables are not touched
    (matches prior regex behavior, which also only patched the outermost
    query text)."""
    predicate = sqlglot.condition(predicate_sql, dialect=DIALECT)
    for select in iter_selects(node):
        aliases = {t.alias.lower() for t in get_table_aliases(select)}
        # Only inject into branches that actually reference the anchor
        # alias — avoids adding a dangling EXISTS(...anchor...) into an
        # unrelated UNION arm.
        if anchor_alias.lower() in aliases:
            select.where(predicate.copy(), copy=False)
    return node


def add_join(select: exp.Select, join_sql: str) -> exp.Select:
    """Append a JOIN clause (parsed from a standalone snippet like
    'SELECT 1 FROM x LEFT JOIN time_slots ts ON ft.slot_id = ts.slot_id')
    to `select`'s join list, in place."""
    join_src = sqlglot.parse_one(join_sql, read=DIALECT)
    join_node = join_src.find(exp.Join)
    if join_node is None:
        return select
    joins = select.args.get("joins") or []
    joins.append(join_node.copy())
    select.set("joins", joins)
    return select


def find_anchor_alias(node: exp.Expression, candidate_tables: tuple[str, ...]) -> str | None:
    """Return the alias of the first table in candidate_tables (priority
    order) found anywhere in the query (searched across all SELECT
    branches, ignoring CTEs)."""
    refs = get_table_aliases(node)
    by_table: dict[str, str] = {}
    for r in refs:
        if not r.is_cte:
            by_table.setdefault(r.name, r.alias)
    for table in candidate_tables:
        if table in by_table:
            return by_table[table]
    return None
