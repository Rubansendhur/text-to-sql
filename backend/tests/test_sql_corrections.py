import sys
import types
import unittest

if "core.rag_engine" not in sys.modules:
    rag_engine_stub = types.ModuleType("core.rag_engine")
    rag_engine_stub.get_rag_engine = lambda: None
    sys.modules["core.rag_engine"] = rag_engine_stub

from core.sql_ast import try_parse, render
from core.sql_corrections import apply_schema_corrections, apply_department_scope


class SchemaCorrectionRuleTests(unittest.TestCase):
    def test_rule1_day_of_week_ts_to_ft(self):
        sql = (
            "SELECT ft.faculty_id FROM faculty_timetable ft "
            "JOIN time_slots ts ON ft.slot_id = ts.slot_id WHERE ts.day_of_week = 'Mon'"
        )
        out = apply_schema_corrections(sql)
        self.assertIn("day_of_week_ts_to_ft", out.applied_rules)
        self.assertNotIn("ts.day_of_week", out.sql)
        self.assertIn("ft.day_of_week", out.sql)

    def test_rule2_current_semester_derived(self):
        sql = "SELECT s.register_number FROM students s WHERE s.current_semester = 8"
        out = apply_schema_corrections(sql)
        self.assertIn("current_semester_derived", out.applied_rules)
        self.assertNotIn("current_semester", out.sql)
        self.assertIn("admission_year", out.sql)

    def test_rule3_exam_year_eq_current_semester(self):
        sql = "SELECT student_id FROM student_subject_attempts WHERE exam_year = current_semester"
        out = apply_schema_corrections(sql)
        self.assertIn("exam_year_eq_current_semester", out.applied_rules)
        self.assertNotIn("current_semester", out.sql)

    def test_rule4_class_timetable_pk_and_hour(self):
        sql = "SELECT ct.tt_id, ct.slot_id FROM class_timetable ct"
        out = apply_schema_corrections(sql)
        self.assertIn("class_timetable_tt_id_to_id", out.applied_rules)
        self.assertIn("class_timetable_slot_id_to_hour_number", out.applied_rules)
        self.assertIn("ct.id", out.sql)
        self.assertIn("ct.hour_number", out.sql)

    def test_rule5_injects_missing_time_slots_join(self):
        sql = (
            "SELECT ft.day_of_week, ts.hour_number FROM faculty_timetable ft "
            "WHERE ts.hour_number = 2"
        )
        out = apply_schema_corrections(sql)
        self.assertIn("inject_missing_time_slots_join", out.applied_rules)
        self.assertIn("time_slots", out.sql.lower())
        self.assertIn("JOIN", out.sql)

    def test_rule6_count_id_to_real_pk(self):
        sql = "SELECT COUNT(s.id) FROM students s"
        out = apply_schema_corrections(sql)
        self.assertIn("count_id_to_real_pk", out.applied_rules)
        self.assertIn("student_id", out.sql)
        self.assertNotIn("COUNT(s.id)", out.sql)

    def test_rule7_timetable_col_on_faculty_alias(self):
        sql = (
            "SELECT f.day_of_week FROM faculty_timetable ft "
            "JOIN faculty f ON ft.faculty_id = f.faculty_id"
        )
        out = apply_schema_corrections(sql)
        self.assertIn("timetable_col_on_faculty_alias", out.applied_rules)
        self.assertIn("ft.day_of_week", out.sql)

    def test_rule8_free_period_literal_to_occupancy_query(self):
        sql = (
            "SELECT f.full_name FROM faculty_timetable ft "
            "JOIN faculty f ON ft.faculty_id = f.faculty_id "
            "JOIN time_slots ts ON ft.slot_id = ts.slot_id "
            "WHERE ft.activity = 'Free Period' AND ft.day_of_week = 'Mon' AND ts.hour_number = 2"
        )
        out = apply_schema_corrections(sql)
        self.assertIn("free_period_literal_to_occupancy_query", out.applied_rules)
        self.assertIn("NOT IN", out.sql)
        self.assertNotIn("Free Period", out.sql)

    def test_clean_query_no_rules_applied(self):
        sql = "SELECT s.register_number, s.name FROM students s WHERE s.status = 'Active'"
        out = apply_schema_corrections(sql)
        self.assertEqual(out.applied_rules, [])
        # sqlglot's render isn't guaranteed byte-identical (e.g. explicit AS) —
        # compare via re-parsed AST rather than raw string equality.
        self.assertEqual(render(try_parse(out.sql)), render(try_parse(sql)))

    def test_unparseable_sql_returns_unchanged(self):
        sql = "SELECT * FROM foo WHERE ("
        out = apply_schema_corrections(sql)
        self.assertFalse(out.parsed)
        self.assertEqual(out.applied_rules, [])
        self.assertEqual(out.sql, sql)


class DepartmentScopeTests(unittest.TestCase):
    def test_injects_exists_predicate(self):
        sql = "SELECT s.name FROM students s WHERE s.status = 'Active'"
        new_sql, changed = apply_department_scope(sql, "DCS")
        self.assertTrue(changed)
        self.assertIn("EXISTS", new_sql)
        self.assertIn("department_code = 'DCS'", new_sql)

    def test_no_anchor_table_no_change(self):
        sql = "SELECT 1"
        new_sql, changed = apply_department_scope(sql, "DCS")
        self.assertFalse(changed)
        self.assertEqual(new_sql, sql)


if __name__ == "__main__":
    unittest.main()
