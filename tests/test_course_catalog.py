"""Unit tests for scripts/build-course-catalog.py."""
import unittest

from _loader import ROOT, load

catalog = load("build-course-catalog.py")


class Model(unittest.TestCase):
    def test_lists_every_track_and_course(self):
        model = catalog.load_model(ROOT)
        self.assertEqual({t["id"] for t in model["tracks"]},
                         {"it-support", "data-foundations", "ai-classroom-facilitator"})
        self.assertEqual(len(model["courses"]), 5)

    def test_courses_carry_structure_and_access(self):
        for course in catalog.load_model(ROOT)["courses"]:
            self.assertGreater(course["chapters"], 0, course)
            self.assertGreater(course["problems"], 0, course)
            self.assertTrue(course["access"], course)
            self.assertTrue(course["valid"], course)

    def test_tracks_reference_resolved_courses(self):
        model = catalog.load_model(ROOT)
        keys = {c["key"] for c in model["courses"]}
        track = next(t for t in model["tracks"] if t["id"] == "it-support")
        for key in track["courses"]:
            self.assertIn(key, keys)


class Page(unittest.TestCase):
    def test_committed_page_matches_the_generator(self):
        committed = (ROOT / "web" / "landing" / "catalog" / "index.html").read_text()
        self.assertEqual(committed, catalog.build(ROOT))

    def test_page_escapes_html_and_links_the_assets(self):
        page = catalog.build(ROOT)
        self.assertIn("&amp;", page)          # "Networking & Systems"
        self.assertIn("assets/favicon.svg", page)
        self.assertIn("IT Support Specialist", page)


if __name__ == "__main__":
    unittest.main()
