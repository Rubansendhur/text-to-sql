import sys
import types
import unittest

# Avoid importing optional heavy dependencies while testing normalization only.
if "core.rag_engine" not in sys.modules:
    rag_engine_stub = types.ModuleType("core.rag_engine")
    rag_engine_stub.get_rag_engine = lambda: None
    sys.modules["core.rag_engine"] = rag_engine_stub

from core.sql_corrections import apply_schema_corrections


class SchemaCorrectionsRegressionTests(unittest.TestCase):
    """Regression coverage for rules formerly implemented via regex in
    chat_helpers.normalize_sql, now implemented as AST rewrites in
    core.sql_corrections (see core/sql_ast.py)."""

    def test_rewrites_exam_year_equals_current_semester(self):
        raw_sql = (
            "SELECT student_id FROM student_subject_attempts "
            "WHERE exam_year = current_semester AND grade IN ('U','AB')"
        )

        outcome = apply_schema_corrections(raw_sql)

        self.assertIn("exam_year_eq_current_semester", outcome.applied_rules)
        self.assertNotIn("exam_year = current_semester", outcome.sql.lower())
        self.assertIn("EXTRACT(YEAR FROM CURRENT_DATE)", outcome.sql)

    def test_rewrites_current_semester_equals_exam_year(self):
        raw_sql = (
            "SELECT student_id FROM student_subject_attempts "
            "WHERE current_semester = exam_year"
        )

        outcome = apply_schema_corrections(raw_sql)

        self.assertIn("current_semester_eq_exam_year", outcome.applied_rules)
        self.assertNotIn("current_semester = exam_year", outcome.sql.lower())
        self.assertIn("EXTRACT(YEAR FROM CURRENT_DATE)", outcome.sql)


if __name__ == "__main__":
    unittest.main()
