"""Unit tests for scripts/build-classrooms.py.

The generation run itself is the server's job and needs the classroom host;
what is checked here is the policy around it — which failures are worth another
model, what the model chain looks like — and the record a finished classroom
leaves in the spec.
"""
import json
import os
import tempfile
import unittest

from _loader import load

build = load("build-classrooms.py")


class ModelChain(unittest.TestCase):
    def test_orders_and_deduplicates_the_models(self):
        self.assertEqual(build.model_candidates("b, a ,b,, c"), ["b", "a", "c"])
        self.assertEqual(build.model_candidates("still, reorders, nothing"),
                         ["still", "reorders", "nothing"])

    def test_accepts_semicolons_and_an_empty_flag(self):
        self.assertEqual(build.model_candidates("a;b"), ["a", "b"])
        self.assertEqual(build.model_candidates(None), [])
        self.assertEqual(build.model_candidates("  "), [])

    def test_refs_name_the_gateway_provider_once(self):
        self.assertEqual(build.model_ref("auto/best-chat"), "omniroute:auto/best-chat")
        self.assertEqual(build.model_ref("omniroute:auto/best-chat"),
                         "omniroute:auto/best-chat")

    def test_a_model_id_with_a_colon_keeps_it(self):
        """Some gateway routes carry a suffix (`:batch`), which is not a provider."""
        self.assertEqual(build.model_ref("no-think/openrouter/claude-opus-5:batch"),
                         "omniroute:no-think/openrouter/claude-opus-5:batch")


class CourseSelection(unittest.TestCase):
    def test_no_flags_covers_every_course(self):
        self.assertTrue(build.course_selected("sql-essentials", "SQL101", [], []))

    def test_course_picks_by_slug_or_code(self):
        self.assertTrue(build.course_selected("sql-essentials", "SQL101", ["SQL101"], []))
        self.assertTrue(build.course_selected("sql-essentials", "SQL101", ["sql-essentials"], []))
        self.assertFalse(build.course_selected("sql-essentials", "SQL101", ["FAI101"], []))

    def test_skip_refuses_by_slug_or_code(self):
        self.assertFalse(build.course_selected("demo-course", "TEST101", [], ["TEST101"]))
        self.assertFalse(build.course_selected("demo-course", "TEST101", [], ["demo-course"]))
        self.assertTrue(build.course_selected("sql-essentials", "SQL101", [], ["TEST101"]))

    def test_skip_wins_over_course(self):
        self.assertFalse(build.course_selected("demo-course", "TEST101",
                                              ["TEST101"], ["demo-course"]))

    def test_split_arg_drops_the_blanks(self):
        self.assertEqual(build.split_arg("a, ,b, "), ["a", "b"])
        self.assertEqual(build.split_arg(None), [])


class CapacityFailures(unittest.TestCase):
    def test_reads_the_gateways_own_words_for_a_spent_route(self):
        for message in (
            "All codex accounts reached configured quota threshold (reset after 59m)",
            "Model 'auto' out of credits (per-model billing)",
            "Request exceeded queue budget maxWaitMs=30000ms for gemini/gemini-2.5-flash",
            "Provider gemini-web circuit breaker is open",
            "No active credentials for provider: gemini.",
            "all targets were skipped by pre-dispatch filters",
        ):
            self.assertTrue(build.looks_like_capacity_failure(message), message)

    def test_a_malformed_request_is_not_a_capacity_failure(self):
        for message in (
            "requiredModelRefusal: no model configured for slot course.content.slide",
            "run completed without a stage id",
            "",
            None,
        ):
            self.assertFalse(build.looks_like_capacity_failure(message), message)


class PausedRun(unittest.TestCase):
    def test_reports_the_step_and_the_gateways_message(self):
        run = build.RunPaused("scene:1:content", "AI_APICallError: [502]: queue budget")
        self.assertEqual(run.step, "scene:1:content")
        self.assertIn("queue budget", run.error)
        self.assertIn("scene:1:content", str(run))
        self.assertTrue(run.capacity)

    def test_a_pause_without_an_error_still_reads_as_a_pause(self):
        run = build.RunPaused(None, None)
        self.assertIn("no error reported", str(run))
        self.assertFalse(run.capacity)


class PlanIndexes(unittest.TestCase):
    """A classroom's index is its place in the spec, not its place in the queue."""

    def test_a_spec_with_a_gap_still_points_each_classroom_at_its_own_entry(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        slug = "demo-course"
        os.makedirs(os.path.join(tmp.name, slug, "openmaic"))
        path = os.path.join(tmp.name, slug, "openmaic", "classrooms.json")
        doc = {
            "version": 1,
            "source_course": "course-v1:InnotelLabs+TEST101+2026_T1",
            "classrooms": [
                {"id": "ch01", "chapter": "ch01_welcome", "classroom_id": "stage-keep-me"},
                {"id": "ch02", "chapter": "ch02_media"},
                {"id": "ch03", "chapter": "ch03_problems"},
            ],
        }
        build.write_spec(path, doc)

        plan, invalid = build.plan_entries(tmp.name)
        self.assertEqual(invalid, [])
        self.assertEqual([p["index"] for p in plan], [0, 1, 2])
        self.assertEqual([p["generated"] for p in plan], [True, False, False])

        pending = [p for p in plan if not p["generated"]]
        items = [(p["slug"], p["spec"], p["index"], p["classroom"], p["doc"], "http://om")
                 for p in pending]
        self.assertEqual([item[2] for item in items], [1, 2])

    def test_the_plan_reads_courses_from_the_directory_it_is_given(self):
        plan, _ = build.plan_entries(str(build.COURSES_DIR))
        self.assertTrue(plan)
        by_slug = {p["slug"] for p in plan}
        self.assertIn("ai-foundations-for-work", by_slug)


class FinishedClassroom(unittest.TestCase):
    """What a completed run writes back, and whether `--check`-style lint still passes."""

    def test_the_id_and_the_model_are_recorded_and_nothing_else_moves(self):
        classrooms = load("check-classrooms.py")
        index = classrooms.olx_index(os.path.join(str(build.REPO), "courses"))
        key = "course-v1:InnotelLabs+ITSP101+2026_T1"
        chapters = [(chapter, units) for chapter, units in index[key]["chapters"].items()
                    if units][:2]
        self.assertEqual(len(chapters), 2, chapters)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "classrooms.json")
        doc = {
            "version": 1,
            "source_course": key,
            "classrooms": [
                {"id": chapter.replace("_", "-"), "chapter": chapter, "title": "A chapter",
                 "prompt": "Run it.", "objectives": ["Describe the role"],
                 "activities": [{"type": "slides", "title": "Intro"}],
                 "linked_units": units[:1]}
                for chapter, units in chapters
            ],
        }
        build.write_spec(path, doc)

        class Stub:
            def __init__(self, base_url):
                pass

        real = build.OpenMAIC, build.submit_once, build.wait_for_run
        build.OpenMAIC = Stub
        build.submit_once = lambda client, requirement, **kw: "run-1"
        build.wait_for_run = lambda client, run_id, **kw: "stage-finished"
        try:
            item = ("it-support-certification", path, 1, doc["classrooms"][1], doc, "http://om")
            out = build.generate_one(item, model="auto/best-coding")
        finally:
            build.OpenMAIC, build.submit_once, build.wait_for_run = real

        self.assertEqual(out[2], "stage-finished")
        self.assertIsNone(out[3])
        written = json.load(open(path))
        self.assertEqual(written["classrooms"][1]["classroom_id"], "stage-finished")
        self.assertEqual(written["classrooms"][1]["model"], "omniroute:auto/best-coding")
        self.assertNotIn("classroom_id", written["classrooms"][0])
        # The extra field must not turn the spec invalid.
        errors, _, _ = classrooms.validate_spec(path, index)
        self.assertEqual(errors, [])


class DiscardedPause(unittest.TestCase):
    """A paused run must not hold the owner's run slot while a model is retried."""

    def test_the_paused_run_is_discarded_and_the_classroom_reported_paused(self):
        calls = {}

        class Stub:
            def __init__(self, base_url):
                pass

            def discard(self, run_id):
                calls["discarded"] = run_id
                return 200, {}

        real = build.OpenMAIC, build.submit_once, build.wait_for_run
        build.OpenMAIC = Stub
        build.submit_once = lambda client, requirement, **kw: "run-1"

        def paused(client, run_id, **kw):
            raise build.RunPaused("scene:1:content", "quota", run_id)

        build.wait_for_run = paused
        try:
            out = build.generate_one(("slug", "/spec", 0, {"chapter": "c1"}, {},
                                      "http://om"))
        finally:
            build.OpenMAIC, build.submit_once, build.wait_for_run = real
        self.assertEqual(calls["discarded"], "run-1")
        self.assertIsNone(out[2])
        self.assertTrue(out[4])
        self.assertIn("quota", out[3])


class Campaign(unittest.TestCase):
    """The classroom loop: fall back one model at a time, then stop."""

    def setUp(self):
        self.attempts = []

    def item(self, slug):
        return (slug, f"/spec/{slug}.json", 0, {"chapter": slug}, {}, "http://om")

    def run_campaign(self, items, candidates, results):
        """Drive run_campaign with a scripted generate_one and a stub client."""
        script = list(results)
        real_generate, real_client, real_publish = (
            build.generate_one, build.OpenMAIC, build.publish_one)

        class Stub:
            def __init__(self, base_url):
                pass

            def set_models(self, model):
                return build.model_ref(model)

        def fake_generate(item, model=None, max_resumes=0, run_timeout=5400):
            self.attempts.append((item[0], model))
            path, index, stage_id, error, paused = script.pop(0)
            return item[1], 0, stage_id, error, paused

        build.generate_one = fake_generate
        build.OpenMAIC = Stub
        build.publish_one = lambda path, args: None
        try:
            args = type("Args", (), {"publish": False, "max_resumes": 0,
                                     "run_timeout": 10, "base_url": "http://om"})
            return build.run_campaign([self.item(s) for s in items], candidates, args)
        finally:
            build.generate_one, build.OpenMAIC, build.publish_one = (
                real_generate, real_client, real_publish)

    def test_a_paused_classroom_is_retried_on_the_next_model(self):
        failures = self.run_campaign(
            ["c1"], ["spent", "working"],
            [(None, None, None, "paused on scene:1:content", True),
             (None, None, "stage-1", None, False)])
        self.assertEqual(failures, [])
        self.assertEqual(self.attempts, [("c1", "spent"), ("c1", "working")])

    def test_an_exhausted_chain_stops_instead_of_burning_the_batch(self):
        failures = self.run_campaign(
            ["c1", "c2"], ["spent", "also-spent"],
            [(None, None, None, "paused", True),
             (None, None, None, "paused", True)])
        self.assertEqual(self.attempts, [("c1", "spent"), ("c1", "also-spent")])
        self.assertEqual(len(failures), 2, failures)
        self.assertIn("not attempted", failures[1])

    def test_a_model_that_works_is_reused(self):
        failures = self.run_campaign(
            ["c1", "c2"], ["spent", "working"],
            [(None, None, None, "paused", True),
             (None, None, "stage-1", None, False),
             (None, None, "stage-2", None, False)])
        self.assertEqual(failures, [])
        self.assertEqual(self.attempts,
                         [("c1", "spent"), ("c1", "working"), ("c2", "working")])

    def test_a_failure_that_is_not_a_pause_does_not_move_the_model(self):
        failures = self.run_campaign(
            ["c1"], ["only"],
            [(None, None, None, "c1: bad spec", False)])
        self.assertEqual(self.attempts, [("c1", "only")])
        self.assertEqual(failures, ["c1: bad spec"])


if __name__ == "__main__":
    unittest.main()
