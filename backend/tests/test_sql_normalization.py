import sys
import types
import unittest

# Avoid importing optional heavy dependencies while testing normalization only.
if "core.rag_engine" not in sys.modules:
    rag_engine_stub = types.ModuleType("core.rag_engine")
    rag_engine_stub.get_rag_engine = lambda: None
    sys.modules["core.rag_engine"] = rag_engine_stub

from core.chat_helpers import normalize_sql


class NormalizeSqlRegressionTests(unittest.TestCase):
    def test_rewrites_exam_year_equals_current_semester(self):
        raw_sql = (
            "SELECT student_id FROM student_subject_attempts "
            "WHERE exam_year = current_semester AND grade IN ('U','AB')"
        )

        normalized = normalize_sql(raw_sql)

        self.assertNotIn("exam_year = current_semester", normalized.lower())
        self.assertIn("exam_year = EXTRACT(YEAR FROM CURRENT_DATE)::int", normalized)

    def test_rewrites_current_semester_equals_exam_year(self):
        raw_sql = (
            "SELECT student_id FROM student_subject_attempts "
            "WHERE current_semester = exam_year"
        )

        normalized = normalize_sql(raw_sql)

        self.assertNotIn("current_semester = exam_year", normalized.lower())
        self.assertIn("EXTRACT(YEAR FROM CURRENT_DATE)::int = exam_year", normalized)


if __name__ == "__main__":
    unittest.main()
