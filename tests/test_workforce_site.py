"""Unit tests for scripts/build-workforce-site.py and its program catalog.

The workforce page is the public face of a funded program, so the tests hold it
to the two things that matter legally and pedagogically: every course it lists
is a real OLX package, and the funding terms it prints are the ones the
administrator published — not a paraphrase a later edit could inflate.
"""
import html
import json
import re
import unittest

from _loader import ROOT, load

site = load("build-workforce-site.py")


def page():
    return site.render(site.load_model(ROOT))


class ProgramCatalog(unittest.TestCase):
    def setUp(self):
        self.model = site.load_model(ROOT)
        self.program = self.model["programs"][0]

    def test_fast_ai_is_a_workforce_program_under_the_institute(self):
        self.assertEqual(self.program["id"], "fast-ai")
        self.assertEqual(self.model["site"]["institute"], "AthenIQ Institute")
        self.assertEqual(self.model["site"]["host"], "workforce.atheniq.online")

    def test_the_program_lists_the_six_course_ladder(self):
        self.assertEqual([c["key"] for c in self.program["_courses"]], [
            f"course-v1:InnotelLabs+FAI{n}+2026_T4" for n in range(101, 107)])
        for course in self.program["_courses"]:
            self.assertTrue(course["chapters"], course["key"])
            self.assertTrue(course["blurb"])

    def test_a_named_course_that_is_not_in_the_repo_is_refused(self):
        """The page cannot advertise a course the LMS would not have."""
        broken = json.loads((ROOT / "config" / "workforce-programs.json").read_text())
        broken["programs"][0]["courses"].append("course-v1:InnotelLabs+FAI999+2026_T4")
        with self.assertRaises(SystemExit):
            site.load_model(ROOT, config=broken)

    def test_the_track_and_the_program_agree_on_the_courses(self):
        tracks = json.loads((ROOT / "config" / "workforce-tracks.json").read_text())
        track = next(t for t in tracks["tracks"] if t["id"] == self.program["track"])
        self.assertEqual(track["courses"], self.program["courses"])

    def test_the_funding_terms_are_the_published_ones(self):
        terms = " ".join(self.program["funding"]["terms"])
        self.assertIn("$300 per instructional hour", terms)
        self.assertIn("$3,000 per person per course", terms)
        self.assertIn("Workforce Investment Trust Fund", self.program["funding"]["source"])
        self.assertIn("Commonwealth Corporation", self.program["funding"]["administrator"])

    def test_timeline_names_the_rfq_and_the_training_window(self):
        timeline = " ".join(self.program["timeline"])
        self.assertIn("November 6, 2026", timeline)
        self.assertIn("February 1, 2027", timeline)
        self.assertIn("June 30, 2028", timeline)


class PageTests(unittest.TestCase):
    def test_the_committed_page_matches_the_generator(self):
        committed = (ROOT / "web" / "workforce" / "index.html").read_text()
        self.assertEqual(committed, page())

    def test_every_course_is_on_the_page_with_its_modules(self):
        text = page()
        model = site.load_model(ROOT)
        for course in model["programs"][0]["_courses"]:
            self.assertIn(html.escape(course["title"]), text)
            for chapter in course["chapters"]:
                self.assertIn(html.escape(chapter["title"]), text)

    def test_the_page_says_who_pays_and_what_it_costs(self):
        text = page()
        self.assertIn("No cost to an eligible employer", text)
        self.assertIn("Workforce Investment Trust Fund", text)
        self.assertIn("Commonwealth Corporation", text)

    def test_the_page_sends_a_learner_to_the_lms(self):
        text = page()
        self.assertIn("https://atheniq.courses/catalog/", text)
        self.assertIn("https://atheniq.courses/login", text)
        self.assertIn("mailto:workforce@atheniq.institute", text)

    def test_the_theme_is_mounted_not_copied(self):
        """One canonical Unity theme, served to both sites."""
        text = page()
        self.assertIn('href="/assets/unity-theme.css"', text)
        self.assertIn('src="/assets/atheniq-mark.svg"', text)
        for asset in ("unity-theme.css", "atheniq-mark.svg"):
            self.assertTrue((ROOT / "web" / "landing" / "assets" / asset).is_file())

    def test_no_local_path_or_second_host_leaks(self):
        text = page()
        self.assertNotIn("/root/", text)
        self.assertNotIn("learn.innotel.us", text)
        self.assertNotIn("apps.atheniq.courses", text)

    def test_the_page_is_valid_looking_html(self):
        text = page()
        self.assertTrue(text.startswith("<!doctype html>"))
        self.assertEqual(text.count("<html"), 1)
        self.assertIsNotNone(re.search(r"</html>\s*$", text))
