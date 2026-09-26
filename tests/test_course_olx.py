"""Unit tests for scripts/check-course-olx.py."""
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from _loader import ROOT, load

olx = load("check-course-olx.py")


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)


def build_course(base, run="2026_T1", org="InnotelLabs", course="ITSP101",
                 chapter_child="sequential"):
    """Write a small but structurally valid OLX course into base; return base."""
    write(os.path.join(base, "course.xml"),
          f'<course url_name="{run}" org="{org}" course="{course}"/>')
    write(os.path.join(base, "course", f"{run}.xml"),
          '<course display_name="Test Course">\n<chapter url_name="ch1"/>\n</course>')
    if chapter_child == "sequential":
        child = '<sequential url_name="seq1"/>\n'
    else:
        child = '<vertical url_name="unit1"/>\n'
    write(os.path.join(base, "chapter", "ch1.xml"),
          f'<chapter display_name="Chapter 1">\n{child}</chapter>')
    write(os.path.join(base, "sequential", "seq1.xml"),
          '<sequential display_name="Lesson" graded="true" format="Homework">\n'
          '<vertical url_name="unit1"/>\n</sequential>')
    write(os.path.join(base, "vertical", "unit1.xml"),
          '<vertical display_name="Unit 1">\n'
          '<html url_name="lesson1"/>\n<problem url_name="p1"/>\n</vertical>')
    write(os.path.join(base, "html", "lesson1.xml"),
          '<html filename="lesson1" display_name="Lesson 1"/>')
    write(os.path.join(base, "html", "lesson1.html"), "<p>Hello</p>")
    write(os.path.join(base, "problem", "p1.xml"),
          '<problem display_name="Q"><multiplechoiceresponse>'
          '<choicegroup type="MultipleChoice"><choice correct="true">'
          '<div>yes</div></choice></choicegroup></multiplechoiceresponse></problem>')
    write(os.path.join(base, "policies", run, "grading_policy.json"),
          json.dumps({"GRADE_CUTOFFS": {"Pass": 0.7}}))
    write(os.path.join(base, "static", "card.svg"), "<svg/>")
    write(os.path.join(base, "policies", run, "policy.json"),
          json.dumps({f"course/{run}": {
              "course_image": "card.svg",
              "certificates": {"certificates": [{
                  "course_title": "Test Course", "id": 0, "is_active": True,
                  "signatories": [{"name": "Signer"}]}]}}}))
    return base


class ValidateCourse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = build_course(
            os.path.join(self.tmp.name, "it-support-certification", "olx"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_accepts_a_valid_course(self):
        errors, warnings, summary = olx.validate_course(self.base)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(summary["course_key"], "course-v1:InnotelLabs+ITSP101+2026_T1")
        self.assertEqual(summary["chapters"], 1)
        self.assertEqual(summary["graded"], 1)
        self.assertEqual(summary["html"], 1)
        self.assertEqual(summary["problems"], 1)

    def test_rejects_missing_course_xml(self):
        os.remove(os.path.join(self.base, "course.xml"))
        errors, _, _ = olx.validate_course(self.base)
        self.assertTrue(any("course.xml not found" in e for e in errors))

    def test_rejects_bad_course_key(self):
        write(os.path.join(self.base, "course.xml"), "<course url_name='' org='' course=''/>")
        errors, _, _ = olx.validate_course(self.base)
        self.assertTrue(any("url_name" in e for e in errors))

    def test_rejects_vertical_directly_under_chapter(self):
        base = build_course(os.path.join(self.tmp.name, "bad"), chapter_child="vertical")
        errors, _, _ = olx.validate_course(base)
        self.assertTrue(any("may only contain sequentials" in e for e in errors))

    def test_rejects_missing_referenced_file(self):
        os.remove(os.path.join(self.base, "problem", "p1.xml"))
        errors, _, _ = olx.validate_course(self.base)
        self.assertTrue(any("problem/p1.xml not found" in e for e in errors))

    def test_rejects_wrong_root_tag(self):
        write(os.path.join(self.base, "chapter", "ch1.xml"),
              '<chapter display_name="x"><sequential url_name="seq1"/></chapter>')
        write(os.path.join(self.base, "sequential", "seq1.xml"),
              '<chapter display_name="wrong"/>')
        errors, _, _ = olx.validate_course(self.base)
        self.assertTrue(any("expected <sequential>" in e for e in errors))

    def test_rejects_html_without_content(self):
        os.remove(os.path.join(self.base, "html", "lesson1.html"))
        errors, _, _ = olx.validate_course(self.base)
        self.assertTrue(any("lesson1.html not found" in e for e in errors))

    def test_rejects_problem_without_response(self):
        write(os.path.join(self.base, "problem", "p1.xml"),
              '<problem display_name="empty"></problem>')
        errors, _, _ = olx.validate_course(self.base)
        self.assertTrue(any("no recognized response" in e for e in errors))

    def test_warns_without_graded_work(self):
        write(os.path.join(self.base, "sequential", "seq1.xml"),
              '<sequential display_name="Lesson" graded="false">\n'
              '<vertical url_name="unit1"/></sequential>')
        write(os.path.join(self.base, "vertical", "unit1.xml"),
              '<vertical display_name="Unit 1"><html url_name="lesson1"/></vertical>')
        errors, warnings, summary = olx.validate_course(self.base)
        self.assertEqual(errors, [])
        self.assertEqual(summary["problems"], 0)
        self.assertTrue(any("no graded" in w for w in warnings))

    def test_find_courses_discovers_packages(self):
        found = olx.find_courses(self.tmp.name)
        self.assertEqual(found, [os.path.join(self.tmp.name, "it-support-certification", "olx")])


class RepositoryCourse(unittest.TestCase):
    def test_shipped_courses_are_valid(self):
        courses = olx.find_courses(os.path.join(ROOT, "courses"))
        self.assertTrue(courses, "no OLX course packages found")
        for course in courses:
            errors, _, summary = olx.validate_course(course)
            self.assertEqual(errors, [], f"{summary.get('course_key')}: {errors}")

    def test_it_support_track_lists_the_whole_ladder(self):
        doc = json.loads((ROOT / "config" / "workforce-tracks.json").read_text())
        track = next(t for t in doc["tracks"] if t["id"] == "it-support")
        for code in ("ITSP101", "ITSP102", "ITSP103", "ITSP104"):
            self.assertIn(f"course-v1:InnotelLabs+{code}+2026_T1", track["courses"])

    def test_every_authored_course_has_a_workforce_key_shape(self):
        for course in olx.find_courses(os.path.join(ROOT, "courses")):
            _, _, summary = olx.validate_course(course)
            self.assertRegex(summary["course_key"], r"^course-v1:InnotelLabs\+[A-Z0-9]+\+\d{4}_T1$")

    def test_every_course_declares_a_signatory_and_course_image(self):
        for course in olx.find_courses(os.path.join(ROOT, "courses")):
            run = ET.parse(os.path.join(course, "course.xml")).getroot().get("url_name")
            with open(os.path.join(course, "policies", run, "policy.json")) as fh:
                policy = json.load(fh)
            course_policy = policy[f"course/{run}"]
            image = course_policy["course_image"]
            self.assertTrue(os.path.isfile(os.path.join(course, "static", image)), image)
            certs = course_policy["certificates"]["certificates"]
            self.assertTrue(any(c.get("is_active") for c in certs))
            self.assertTrue(any(c.get("signatories") for c in certs))


if __name__ == "__main__":
    unittest.main()
