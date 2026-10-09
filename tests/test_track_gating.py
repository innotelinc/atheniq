"""Unit tests for scripts/track-gating.py."""
import json
import unittest

from _loader import ROOT, load

gating = load("track-gating.py")


def catalog(courses):
    return {"version": 1, "tracks": [
        {"id": "sample", "title": "Sample", "summary": "s",
         "status": "active", "courses": courses},
    ]}


class Plan(unittest.TestCase):
    def test_sequential_requires_the_previous_course(self):
        doc = catalog(["course-v1:O+A+1", "course-v1:O+B+1", "course-v1:O+C+1"])
        plan = gating.prerequisite_plan(doc)
        self.assertEqual([i["prerequisites"] for i in plan],
                         [[], ["course-v1:O+A+1"], ["course-v1:O+B+1"]])

    def test_cumulative_requires_every_earlier_course(self):
        doc = catalog(["course-v1:O+A+1", "course-v1:O+B+1", "course-v1:O+C+1"])
        plan = gating.prerequisite_plan(doc, cumulative=True)
        self.assertEqual(plan[-1]["prerequisites"],
                         ["course-v1:O+A+1", "course-v1:O+B+1"])

    def test_track_filter_selects_one_track(self):
        doc = {"version": 1, "tracks": [
            {"id": "one", "courses": ["course-v1:O+A+1"]},
            {"id": "two", "courses": ["course-v1:O+B+1"]},
        ]}
        plan = gating.prerequisite_plan(doc, track_id="two")
        self.assertEqual([i["track"] for i in plan], ["two"])

    def test_validate_flags_duplicates_and_bad_keys(self):
        doc = catalog(["course-v1:O+A+1", "course-v1:O+A+1", "TEST101"])
        plan = gating.prerequisite_plan(doc)
        errors = gating.validate_plan(doc, plan)
        self.assertTrue(any("appears twice" in e for e in errors))
        self.assertTrue(any("course-v1:" in e for e in errors))


class ShippedCatalog(unittest.TestCase):
    def test_catalog_yields_a_clean_nonempty_plan(self):
        doc = json.loads((ROOT / "config" / "workforce-tracks.json").read_text())
        plan = gating.prerequisite_plan(doc)
        self.assertTrue(plan)
        self.assertEqual(gating.validate_plan(doc, plan), [])

    def test_it_support_is_fully_sequenced(self):
        doc = json.loads((ROOT / "config" / "workforce-tracks.json").read_text())
        plan = gating.prerequisite_plan(doc, track_id="it-support")
        gated = [i for i in plan if i["prerequisites"]]
        self.assertEqual(len(plan), 4)
        self.assertEqual(len(gated), 3)
        self.assertEqual(gated[0]["prerequisites"], ["course-v1:InnotelLabs+ITSP101+2026_T1"])

    def test_data_foundations_is_fully_sequenced(self):
        doc = json.loads((ROOT / "config" / "workforce-tracks.json").read_text())
        plan = gating.prerequisite_plan(doc, track_id="data-foundations")
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["prerequisites"], [])
        self.assertEqual(plan[1]["prerequisites"],
                         ["course-v1:InnotelLabs+DATA101+2026_T1"])


if __name__ == "__main__":
    unittest.main()
