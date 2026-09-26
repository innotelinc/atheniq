"""Unit tests for scripts/paid-enrollment.py's pure logic."""
import unittest

from _loader import load

pe = load("paid-enrollment.py")


class EnrollmentSql(unittest.TestCase):
    def test_insert_when_no_row_exists(self):
        sql = pe.enrollment_sql(False, 7, "course-v1:Innotel+TEST101+2026_T1",
                                "verified", True)
        self.assertIn("INSERT INTO student_courseenrollment", sql)
        self.assertIn("VALUES", sql)
        self.assertIn(", 1, ", sql)  # is_active column value
        self.assertIn("'course-v1:Innotel+TEST101+2026_T1'", sql)

    def test_update_when_a_row_exists(self):
        sql = pe.enrollment_sql(True, 7, "course-v1:Innotel+TEST101+2026_T1",
                                "verified", True)
        self.assertIn("UPDATE student_courseenrollment", sql)
        self.assertIn("is_active = 1", sql)
        self.assertNotIn("INSERT", sql)

    def test_revoke_deactivates(self):
        sql = pe.enrollment_sql(True, 7, "course-v1:Innotel+TEST101+2026_T1",
                                "verified", False)
        self.assertIn("is_active = 0", sql)

    def test_identifier_is_escaped(self):
        sql = pe.enrollment_sql(True, 7, "course-v1:O'+C+R", "verified", True)
        self.assertIn("O'\\''", sql)


class Quoting(unittest.TestCase):
    def test_single_quotes_are_escaped(self):
        self.assertEqual(pe.sh_quote("a'b"), "'a'\\''b'")
        self.assertEqual(pe.sh_quote(5), "'5'")


class EntitlementInterpretation(unittest.TestCase):
    def test_true_false_and_unknown(self):
        self.assertIs(pe.entitlement_allows({"entitled": True}), True)
        self.assertIs(pe.entitlement_allows({"entitled": False}), False)
        # Unknown must never be read as permission.
        self.assertIsNone(pe.entitlement_allows({"entitled": None}))
        self.assertIsNone(pe.entitlement_allows({}))
        self.assertIsNone(pe.entitlement_allows(None))


if __name__ == "__main__":
    unittest.main()
