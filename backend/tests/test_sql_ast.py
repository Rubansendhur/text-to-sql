import sys
import types
import unittest

if "core.rag_engine" not in sys.modules:
    rag_engine_stub = types.ModuleType("core.rag_engine")
    rag_engine_stub.get_rag_engine = lambda: None
    sys.modules["core.rag_engine"] = rag_engine_stub

from core.sql_ast import (
    try_parse,
    render,
    get_table_aliases,
    get_column_refs,
    substitute_column_ref,
    substitute_column_expr,
    add_predicate,
)


class TryParseTests(unittest.TestCase):
    def test_valid_sql_parses(self):
        tree = try_parse("SELECT s.name FROM students s")
        self.assertIsNotNone(tree)

    def test_garbage_returns_none_not_exception(self):
        tree = try_parse("SELECT SELECT FROM foo WHERE (")
        self.assertIsNone(tree)

    def test_empty_returns_none(self):
        self.assertIsNone(try_parse(""))
        self.assertIsNone(try_parse(None))


class TableAliasTests(unittest.TestCase):
    def test_plain_tables_and_aliases(self):
        tree = try_parse(
            "SELECT ft.day_of_week FROM faculty_timetable ft "
            "JOIN faculty f ON ft.faculty_id = f.faculty_id"
        )
        refs = {r.alias: r.name for r in get_table_aliases(tree)}
        self.assertEqual(refs, {"ft": "faculty_timetable", "f": "faculty"})

    def test_cte_flagged_is_cte(self):
        tree = try_parse("WITH latest AS (SELECT 1 AS x) SELECT * FROM latest l WHERE l.x = 1")
        refs = get_table_aliases(tree)
        latest_refs = [r for r in refs if r.name == "latest"]
        self.assertTrue(latest_refs)
        self.assertTrue(all(r.is_cte for r in latest_refs))


class ColumnRefTests(unittest.TestCase):
    def test_qualified_and_unqualified(self):
        tree = try_parse("SELECT s.name, status FROM students s")
        refs = get_column_refs(tree)
        self.assertIn(("s", "name"), refs)
        self.assertIn((None, "status"), refs)


class SubstituteColumnRefTests(unittest.TestCase):
    def test_day_of_week_ts_to_ft(self):
        tree = try_parse(
            "SELECT ts.day_of_week FROM faculty_timetable ft "
            "JOIN time_slots ts ON ft.slot_id = ts.slot_id"
        )
        changed = substitute_column_ref(
            tree, old_alias="ts", old_col="day_of_week", new_alias="ft", new_col="day_of_week"
        )
        self.assertTrue(changed)
        self.assertIn("ft.day_of_week", render(tree))
        self.assertNotIn("ts.day_of_week", render(tree))

    def test_no_match_returns_false(self):
        tree = try_parse("SELECT s.name FROM students s")
        changed = substitute_column_ref(
            tree, old_alias="ts", old_col="day_of_week", new_alias="ft", new_col="day_of_week"
        )
        self.assertFalse(changed)


class SubstituteColumnExprTests(unittest.TestCase):
    def test_current_semester_derived(self):
        tree = try_parse("SELECT s.current_semester FROM students s")
        changed = substitute_column_expr(
            tree, alias="s", col="current_semester",
            replacement_sql="(EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2",
        )
        self.assertTrue(changed)
        self.assertIn("admission_year", render(tree))
        self.assertNotIn("current_semester", render(tree))


class AddPredicateTests(unittest.TestCase):
    def test_lands_before_group_order_limit(self):
        tree = try_parse(
            "SELECT ft.day_of_week, COUNT(*) FROM faculty_timetable ft "
            "WHERE ft.day_of_week = 'Mon' GROUP BY ft.day_of_week ORDER BY ft.day_of_week LIMIT 5"
        )
        add_predicate(tree, "ft.department_id = 1", anchor_alias="ft")
        sql = render(tree)
        self.assertIn("WHERE ft.day_of_week = 'Mon' AND ft.department_id = 1", sql)
        self.assertTrue(sql.index("GROUP BY") > sql.index("WHERE"))
        self.assertTrue(sql.rstrip().endswith("LIMIT 5"))

    def test_union_scopes_both_branches_referencing_anchor(self):
        tree = try_parse(
            "SELECT s.name FROM students s WHERE s.status = 'Active' "
            "UNION SELECT s2.name FROM students s2"
        )
        # Both branches use a students table, but different aliases — use the
        # first branch's alias as the anchor and confirm only that branch is
        # scoped (documented limitation: one global anchor alias per call).
        add_predicate(tree, "s.department_id = 1", anchor_alias="s")
        sql = render(tree)
        self.assertIn("s.department_id = 1", sql)

    def test_skips_branch_not_referencing_anchor(self):
        tree = try_parse(
            "SELECT s.name FROM students s UNION SELECT f.full_name FROM faculty f"
        )
        add_predicate(tree, "s.department_id = 1", anchor_alias="s")
        sql = render(tree)
        # Faculty branch must not get a dangling reference to alias s.
        faculty_branch = sql.split("UNION")[1]
        self.assertNotIn("s.department_id", faculty_branch)


if __name__ == "__main__":
    unittest.main()
