"""The course-card photographs: one pool, one mapping, everywhere.

A card photograph is only useful if the same course gets the same picture in
the catalog and in the LMS, and only if the picture is actually there. These
tests pin both halves: the resolver's routing and stability, and the files the
publisher will point a course at.
"""
import json
import unittest

from _loader import ROOT, load

PHOTOS = load("course-photos.py")
PUBLISH = load("publish-courses.py")

MANIFEST = json.loads((ROOT / "config" / "course-photos.json").read_text(encoding="utf-8"))
PHOTO_DIR = ROOT / "contrib" / "atheniq-theme" / "lms" / "static" / "images" / "courses"


class Manifest(unittest.TestCase):
    def test_every_subject_has_keywords_and_photographs(self):
        for name, subject in MANIFEST["subjects"].items():
            self.assertTrue(subject.get("photos"), f"{name} has no photographs")
            self.assertTrue(subject.get("keywords"), f"{name} has no keywords")

    def test_photographs_are_not_duplicated_across_subjects(self):
        seen = {}
        for name, subject in MANIFEST["subjects"].items():
            for photo in subject["photos"]:
                self.assertNotIn(photo, seen, f"{photo} is in {seen.get(photo)} and {name}")
                seen[photo] = name

    def test_the_pool_is_high_resolution_enough_for_a_card(self):
        self.assertEqual(MANIFEST["size"], [1200, 675])
        self.assertEqual(
            len([p for subject in MANIFEST["subjects"].values()
                 for p in subject["photos"]]), 81,
        )


class Resolver(unittest.TestCase):
    def test_a_title_routes_to_its_subject(self):
        cases = {
            ("Nursing Fundamentals", "NUR101"): "health",
            ("Criminal Justice Policy", "CJ401"): "justice",
            ("SQL Essentials", "SQL101"): "data",
            ("Prompt Engineering & AI Productivity", "FAI102"): "ai",
            ("Corporate Finance", "FIN310"): "finance",
            ("College Writing", "ENGL101"): "writing",
        }
        for (title, code), subject in cases.items():
            self.assertEqual(PHOTOS.subject_for(title, code), subject, title)

    def test_an_unknown_title_falls_back_to_the_declared_default(self):
        self.assertEqual(PHOTOS.subject_for("Something Entirely New", "ZZZ999"),
                         MANIFEST["default"])

    def test_the_choice_is_stable(self):
        first = PHOTOS.resolve("FAI101", "Applied AI Foundations for Work")
        second = PHOTOS.resolve("FAI101", "Applied AI Foundations for Work")
        self.assertEqual(first, second)

    def test_the_url_is_the_one_the_lms_serves(self):
        photo = PHOTOS.resolve("DATA101", "Data Foundations")
        self.assertEqual(photo["url"], f"/static/atheniq/images/courses/{photo['file']}")
        self.assertTrue((PHOTO_DIR / photo["file"]).is_file(), photo["file"])

    def test_every_repository_course_resolves_to_an_existing_photograph(self):
        rows = PHOTOS.course_rows()
        self.assertGreaterEqual(len(rows), 10)
        for code, title, photo in rows:
            self.assertTrue((PHOTO_DIR / photo["file"]).is_file(),
                            f"{code} ({title}) -> {photo['file']} is missing")

    def test_every_pooled_photograph_is_present_and_sized(self):
        self.assertEqual(PHOTOS.check(), [])


class Publishing(unittest.TestCase):
    def test_the_publisher_uses_the_same_resolver(self):
        url = PUBLISH.course_image_url("FAI101", "Applied AI Foundations for Work")
        self.assertTrue(url.startswith("/static/atheniq/images/courses/"))

    def test_publishing_applies_the_photographs(self):
        """A card image is part of publishing, not an afterthought."""
        source = (ROOT / "scripts" / "publish-courses.py").read_text(encoding="utf-8")
        self.assertIn("CourseOverview.objects.filter(id=key).update(course_image_url=url, banner_image_url=url)", source)
        self.assertIn("answer[\"images\"] = self.set_images(entries)", source)

    def test_there_is_a_delete_all_for_a_start_from_scratch(self):
        source = (ROOT / "scripts" / "publish-courses.py").read_text(encoding="utf-8")
        self.assertIn("def delete_all_courses", source)
        self.assertIn("def delete_all(", source)
        self.assertIn('"--delete-all"', source)
        self.assertIn("CourseEnrollment.objects.filter(course_id=key).delete()", source)


if __name__ == "__main__":
    unittest.main()
