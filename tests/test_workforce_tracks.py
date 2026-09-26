"""Unit tests for scripts/check-workforce-tracks.py."""
import json
import pathlib
import unittest

from _loader import ROOT, load

wft = load("check-workforce-tracks.py")


def track(**overrides):
    base = {
        "id": "sample",
        "title": "Sample Track",
        "summary": "A sample.",
        "status": "draft",
        "courses": ["course-v1:Innotel+TEST101+2026_T1"],
    }
    base.update(overrides)
    return base


class Validate(unittest.TestCase):
    def test_accepts_a_valid_catalog(self):
        errors, warnings = wft.validate({"version": 1, "tracks": [track()]})
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_requires_version_and_tracks(self):
        errors, _ = wft.validate({"tracks": [track()]})
        self.assertTrue(any("version" in e for e in errors))
        errors, _ = wft.validate({"version": 1, "tracks": []})
        self.assertTrue(any("tracks" in e for e in errors))

    def test_rejects_bad_slug_title_and_status(self):
        errors, _ = wft.validate({"version": 1, "tracks": [
            track(id="Not A Slug", title="", status="live"),
        ]})
        joined = " ".join(errors)
        self.assertIn(".id must be a lowercase slug", joined)
        self.assertIn(".title must be a non-empty string", joined)
        self.assertIn(".status must be one of", joined)

    def test_rejects_duplicate_ids(self):
        errors, _ = wft.validate({"version": 1, "tracks": [track(), track()]})
        self.assertTrue(any("not unique" in e for e in errors))

    def test_requires_a_course_v1_key(self):
        errors, _ = wft.validate({"version": 1, "tracks": [track(courses=["TEST101"])]})
        self.assertTrue(any("course-v1:" in e for e in errors))

    def test_warns_when_a_course_is_shared(self):
        errors, warnings = wft.validate({"version": 1, "tracks": [
            track(id="one"), track(id="two"),
        ]})
        self.assertEqual(errors, [])
        self.assertTrue(any("multiple tracks" in w for w in warnings))

    def test_rejects_unknown_credential_type_and_bad_plan(self):
        errors, _ = wft.validate({"version": 1, "tracks": [
            track(credential={"type": "gift-certificate"},
                  entitlement={"plan": "Not A Slug"}),
        ]})
        joined = " ".join(errors)
        self.assertIn("credential.type", joined)
        self.assertIn("entitlement.plan", joined)

    def test_certificate_without_template_is_a_warning(self):
        errors, warnings = wft.validate({"version": 1, "tracks": [
            track(credential={"type": "certificate"}),
        ]})
        self.assertEqual(errors, [])
        self.assertTrue(any("signara_template" in w for w in warnings))

    def test_skills_must_be_strings(self):
        errors, _ = wft.validate({"version": 1, "tracks": [track(skills=["ok", 3])]})
        self.assertTrue(any("skills" in e for e in errors))

    def test_markdown_table_lists_tracks(self):
        table = wft.markdown_table([track(title="Visible Title")])
        self.assertIn("Visible Title", table)
        self.assertIn("| Track |", table)


class RepositoryCatalog(unittest.TestCase):
    def test_shipped_catalog_is_valid(self):
        doc = json.loads((ROOT / "config" / "workforce-tracks.json").read_text())
        errors, _ = wft.validate(doc)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
