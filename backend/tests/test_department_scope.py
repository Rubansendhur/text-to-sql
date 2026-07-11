import sys
import types
import unittest

if "core.rag_engine" not in sys.modules:
    rag_engine_stub = types.ModuleType("core.rag_engine")
    rag_engine_stub.get_rag_engine = lambda: None
    sys.modules["core.rag_engine"] = rag_engine_stub

from core.sql_corrections import apply_department_scope
from core.sql_validator import validate_sql


class DepartmentScopeSecurityTests(unittest.TestCase):
    """Security-critical coverage for the department-scope injection that
    replaced chat_helpers.force_department_scope's hand-rolled paren-depth
    string scanner. These are the tests that mattered most for this
    refactor — a leak here means one department's HOD can see another
    department's students/faculty."""

    def test_predicate_lands_before_group_order_limit_regardless_of_order(self):
        sql = (
            "SELECT d.department_name, COUNT(*) FROM students s "
            "JOIN departments d ON s.department_id = d.department_id "
            "GROUP BY d.department_name ORDER BY d.department_name LIMIT 10"
        )
        new_sql, changed = apply_department_scope(sql, "DCS")
        self.assertTrue(changed)
        # Predicate must be in the WHERE clause, not spliced in after LIMIT.
        where_pos = new_sql.upper().index("WHERE")
        group_pos = new_sql.upper().index("GROUP BY")
        limit_pos = new_sql.upper().index("LIMIT")
        exists_pos = new_sql.index("EXISTS")
        self.assertTrue(where_pos < exists_pos < group_pos < limit_pos)

    def test_ands_into_existing_where(self):
        sql = "SELECT s.name FROM students s WHERE s.status = 'Active'"
        new_sql, changed = apply_department_scope(sql, "DCS")
        self.assertTrue(changed)
        self.assertIn("s.status = 'Active' AND EXISTS", new_sql)

    def test_union_query_scopes_referencing_branch_only(self):
        sql = "SELECT s.name FROM students s UNION SELECT f.full_name FROM faculty f"
        new_sql, changed = apply_department_scope(sql, "DCS")
        self.assertTrue(changed)
        branches = new_sql.split("UNION")
        self.assertIn("EXISTS", branches[0])
        self.assertNotIn("s.department_id", branches[1])

    def test_department_code_is_escaped(self):
        sql = "SELECT s.name FROM students s"
        new_sql, changed = apply_department_scope(sql, "DC'S")
        self.assertTrue(changed)
        self.assertIn("DC''S", new_sql)

    def test_central_admin_path_skips_injection_at_validator_level(self):
        # is_central_admin=True must never trigger the "missing department
        # scope" error in the first place — apply_department_scope is only
        # ever called by central_agent.py when that error fires for a
        # non-admin user. Confirm the validator itself agrees admins are exempt.
        sql = "SELECT s.name FROM students s"
        result = validate_sql(sql, department_code=None, is_central_admin=True)
        self.assertTrue(result.is_valid)

    def test_non_admin_missing_scope_is_flagged(self):
        sql = "SELECT s.name FROM students s"
        result = validate_sql(sql, department_code="DCS", is_central_admin=False)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("department scope" in e.lower() for e in result.errors))
        # After injection, the same query must validate cleanly.
        fixed_sql, changed = apply_department_scope(sql, "DCS")
        self.assertTrue(changed)
        fixed_result = validate_sql(fixed_sql, department_code="DCS", is_central_admin=False)
        self.assertTrue(fixed_result.is_valid)


if __name__ == "__main__":
    unittest.main()
