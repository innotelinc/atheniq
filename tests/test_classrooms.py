"""Unit tests for scripts/check-classrooms.py."""
import json
import os
import tempfile
import unittest

from _loader import ROOT, load

classrooms = load("check-classrooms.py")

# The real OLX outlines — the spec is checked against the shipped courseware.
INDEX = classrooms.olx_index(os.path.join(ROOT, "courses"))


def room(**overrides):
    base = {
        "id": "c1-room",
        "chapter": "ch01_welcome",
        "linked_units": ["unit01_how_it_works"],
        "title": "A classroom",
        "prompt": "Run the classroom.",
        "objectives": ["Describe the role"],
        "activities": [{"type": "slides", "title": "Intro"}],
    }
    base.update(overrides)
    return base


def full_coverage():
    """One classroom per ITSP101 chapter, so the spec raises no coverage warning."""
    outline = INDEX["course-v1:InnotelLabs+ITSP101+2026_T1"]["chapters"]
    return [room(id="room-" + chapter.replace("_", ""), chapter=chapter,
                 linked_units=units[:1])
            for chapter, units in outline.items() if units]


def spec(**overrides):
    base = {
        "version": 1,
        "provider": "openmaic",
        "gateway": "OmniRoute",
        "source_course": "course-v1:InnotelLabs+ITSP101+2026_T1",
        "classrooms": full_coverage(),
    }
    base.update(overrides)
    return base


class Validate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "classrooms.json")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, doc):
        with open(self.path, "w") as fh:
            json.dump(doc, fh)
        return classrooms.validate_spec(self.path, INDEX)

    def test_accepts_a_valid_spec(self):
        errors, warnings, summary = self.check(spec())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(summary["source_course"], "course-v1:InnotelLabs+ITSP101+2026_T1")
        self.assertEqual(summary["classrooms"], 7)

    def test_a_chapter_without_a_classroom_is_only_a_warning(self):
        errors, warnings, _ = self.check(spec(classrooms=[room()]))
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 6, warnings)

    def test_rejects_unparseable_json(self):
        with open(self.path, "w") as fh:
            fh.write("{not json")
        errors, _, _ = classrooms.validate_spec(self.path, INDEX)
        self.assertTrue(any("not valid JSON" in e for e in errors))

    def test_requires_version_and_classrooms(self):
        errors, _, _ = self.check(spec(version="1"))
        self.assertTrue(any("version" in e for e in errors))
        errors, _, _ = self.check(spec(classrooms=[]))
        self.assertTrue(any("classrooms" in e for e in errors))

    def test_rejects_a_source_course_with_no_olx_package(self):
        errors, _, _ = self.check(spec(source_course="course-v1:InnotelLabs+NOPE101+2026_T1"))
        self.assertTrue(any("no OLX package" in e for e in errors))

    def test_rejects_a_non_course_v1_source(self):
        errors, _, _ = self.check(spec(source_course="ITSP101"))
        self.assertTrue(any("course-v1:" in e for e in errors))

    def test_rejects_a_chapter_that_is_not_in_the_outline(self):
        errors, _, _ = self.check(spec(classrooms=[room(chapter="ch99_gone")]))
        self.assertTrue(any("is not a chapter of" in e for e in errors))

    def test_rejects_a_unit_from_another_chapter(self):
        """A unit moved between chapters must be caught, not just a deleted one."""
        errors, _, _ = self.check(spec(classrooms=[room(linked_units=["unit04_hardware_basics"])]))
        self.assertTrue(any("is not a unit of chapter" in e for e in errors))

    def test_rejects_duplicate_ids_and_missing_fields(self):
        errors, _, _ = self.check(spec(classrooms=[
            room(), room(),
        ]))
        self.assertTrue(any("not unique" in e for e in errors))
        errors, _, _ = self.check(spec(classrooms=[room(id="Not A Slug")]))
        self.assertTrue(any(".id must be a lowercase slug" in e for e in errors))
        errors, _, _ = self.check(spec(classrooms=[room(title="")]))
        self.assertTrue(any(".title must be a non-empty string" in e for e in errors))

    def test_rejects_empty_objectives_and_activities(self):
        errors, _, _ = self.check(spec(classrooms=[room(objectives=[])]))
        self.assertTrue(any(".objectives must be a non-empty array" in e for e in errors))
        errors, _, _ = self.check(spec(classrooms=[room(activities=[])]))
        self.assertTrue(any(".activities must be a non-empty array" in e for e in errors))

    def test_warns_when_a_chapter_has_no_classroom(self):
        errors, warnings, _ = self.check(spec(classrooms=[room()]))
        self.assertEqual(errors, [])
        self.assertTrue(any("has no classroom" in w for w in warnings), warnings)

    def test_warns_on_an_unknown_activity_type_and_missing_gateway(self):
        _, warnings, _ = self.check(spec(
            gateway=None,
            classrooms=[room(activities=[{"type": "hologram", "title": "x"}])]))
        self.assertTrue(any("gateway" in w for w in warnings), warnings)
        self.assertTrue(any("not one this repo uses" in w for w in warnings), warnings)

    def test_find_specs_discovers_a_package_spec(self):
        found = classrooms.find_specs(os.path.join(ROOT, "courses"))
        self.assertTrue(found)
        for path in found:
            self.assertTrue(path.endswith(os.path.join("openmaic", "classrooms.json")))


class RepositorySpecs(unittest.TestCase):
    def test_every_shipped_spec_is_valid(self):
        specs = classrooms.find_specs(os.path.join(ROOT, "courses"))
        self.assertTrue(specs, "no classroom specs found")
        for path in specs:
            errors, _, summary = classrooms.validate_spec(path, INDEX)
            self.assertEqual(errors, [], f"{summary['source_course']}: {errors}")

    def test_every_spec_covers_its_whole_course(self):
        """A classroom per chapter — the spec and the OLX must not drift apart."""
        for path in classrooms.find_specs(os.path.join(ROOT, "courses")):
            _, warnings, summary = classrooms.validate_spec(path, INDEX)
            coverage = [w for w in warnings if "has no classroom" in w]
            self.assertEqual(coverage, [], f"{summary['source_course']}: {coverage}")

    def test_specs_resolve_to_authored_courses(self):
        for path in classrooms.find_specs(os.path.join(ROOT, "courses")):
            _, _, summary = classrooms.validate_spec(path, INDEX)
            self.assertIn(summary["source_course"], INDEX)

    def test_the_ai_classroom_course_ships_a_spec(self):
        specs = {os.path.basename(os.path.dirname(os.path.dirname(p)))
                 for p in classrooms.find_specs(os.path.join(ROOT, "courses"))}
        self.assertIn("ai-classroom-facilitation", specs)


if __name__ == "__main__":
    unittest.main()
