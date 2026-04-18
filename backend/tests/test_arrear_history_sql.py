import sys
import types
import unittest

# Stub optional dependency chain used by chat_helpers import.
if "core.rag_engine" not in sys.modules:
    rag_engine_stub = types.ModuleType("core.rag_engine")
    rag_engine_stub.get_rag_engine = lambda: None
    sys.modules["core.rag_engine"] = rag_engine_stub

from core.chat_helpers import build_active_vs_history_arrears_sql


class ActiveVsHistoryArrearSqlTests(unittest.TestCase):
    def test_builds_sql_for_active_and_history_count_question(self):
        question = "how many students have active arrears and how many have history of arrears?"

        sql = build_active_vs_history_arrears_sql(
            question=question,
            department_code="DCS",
            is_central_admin=False,
        )

        self.assertIsNotNone(sql)
        assert sql is not None
        self.assertIn("active_students_count", sql)
        self.assertIn("history_students_count", sql)
        self.assertIn("ever_had_arrear_count", sql)
        self.assertIn("d.department_code = 'DCS'", sql)

    def test_returns_none_for_active_only_prompt(self):
        question = "show students with active arrears"

        sql = build_active_vs_history_arrears_sql(
            question=question,
            department_code="DCS",
            is_central_admin=False,
        )

        self.assertIsNone(sql)


if __name__ == "__main__":
    unittest.main()
