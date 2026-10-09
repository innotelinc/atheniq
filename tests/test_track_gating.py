"""Unit tests for scripts/track-gating.py."""
import contextlib
import io
import json
import types
import unittest
from unittest import mock

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


class ApplySnippet(unittest.TestCase):
    """The snippet must write every layer the LMS keeps prerequisites on.

    The previous version assigned `CourseOverview.prerequisites` — an attribute
    that does not exist on the model and whose nearest real field has a documented
    do-nothing setter, so the run exited 0, printed "prerequisites written", and
    persisted nothing. These pin the three layers that actually hold the gate.
    """

    def test_writes_the_course_block_field_the_lms_reads(self):
        self.assertIn("block.pre_requisite_courses = prerequisites", gating.APPLY_SNIPPET)
        self.assertIn("store.update_item(block, editor.id)", gating.APPLY_SNIPPET)

    def test_registers_the_milestone_that_enforces_the_gate(self):
        self.assertIn("set_prerequisite_courses(key, prerequisites)", gating.APPLY_SNIPPET)

    def test_regenerates_the_derived_course_overview(self):
        self.assertIn("CourseOverview.update_select_courses(", gating.APPLY_SNIPPET)

    def test_refuses_to_run_when_prerequisites_are_switched_off(self):
        self.assertIn("is_prerequisite_courses_enabled()", gating.APPLY_SNIPPET)

    def test_no_longer_writes_the_read_only_overview_property(self):
        self.assertNotIn("overview.prerequisites", gating.APPLY_SNIPPET)
        self.assertNotIn("overview.save()", gating.APPLY_SNIPPET)

    def test_snippet_is_valid_python_once_formatted(self):
        snippet = gating.APPLY_SNIPPET.format(
            plan_json='[{"course": "course-v1:O+A+1", "prerequisites": []}]',
            missing_prefix=gating.MISSING_PREFIX)
        compile(snippet, "apply-snippet", "exec")
        self.assertIn('plan = json.loads(\'[{"course": "course-v1:O+A+1"', snippet)
        self.assertIn('print("missing course: " + course)', snippet)


class Apply(unittest.TestCase):
    def test_dry_run_prints_the_snippet_and_runs_nothing(self):
        printed = io.StringIO()
        with mock.patch.object(gating.subprocess, "run") as run, \
                contextlib.redirect_stdout(printed):
            missing = gating.apply_plan(
                [{"track": "t", "course": "course-v1:O+A+1", "prerequisites": []}],
                "some-cms", dry_run=True)
        run.assert_not_called()
        self.assertEqual(missing, [])
        self.assertIn("course-v1:O+A+1", printed.getvalue())
        self.assertIn("set_prerequisite_courses", printed.getvalue())

    def test_courses_missing_from_the_lms_come_back_to_the_caller(self):
        out = ("prerequisites set for 2 course(s): 2 changed, editor darnel\n"
               "missing course: course-v1:O+Z+1\n"
               "missing course: course-v1:O+Y+1\n")
        fake = types.SimpleNamespace(returncode=0, stdout=out, stderr="")
        with mock.patch.object(gating.subprocess, "run", return_value=fake):
            missing = gating.apply_plan([], "some-cms", dry_run=False)
        self.assertEqual(missing, ["course-v1:O+Z+1", "course-v1:O+Y+1"])

    def test_a_complete_apply_reports_no_missing_courses(self):
        fake = types.SimpleNamespace(
            returncode=0, stdout="prerequisites set for 1 course(s): 1 changed, editor x\n",
            stderr="")
        with mock.patch.object(gating.subprocess, "run", return_value=fake):
            self.assertEqual(gating.apply_plan([], "some-cms", dry_run=False), [])

    def test_a_failed_apply_raises_instead_of_claiming_success(self):
        fake = types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
        with mock.patch.object(gating.subprocess, "run", return_value=fake):
            with self.assertRaises(SystemExit):
                gating.apply_plan([], "some-cms", dry_run=False)

    def test_apply_sends_the_plan_without_the_track_label(self):
        fake = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        plan = [{"track": "it-support", "course": "course-v1:O+A+1", "prerequisites": []}]
        with mock.patch.object(gating.subprocess, "run", return_value=fake) as run:
            gating.apply_plan(plan, "some-cms", dry_run=False)
        snippet = run.call_args[0][0][-1]
        self.assertIn('"course": "course-v1:O+A+1"', snippet)
        self.assertNotIn("it-support", snippet)


class ImportUnit(unittest.TestCase):
    """A (re-)import rebuilds the course block from the OLX, which does not carry
    `pre_requisite_courses` — so importing alone clears the block layer of the gate
    that `--apply` writes. The shipped timer must therefore do both, in order."""

    def test_import_unit_reapplies_the_gating_after_each_import(self):
        unit = (ROOT / "deploy" / "systemd" /
                "atheniq-course-import.service").read_text()
        starts = [line for line in unit.splitlines() if line.startswith("ExecStart=")]
        self.assertEqual(len(starts), 2, starts)
        self.assertIn("import-courses.py --execute", starts[0])
        self.assertIn("track-gating.py --apply", starts[1])


if __name__ == "__main__":
    unittest.main()
