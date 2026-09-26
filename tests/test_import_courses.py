"""Unit tests for scripts/import-courses.py."""
import os
import tarfile
import tempfile
import unittest

from _loader import ROOT, load

imp = load("import-courses.py")
olx = load("check-course-olx.py")


class Plan(unittest.TestCase):
    def test_plan_finds_every_shipped_course(self):
        entries = imp.plan(os.path.join(ROOT, "courses"))
        keys = {e["key"] for e in entries}
        for code in ("TEST101", "ITSP101", "ITSP102", "ITSP103", "ITSP104"):
            self.assertIn(f"course-v1:InnotelLabs+{code}+2026_T1", keys)

    def test_plan_entries_carry_a_title_and_slug(self):
        for entry in imp.plan(os.path.join(ROOT, "courses")):
            self.assertTrue(entry["title"], entry)
            self.assertTrue(entry["slug"], entry)
            self.assertTrue(entry["archive"].endswith(".tar.gz"), entry)

    def test_generated_keys_match_the_validator(self):
        for entry in imp.plan(os.path.join(ROOT, "courses")):
            _, _, summary = olx.validate_course(entry["olx_dir"])
            self.assertEqual(entry["key"], summary["course_key"])


class Archive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.entries = {e["slug"]: e for e in imp.plan(os.path.join(ROOT, "courses"))}

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_archive_contains_olx_course_xml(self):
        entry = self.entries["demo-course"]
        path = imp.build_archive(entry, self.tmp.name)
        self.assertTrue(os.path.isfile(path))
        with tarfile.open(path) as tar:
            names = tar.getnames()
        self.assertIn("olx/course.xml", names)
        self.assertIn("olx/chapter/ch01_welcome.xml", names)

    def test_archive_round_trips_through_the_validator(self):
        entry = self.entries["it-support-certification"]
        path = imp.build_archive(entry, self.tmp.name)
        with tarfile.open(path) as tar:
            try:
                tar.extractall(self.tmp.name, filter="data")
            except TypeError:  # Python < 3.12
                tar.extractall(self.tmp.name)
        extracted = os.path.join(self.tmp.name, "olx")
        errors, _, summary = olx.validate_course(extracted)
        self.assertEqual(errors, [])
        self.assertEqual(summary["course_key"], entry["key"])

    def test_import_commands_target_the_cms(self):
        entry = self.entries["capstone"]
        path = os.path.join(self.tmp.name, entry["archive"])
        cmds = imp.import_commands(entry, path)
        self.assertEqual(len(cmds), 2)
        self.assertIn("docker cp", cmds[0])
        self.assertIn("manage.py cms import", cmds[1])
        self.assertIn(entry["key"], cmds[1])
        self.assertIn("tutor_local-cms-1", cmds[1])


if __name__ == "__main__":
    unittest.main()
