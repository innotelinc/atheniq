"""Unit tests for the LMS publisher.

A programme in the console is a plan; a *course* is what the LMS has. This tool is
the seam between them, so what matters is that the thing it publishes is a real,
valid Open edX course that says what the plan actually says — not invented
courseware — that its key is stable (a second publish is a no-op, not a second
run), and that a failure is reported rather than swallowed.
"""
import json
import os
import tempfile
import unittest

from _loader import load

publisher = load("publish-courses.py")
manager = load("program-manager.py")
validator = load("check-course-olx.py")
console = load("generation-console.py")

SEMESTERS = [{
    "name": "Foundations",
    "courses": [
        {"code": "TST101", "title": "Testing & Things", "credits": 3,
         "description": "A first course about <testing> & evidence.",
         "prerequisites": [], "finalExam": "comprehensive", "classrooms": 2},
    ],
}, {
    "name": "Practice",
    "courses": [
        {"code": "TST102", "title": "Testing Further", "credits": 4,
         "description": "", "prerequisites": ["TST101"],
         "finalExam": "practical", "classrooms": 3},
    ],
}]


class FakeLms:
    """A stand-in for the Tutor stack that remembers what it was told."""

    def __init__(self, keys=(), fail_imports=()):
        self.keys = list(keys)
        self.imports = []
        self.batches = 0
        self.reindexes = 0
        self.enrolled = []
        self.fail_imports = set(fail_imports)
        self.fail_reindex_times = 0
        self.down = False

    def course_ids(self):
        if self.down:
            raise publisher.LmsError("docker: cannot connect")
        return list(self.keys)

    def _import(self, olx_dir, name):
        if self.down:
            raise publisher.LmsError("docker: cannot connect")
        if name in self.fail_imports:
            raise publisher.LmsError(f"import {name} failed")
        self.imports.append((olx_dir, name))
        code, term = name.split("-", 1)
        self.keys.append(f"course-v1:InnotelLabs+{code}+{term}")
        return "imported"

    def import_olx(self, olx_dir, name):
        return self._import(olx_dir, name)

    def import_batch(self, packages):
        self.batches += 1
        return [self._import(olx, name) for olx, name in packages]

    def reindex(self):
        self.reindexes += 1
        if self.fail_reindex_times > 0:
            self.fail_reindex_times -= 1
            raise publisher.LmsError("search service busy")
        return "reindexed"

    def enroll(self, students, keys):
        if self.down:
            raise publisher.LmsError("docker: cannot connect")
        self.enrolled.append((list(students), list(keys)))
        return {"students": [{"student": students[0], "user": "tester", "missing": False,
                              "enrolled": list(keys), "errors": []}]}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="atheniq-publish-")
        os.makedirs(os.path.join(self.root, "programs"))
        self.store = manager.ProgramStore(os.path.join(self.root, "programs"))
        self.program = self.store.create(None, {
            "name": "Test Programme", "credential": "Test Degree",
            "startTerm": "Fall 2026", "semesters": SEMESTERS,
        })
        self.lms = FakeLms()
        self.publisher = publisher.Publisher(
            self.root, work_dir=os.path.join(self.root, "lms"), lms=self.lms,
            clock=lambda: 1_790_000_000)
        self.publisher.retry_delay = 0


class KeyTests(unittest.TestCase):
    def test_term_comes_from_the_programme(self):
        self.assertEqual(publisher.term_for({"startTerm": "Fall 2026"}), "2026_T4")
        self.assertEqual(publisher.term_for({"startTerm": "Spring 2027"}), "2027_T2")
        self.assertEqual(publisher.term_for({"startTerm": "2026_T1"}), "2026_T1")
        self.assertEqual(publisher.term_for({"startTerm": "Winter 2028"}), "2028_T1")

    def test_term_falls_back_to_when_the_programme_was_created(self):
        self.assertEqual(
            publisher.term_for({"createdAt": "2027-05-04T10:00:00Z"}), "2027_T2")

    def test_the_key_is_the_course_not_the_programme(self):
        self.assertEqual(publisher.course_key("acct201", "2026_T4"),
                         "course-v1:InnotelLabs+ACCT201+2026_T4")

    def test_an_existing_run_wins(self):
        keys = publisher.key_index(["course-v1:InnotelLabs+DATA101+2026_T1",
                                    "course-v1:InnotelLabs+ACCT201+2026_T4",
                                    "course-v1:Other+ACCT201+2099_T1"])
        self.assertEqual(keys["DATA101"], "course-v1:InnotelLabs+DATA101+2026_T1")
        self.assertEqual(keys["ACCT201"], "course-v1:InnotelLabs+ACCT201+2026_T4")


class ShellTests(Fixture):
    def entries(self):
        return self.publisher.entries(self.program, keys={})

    def test_every_shell_is_a_valid_course(self):
        for entry in self.entries():
            with self.subTest(course=entry["code"]):
                olx = publisher.build_shell(
                    entry, os.path.join(self.root, "lms", "shells", entry["slug"]))
                errors, _, summary = validator.validate_course(olx)
                self.assertEqual(errors, [])
                self.assertEqual(summary["course_key"], entry["key"])
                self.assertEqual(summary["title"], f"{entry['code']} — {entry['title']}")

    def test_the_shell_says_what_the_plan_says(self):
        entry = self.entries()[0]
        olx = publisher.build_shell(
            entry, os.path.join(self.root, "lms", "shells", entry["slug"]))
        syllabus = read(os.path.join(olx, "html", "l2_syllabus.html"))
        self.assertIn("3 credits", syllabus)
        self.assertIn("None — this is an entry course.", syllabus)
        self.assertIn("60%", syllabus)  # pass mark
        self.assertIn("Comprehensive final examination", syllabus)
        plan = read(os.path.join(olx, "html", "l3_plan.html"))
        self.assertIn("Classroom module 1", plan)
        self.assertIn("Classroom module 2", plan)
        self.assertNotIn("Classroom module 3", plan)
        welcome = read(os.path.join(olx, "html", "l1_welcome.html"))
        self.assertIn("Testing &amp; Things", welcome)
        self.assertIn("&lt;testing&gt; &amp; evidence", welcome)

    def test_the_prerequisite_and_practical_final_are_published(self):
        entry = self.entries()[1]
        olx = publisher.build_shell(
            entry, os.path.join(self.root, "lms", "shells", entry["slug"]))
        syllabus = read(os.path.join(olx, "html", "l2_syllabus.html"))
        self.assertIn("TST101", syllabus)
        assessment = read(os.path.join(olx, "html", "l4_assessment.html"))
        self.assertIn("Practical examination", assessment)
        self.assertIn("Skill demonstration", assessment)

    def test_the_run_dates_open_before_the_term_and_are_enrollable(self):
        entry = self.entries()[0]
        olx = publisher.build_shell(
            entry, os.path.join(self.root, "lms", "shells", entry["slug"]))
        block = read(os.path.join(olx, "course", f"{entry['term']}.xml"))
        policy = json.loads(read(os.path.join(olx, "policies", entry["term"],
                                              "policy.json")))[f"course/{entry['term']}"]
        self.assertIn('start="2026-10-01T00:00:00Z"', block)
        self.assertIn('enrollment_start="2026-08-02T00:00:00Z"', block)
        self.assertEqual(policy["enrollment_start"], "2026-08-02T00:00:00Z")
        self.assertTrue(policy["certificates"]["certificates"][0]["is_active"])


class PublishTests(Fixture):
    def test_plan_touches_nothing(self):
        answer = self.publisher.publish()
        self.assertEqual(len(answer["planned"]), 2)
        self.assertEqual(answer["published"], [])
        self.assertEqual(self.lms.imports, [])
        self.assertEqual(self.lms.reindexes, 0)

    def test_execute_publishes_each_missing_course_and_reindexes_once(self):
        answer = self.publisher.publish(execute=True)
        self.assertEqual([entry["code"] for entry in answer["published"]], ["TST101", "TST102"])
        self.assertEqual([name for _, name in self.lms.imports],
                         ["TST101-2026_T4", "TST102-2026_T4"])
        self.assertEqual(self.lms.reindexes, 1)
        self.assertTrue(answer["reindexed"])
        record = json.loads(read(os.path.join(self.root, "lms", "published.json")))
        self.assertIn("course-v1:InnotelLabs+TST101+2026_T4", record)

    def test_a_second_run_is_a_no_op(self):
        self.publisher.publish(execute=True)
        again = self.publisher.publish(execute=True)
        self.assertEqual(again["published"], [])
        self.assertEqual(len(again["skipped"]), 2)
        self.assertEqual(len(self.lms.imports), 2)
        self.assertEqual(self.lms.reindexes, 1)

    def test_courses_already_in_the_lms_are_left_alone(self):
        self.lms.keys = ["course-v1:InnotelLabs+TST101+2024_T1"]
        answer = self.publisher.publish(execute=True)
        self.assertEqual([entry["code"] for entry in answer["published"]], ["TST102"])
        self.assertEqual(answer["skipped"][0]["key"],
                         "course-v1:InnotelLabs+TST101+2024_T1")

    def test_one_failed_course_does_not_stop_the_batch(self):
        self.lms.fail_imports = {"TST101-2026_T4"}
        answer = self.publisher.publish(execute=True)
        self.assertEqual([failure["code"] for failure in answer["failed"]], ["TST101"])
        self.assertEqual([entry["code"] for entry in answer["published"]], ["TST102"])
        self.assertEqual(self.lms.reindexes, 1)

    def test_an_unreachable_lms_is_reported_not_raised(self):
        self.lms.down = True
        answer = self.publisher.publish(execute=True)
        self.assertFalse(answer["available"])
        self.assertIn("docker", answer["error"])

    def test_status_counts_what_the_lms_holds(self):
        self.publisher.publish(execute=True)
        status = self.publisher.status(self.program["id"])
        self.assertTrue(status["available"])
        self.assertEqual((status["published"], status["courses"]), (2, 2))
        self.assertEqual(status["keys"]["TST101"], "course-v1:InnotelLabs+TST101+2026_T4")

    def test_courses_are_imported_in_one_batch(self):
        self.publisher.publish(execute=True)
        self.assertEqual(self.lms.batches, 1)
        self.assertEqual(len(self.lms.imports), 2)

    def test_a_batch_failure_falls_back_to_one_course_at_a_time(self):
        self.lms.fail_imports = {"TST101-2026_T4"}
        self.lms.import_batch = lambda packages: (_ for _ in ()).throw(
            publisher.LmsError("batch import failed (1)"))
        answer = self.publisher.publish(execute=True)
        self.assertEqual([entry["code"] for entry in answer["published"]], ["TST102"])
        self.assertEqual([failure["code"] for failure in answer["failed"]], ["TST101"])

    def test_a_reindex_that_fails_once_is_retried(self):
        self.lms.fail_reindex_times = 1
        answer = self.publisher.publish(execute=True)
        self.assertTrue(answer["reindexed"])
        self.assertEqual(self.lms.reindexes, 2)
        self.assertIn("course-v1:InnotelLabs+TST101+2026_T4",
                      json.loads(read(os.path.join(self.root, "lms", "published.json"))))

    def test_a_course_shared_by_two_programmes_is_published_once(self):
        self.store.create(None, {
            "name": "Second Programme", "credential": "Second Degree",
            "semesters": [{"name": "One", "courses": [
                {"code": "TST101", "title": "Testing & Things", "credits": 3,
                 "description": "Same course, second programme.", "prerequisites": [],
                 "finalExam": "comprehensive", "classrooms": 2}]}],
        })
        answer = self.publisher.publish(execute=True)
        self.assertEqual([name for _, name in self.lms.imports],
                         ["TST101-2026_T4", "TST102-2026_T4"])
        self.assertEqual(len(answer["published"]), 2)

    def test_course_filter_publishes_one_course(self):
        answer = self.publisher.publish(codes=["TST102"], execute=True)
        self.assertEqual([entry["code"] for entry in answer["published"]], ["TST102"])


class EnrolTests(Fixture):
    def test_enrol_puts_the_learner_in_every_course_of_the_programme(self):
        self.publisher.publish(execute=True)
        report = self.publisher.enroll(self.program["id"], "tester@example.org")
        self.assertTrue(report["available"])
        students, keys = self.lms.enrolled[0]
        self.assertEqual(students, ["tester@example.org"])
        self.assertEqual(keys, ["course-v1:InnotelLabs+TST101+2026_T4",
                                "course-v1:InnotelLabs+TST102+2026_T4"])

    def test_an_unknown_programme_enrols_nobody(self):
        report = self.publisher.enroll("nope", "tester@example.org")
        self.assertFalse(report["available"])
        self.assertEqual(self.lms.enrolled, [])


class ConsoleTests(Fixture):
    class FakePublisher:
        def __init__(self, inner):
            self.inner = inner
            self.enrolled = []

        def publish(self, program_ids=None, codes=None, execute=False):
            return self.inner.publish(program_ids, codes, execute)

        def status(self, program_id):
            return self.inner.status(program_id)

        def enroll(self, program_id, student):
            self.enrolled.append((program_id, student))
            return {"available": True, "courses": ["course-v1:InnotelLabs+TST101+2026_T4"],
                    "students": [{"student": student, "user": "tester", "missing": False,
                                  "enrolled": ["course-v1:InnotelLabs+TST101+2026_T4"],
                                  "errors": []}]}

    def console(self, publisher=None, publish_courses=False):
        # The console loads program-manager.py as its own module (by path), so its
        # ProgramError is the class its store raises — build the store from there.
        programs = console._load_program_manager().ProgramStore(
            os.path.join(self.root, "programs"))
        config = console.Config(root=self.root, publish_courses=publish_courses)
        return console.Console(config, builder=object(), programs=programs,
                               publisher=publisher)

    def test_program_get_reports_the_lms_state(self):
        fake = self.FakePublisher(self.publisher)
        api = self.console(fake)
        doc = api.program_get(self.program["id"])
        self.assertEqual(doc["lms"]["courses"], 2)
        self.assertEqual(doc["lms"]["published"], 0)

    def test_program_get_without_a_publisher_says_so(self):
        api = self.console()
        doc = api.program_get(self.program["id"])
        self.assertFalse(doc["lms"]["available"])

    def test_publish_runs_in_the_background_and_reports(self):
        fake = self.FakePublisher(self.publisher)
        api = self.console(fake)
        started = api.program_publish(self.program["id"])
        self.assertTrue(started["running"])
        for _ in range(200):
            run = api.program_lms_status(self.program["id"])["run"]
            if run and not run["running"]:
                break
            __import__("time").sleep(0.01)
        self.assertEqual(run["published"], 2)
        self.assertEqual(api.program_lms_status(self.program["id"])["published"], 2)

    def test_publish_is_refused_when_publishing_is_off(self):
        api = self.console()
        with self.assertRaises(console.Bad) as caught:
            api.program_publish(self.program["id"])
        self.assertEqual(caught.exception.status, 503)

    def test_publish_of_an_unknown_programme_is_a_404(self):
        api = self.console(self.FakePublisher(self.publisher))
        with self.assertRaises(console.Bad) as caught:
            api.program_publish("no-such-program")
        self.assertEqual(caught.exception.status, 404)

    def test_creating_a_programme_publishes_it(self):
        fake = self.FakePublisher(self.publisher)
        api = self.console(fake)
        created = api.program_create(None, {"name": "Second", "credential": "Second Degree",
                                            "semesters": SEMESTERS})
        for _ in range(200):
            run = api.program_lms_status(created["id"])["run"]
            if run and not run["running"]:
                break
            __import__("time").sleep(0.01)
        self.assertEqual(run["published"], 2)

    def test_creating_a_programme_without_a_publisher_still_creates_it(self):
        api = self.console()
        created = api.program_create(None, {"name": "Third", "credential": "Third Degree",
                                            "semesters": SEMESTERS})
        self.assertEqual(created["name"], "Third")

    def test_enrolling_a_learner_also_enrols_them_in_the_lms(self):
        fake = self.FakePublisher(self.publisher)
        api = self.console(fake)
        answer = api.program_enroll(self.program["id"], {"student": "tester@example.org"})
        self.assertEqual(fake.enrolled, [(self.program["id"], "tester@example.org")])
        self.assertTrue(answer["lms"]["available"])
        self.assertEqual(answer["student"], "tester@example.org")


if __name__ == "__main__":
    unittest.main()
