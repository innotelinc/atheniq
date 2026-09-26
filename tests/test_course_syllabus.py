"""Unit tests for scripts/build-course-syllabus.py."""
import unittest

from _loader import ROOT, load

syllabus = load("build-course-syllabus.py")
olx = load("check-course-olx.py")


class Outline(unittest.TestCase):
    def test_every_shipped_course_has_a_page(self):
        pages = syllabus.build_all(ROOT)
        self.assertEqual(len(pages), 5)
        for slug in ("demo-course", "it-support-certification",
                     "networking-systems-support", "security-operations", "capstone"):
            self.assertIn(slug, pages)

    def test_outline_counts_match_the_validator(self):
        for olx_dir in olx.find_courses(str(ROOT / "courses")):
            model = syllabus.load_outline(olx_dir)
            _, _, summary = olx.validate_course(olx_dir)
            self.assertEqual(model["key"], summary["course_key"])
            self.assertEqual(len(model["chapters"]), summary["chapters"])
            subs = [s for c in model["chapters"] for s in c["subsections"]]
            self.assertEqual(len(subs), summary["sequentials"])
            self.assertEqual(sum(s["graded"] for s in subs), summary["graded"])

    def test_grading_and_pass_threshold_are_read(self):
        model = syllabus.load_outline(str(ROOT / "courses" / "it-support-certification" / "olx"))
        self.assertTrue(model["grading"])
        self.assertAlmostEqual(model["pass"], 0.7)

    def test_committed_pages_match_the_generator(self):
        for slug, page in syllabus.build_all(ROOT).items():
            committed = (ROOT / "web" / "landing" / "courses" / slug / "index.html").read_text()
            self.assertEqual(committed, page, slug)


if __name__ == "__main__":
    unittest.main()
