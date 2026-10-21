"""Unit tests for the LMS publisher.

A program in the console is a plan; a *course* is what the LMS has. This tool is
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


LESSONS = [{
    "id": "scene_1", "title": "What a firm is",
    "description": "Firms combine inputs into something a customer pays for.",
    "key_points": ["Inputs", "Value", "Customers"],
    "classroomId": "stage-test1",
    "questions": [
        {"prompt": "What does a firm do?", "kind": "single",
         "solution": "It combines inputs into value.",
         "options": [
             {"value": "A", "label": "Combines inputs into value", "correct": True},
             {"value": "B", "label": "Prints money", "correct": False},
         ]},
        {"prompt": "Which of these are inputs? Select all that apply.", "kind": "multiple",
         "solution": "Labour and capital are inputs; weather is not.",
         "options": [
             {"value": "A", "label": "Labour", "correct": True},
             {"value": "B", "label": "Capital", "correct": True},
             {"value": "C", "label": "Weather", "correct": False},
         ]},
    ],
}, {
    "id": "scene_2", "title": "Why margins matter",
    "description": "Revenue minus cost is what pays for the next year.",
    "key_points": ["Revenue", "Cost"], "classroomId": "stage-test1",
    "questions": [],
}]


class FakeLessons:
    """A classroom outline and its quizzes, without OpenMAIC behind it."""

    def __init__(self, lessons=None, fail=None):
        self.calls = []
        self._lessons = lessons if lessons is not None else LESSONS
        self.fail = fail

    def lessons(self, stage_id):
        self.calls.append(stage_id)
        if self.fail:
            raise publisher.LmsError(self.fail)
        return [dict(lesson) for lesson in self._lessons]


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

    def grades(self, students, keys):
        if self.down:
            raise publisher.LmsError("docker: cannot connect")
        rows = [{"student": student, "user": "tester", "missing": False,
                 "courses": [{"course": key, "percent": 82.5 if key.endswith("TST101+2026_T4") else None,
                              "passed": key.endswith("TST101+2026_T4"), "letter": "B"}
                             for key in keys]}
                for student in students]
        return {"students": rows}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="atheniq-publish-")
        os.makedirs(os.path.join(self.root, "programs"))
        self.store = manager.ProgramStore(os.path.join(self.root, "programs"))
        self.program = self.store.create(None, {
            "name": "Test Program", "credential": "Test Degree",
            "startTerm": "Fall 2026", "semesters": SEMESTERS,
        })
        self.lms = FakeLms()
        self.publisher = publisher.Publisher(
            self.root, work_dir=os.path.join(self.root, "lms"), lms=self.lms,
            clock=lambda: 1_790_000_000)
        self.publisher.retry_delay = 0


class KeyTests(unittest.TestCase):
    def test_term_comes_from_the_program(self):
        self.assertEqual(publisher.term_for({"startTerm": "Fall 2026"}), "2026_T4")
        self.assertEqual(publisher.term_for({"startTerm": "Spring 2027"}), "2027_T2")
        self.assertEqual(publisher.term_for({"startTerm": "2026_T1"}), "2026_T1")
        self.assertEqual(publisher.term_for({"startTerm": "Winter 2028"}), "2028_T1")

    def test_term_falls_back_to_when_the_program_was_created(self):
        self.assertEqual(
            publisher.term_for({"createdAt": "2027-05-04T10:00:00Z"}), "2027_T2")

    def test_the_key_is_the_course_not_the_program(self):
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

    def test_a_course_shared_by_two_programs_is_published_once(self):
        self.store.create(None, {
            "name": "Second Program", "credential": "Second Degree",
            "semesters": [{"name": "One", "courses": [
                {"code": "TST101", "title": "Testing & Things", "credits": 3,
                 "description": "Same course, second program.", "prerequisites": [],
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
    def test_enroll_puts_the_learner_in_every_course_of_the_program(self):
        self.publisher.publish(execute=True)
        report = self.publisher.enroll(self.program["id"], "tester@example.org")
        self.assertTrue(report["available"])
        students, keys = self.lms.enrolled[0]
        self.assertEqual(students, ["tester@example.org"])
        self.assertEqual(keys, ["course-v1:InnotelLabs+TST101+2026_T4",
                                "course-v1:InnotelLabs+TST102+2026_T4"])

    def test_an_unknown_program_enrols_nobody(self):
        report = self.publisher.enroll("nope", "tester@example.org")
        self.assertFalse(report["available"])
        self.assertEqual(self.lms.enrolled, [])


class LessonTests(Fixture):
    def entry(self, lessons=None):
        entry = dict(self.entries()[0])
        entry.update({
            "classroomId": "stage-test1",
            "lessons": lessons if lessons is not None else LESSONS,
            "lessonCount": len(lessons if lessons is not None else LESSONS),
            "questionCount": sum(len(lesson["questions"])
                                 for lesson in (lessons if lessons is not None else LESSONS)),
        })
        return entry

    def entries(self):
        return self.publisher.entries(self.program, keys={})

    def shell(self, entry, name="lesson"):
        return publisher.build_shell(entry, os.path.join(self.root, "lms", "shells", name))

    def test_a_lesson_becomes_a_chapter_with_its_classroom_and_checks(self):
        olx = self.shell(self.entry())
        errors, _, _ = validator.validate_course(olx)
        self.assertEqual(errors, [])
        block = read(os.path.join(olx, "course", f"{self.entry()['term']}.xml"))
        self.assertIn('<chapter url_name="l1"/>', block)
        self.assertIn('<chapter url_name="l2"/>', block)
        chapter = read(os.path.join(olx, "chapter", "l1.xml"))
        self.assertIn("Module 1 — What a firm is", chapter)
        self.assertIn('url_name="l1_study"', chapter)
        self.assertIn('url_name="l1_check"', chapter)
        lesson = read(os.path.join(olx, "html", "l1_html.html"))
        self.assertIn("Firms combine inputs", lesson)
        self.assertIn("https://classroom.innotel.us/classroom/stage-test1", lesson)
        # A lesson with no quiz has no check, rather than an empty one.
        self.assertNotIn('url_name="l2_check"', read(os.path.join(olx, "chapter", "l2.xml")))

    def test_the_final_examination_is_the_generated_questions(self):
        olx = self.shell(self.entry())
        exam = read(os.path.join(olx, "sequential", "s5_exam.xml"))
        self.assertIn('graded="true"', exam)
        self.assertIn('format="Final Exam"', exam)
        self.assertIn('url_name="u5_exam"', exam)
        vertical = read(os.path.join(olx, "vertical", "u5_exam.xml"))
        self.assertIn('url_name="exam_q1"', vertical)
        self.assertIn('url_name="exam_q2"', vertical)
        single = read(os.path.join(olx, "problem", "exam_q1.xml"))
        self.assertIn("<multiplechoiceresponse>", single)
        self.assertIn('<choice correct="true">', single)
        self.assertIn("Combines inputs into value", single)
        multi = read(os.path.join(olx, "problem", "exam_q2.xml"))
        self.assertIn("<checkboxgroup>", multi)
        self.assertIn("<choiceresponse>", multi)
        plan = read(os.path.join(olx, "html", "l3_plan.html"))
        self.assertIn("What a firm is", plan)
        self.assertIn("2 lessons", plan)
        syllabus = read(os.path.join(olx, "html", "l2_syllabus.html"))
        self.assertIn("2 questions", syllabus)

    def test_a_shell_without_lessons_has_no_exam_paper(self):
        entry = dict(self.entries()[0])
        olx = self.shell(entry, "empty")
        self.assertFalse(os.path.exists(os.path.join(olx, "sequential", "s5_exam.xml")))
        self.assertFalse(os.path.exists(os.path.join(olx, "problem")))
        self.assertIn("program office", read(os.path.join(olx, "html", "l2_syllabus.html")))

    def test_quiz_scenes_are_normalized(self):
        scene = {"outlineId": "scene_1", "content": {"type": "quiz", "questions": [
            {"type": "single", "question": "Pick B", "analysis": "Because B.",
             "answer": ["B"], "options": [{"label": "A", "value": "A"},
                                         {"label": "B", "value": "B"}]},
            {"type": "multiple", "question": "Pick both", "answer": ["A", "B"],
             "options": [{"label": "A", "value": "A"}, {"label": "B", "value": "B"},
                         {"label": "C", "value": "C"}]},
            {"type": "single", "question": "No answer", "answer": [],
             "options": [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]},
        ]}}
        questions = publisher._questions(scene)
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["kind"], "single")
        self.assertEqual(questions[1]["kind"], "multiple")
        self.assertEqual([option["correct"] for option in questions[1]["options"]],
                         [True, True, False])

    def test_attach_rewrites_one_course_and_records_its_lessons(self):
        self.publisher.lessons = FakeLessons()
        self.publisher.publish(execute=True)
        answer = self.publisher.attach(self.program["id"], "TST101", "stage-test1")
        self.assertTrue(answer["attached"], answer)
        self.assertEqual((answer["lessons"], answer["questions"]), (2, 2))
        self.assertEqual(self.lms.imports[-1][1], "TST101-2026_T4")
        self.assertTrue(answer["graded"])
        record = json.loads(read(os.path.join(self.root, "lms", "published.json")))
        self.assertEqual(record["course-v1:InnotelLabs+TST101+2026_T4"]["lessons"], 2)
        self.assertEqual(record["course-v1:InnotelLabs+TST101+2026_T4"]["questions"], 2)

    def test_attach_needs_a_classroom_and_a_published_course(self):
        missing = self.publisher.attach(self.program["id"], "TST101")
        self.assertFalse(missing["attached"])
        self.assertIn("no generated classroom", missing["error"])
        unpublished = self.publisher.attach(self.program["id"], "TST101", "stage-test1")
        self.assertFalse(unpublished["attached"])
        self.assertIn("not in the LMS", unpublished["error"])

    def test_attach_reports_an_unreadable_classroom(self):
        self.publisher.lessons = FakeLessons(fail="no such stage")
        self.publisher.publish(execute=True)
        answer = self.publisher.attach(self.program["id"], "TST101", "stage-test1")
        self.assertFalse(answer["attached"])
        self.assertIn("no such stage", answer["error"])


class OpenmaicLessonTests(unittest.TestCase):
    class Reader(publisher.OpenmaicLessons):
        def __init__(self, outline, scenes):
            super().__init__()
            self.outline = outline
            self.scenes = scenes

        def _query(self, sql):
            return self.outline if "document_outlines" in sql else self.scenes

    def test_outline_and_quizzes_become_lessons(self):
        outline = json.dumps({"outlines": [
            {"id": "scene_1", "title": "What is addition?", "description": "Combining",
             "keyPoints": ["Combining groups"]},
            {"id": "scene_2", "title": "Quick check"},
        ]})
        scenes = "\n".join([
            json.dumps({"outlineId": "scene_1", "content": {"type": "slide"}}),
            json.dumps({"outlineId": "scene_2", "content": {"type": "quiz", "questions": [
                {"type": "single", "question": "1 + 1?", "answer": ["B"],
                 "options": [{"label": "1", "value": "A"}, {"label": "2", "value": "B"}]}]}}),
        ])
        lessons = self.Reader(outline, scenes).lessons("stage-abc")
        self.assertEqual([lesson["title"] for lesson in lessons],
                         ["What is addition?", "Quick check"])
        self.assertEqual(lessons[0]["key_points"], ["Combining groups"])
        self.assertEqual(lessons[0]["questions"], [])
        self.assertEqual(len(lessons[1]["questions"]), 1)
        self.assertEqual(lessons[1]["questions"][0]["options"][1]["correct"], True)
        self.assertEqual(lessons[0]["classroomId"], "stage-abc")

    def test_a_stage_id_cannot_smuggle_sql(self):
        with self.assertRaises(publisher.LmsError):
            publisher.OpenmaicLessons._stage("stage-1'; drop table document_scenes; --")


class GradeTests(Fixture):
    def test_grades_are_read_per_learner_and_course(self):
        self.publisher.publish(execute=True)
        self.store.enroll(self.program["id"], "tester@example.org")
        report = self.publisher.grades(self.program["id"])
        self.assertTrue(report["available"])
        self.assertEqual(report["courses"], 2)
        rows = {(row["student"], row["course"]): row for row in report["rows"]}
        self.assertEqual(rows[("tester@example.org", "TST101")]["percent"], 82.5)
        self.assertTrue(rows[("tester@example.org", "TST101")]["passed"])
        self.assertIsNone(rows[("tester@example.org", "TST102")]["percent"])
        self.assertFalse(rows[("tester@example.org", "TST102")]["passed"])

    def test_an_unreachable_lms_is_reported_not_raised(self):
        self.publisher.publish(execute=True)
        self.lms.down = True
        report = self.publisher.grades(self.program["id"], ["tester@example.org"])
        self.assertFalse(report["available"])
        self.assertIn("docker", report["error"])


class ConsoleTests(Fixture):
    class FakePublisher:
        def __init__(self, inner):
            self.inner = inner
            self.enrolled = []
            self.attached = []

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

        def attach(self, program_id, code, classroom_id=None):
            self.attached.append((program_id, code, classroom_id))
            return {"available": True, "attached": True, "key": f"course-v1:InnotelLabs+{code}+2026_T4",
                    "code": code, "classroomId": classroom_id or "stage-x",
                    "lessons": 2, "questions": 3, "graded": True}

        def grades(self, program_id, students=None):
            return {"available": True, "students": ["tester@example.org"], "courses": 2,
                    "rows": [
                        {"student": "tester@example.org", "course": "TST101",
                         "key": "course-v1:InnotelLabs+TST101+2026_T4", "percent": 88.0,
                         "passed": True, "letter": "B", "error": ""},
                        {"student": "tester@example.org", "course": "TST102",
                         "key": "course-v1:InnotelLabs+TST102+2026_T4", "percent": None,
                         "passed": False, "letter": "", "error": ""}]}

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

    def test_publish_of_an_unknown_program_is_a_404(self):
        api = self.console(self.FakePublisher(self.publisher))
        with self.assertRaises(console.Bad) as caught:
            api.program_publish("no-such-program")
        self.assertEqual(caught.exception.status, 404)

    def test_creating_a_program_publishes_it(self):
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

    def test_creating_a_program_without_a_publisher_still_creates_it(self):
        api = self.console()
        created = api.program_create(None, {"name": "Third", "credential": "Third Degree",
                                            "semesters": SEMESTERS})
        self.assertEqual(created["name"], "Third")

    def test_pulling_lms_grades_records_completion_with_its_source(self):
        api = self.console(self.FakePublisher(self.publisher))
        answer = api.program_grades(self.program["id"])
        self.assertEqual([row["course"] for row in answer["recorded"]], ["TST101"])
        self.assertEqual(len(answer["skipped"]), 1)  # TST102 has no grade yet
        progress = api.program_progress(self.program["id"], "tester@example.org")
        completed = {row["code"]: row for row in progress["completed"]}
        self.assertEqual(completed["TST101"]["score"], 88.0)
        self.assertEqual(completed["TST101"]["source"], "lms")
        self.assertNotIn("TST102", completed)

    def test_pulling_grades_needs_the_publisher(self):
        api = self.console()
        with self.assertRaises(console.Bad) as caught:
            api.program_grades(self.program["id"])
        self.assertEqual(caught.exception.status, 503)

    def test_building_lessons_writes_each_recorded_classroom_into_its_course(self):
        path = os.path.join(self.root, "programs", f"{self.program['id']}.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["semesters"][0]["courses"][0]["classroomIds"] = ["stage-test1"]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        fake = self.FakePublisher(self.publisher)
        api = self.console(fake)
        started = api.program_lessons(self.program["id"])
        self.assertTrue(started["running"])
        for _ in range(200):
            run = api.program_get(self.program["id"])["lessonsRun"]
            if run and not run["running"]:
                break
            __import__("time").sleep(0.01)
        self.assertEqual(run["lessons"], 2)
        self.assertEqual(fake.attached,
                         [(self.program["id"], "TST101", "stage-test1")])
        plan = api.program_get(self.program["id"])["plan"]
        course = plan["semesters"][0]["courses"][0]
        self.assertEqual(course["lessons"]["count"], 2)
        self.assertEqual(course["lessons"]["questions"], 3)

    def test_building_lessons_twice_leaves_a_built_course_alone(self):
        path = os.path.join(self.root, "programs", f"{self.program['id']}.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["semesters"][0]["courses"][0]["classroomIds"] = ["stage-test1"]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        fake = self.FakePublisher(self.publisher)
        api = self.console(fake)
        for _ in range(2):
            api.program_lessons(self.program["id"])
            for _ in range(200):
                run = api.program_get(self.program["id"])["lessonsRun"]
                if run and not run["running"]:
                    break
                __import__("time").sleep(0.01)
        self.assertEqual(len(fake.attached), 1)

    def test_enrolling_a_learner_also_enrols_them_in_the_lms(self):
        fake = self.FakePublisher(self.publisher)
        api = self.console(fake)
        answer = api.program_enroll(self.program["id"], {"student": "tester@example.org"})
        self.assertEqual(fake.enrolled, [(self.program["id"], "tester@example.org")])
        self.assertTrue(answer["lms"]["available"])
        self.assertEqual(answer["student"], "tester@example.org")


if __name__ == "__main__":
    unittest.main()
