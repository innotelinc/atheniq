"""Unit tests for the degree-program layer.

A program is the platform's unit of a real credential, so what matters is not
that a JSON file exists but that the thing it describes is walkable: every
prerequisite taught earlier than the course that needs it, every credit counted
once, every final accounted for, and a credential conferred only when a learner
has actually finished.

`program-catalog.py` is tested as data; `program-manager.py` as the rules over
it; and the console's program methods as the seam a request actually hits.
"""
import os
import tempfile
import unittest

from _loader import load

catalog = load("program-catalog.py")
manager = load("program-manager.py")
console = load("generation-console.py")

STUDENT = "learner@example.org"


class Identity:
    user = "dana"
    email = "dana@innotel.us"
    groups = ("atheniq-admins",)


class CatalogueTests(unittest.TestCase):
    def test_ships_three_complete_programs(self):
        slugs = {template.slug for template in catalog.PROGRAM_TEMPLATES.values()}
        self.assertEqual(slugs, {"criminal-justice", "business-administration", "nursing"})

    def test_every_prerequisite_is_taught_earlier(self):
        for template in catalog.PROGRAM_TEMPLATES.values():
            with self.subTest(program=template.slug):
                self.assertEqual(catalog.prerequisite_errors(template), [])

    def test_declared_credits_are_the_credits_taught(self):
        for template in catalog.PROGRAM_TEMPLATES.values():
            with self.subTest(program=template.slug):
                self.assertEqual(catalog.catalogue_credits(template), template.total_credits)

    def test_every_course_names_a_final_assessment(self):
        for template in catalog.PROGRAM_TEMPLATES.values():
            for semester in template.semesters:
                for course in semester.courses:
                    with self.subTest(course=course.code):
                        self.assertIn(course.final_exam,
                                      ("comprehensive", "practical", "project",
                                       "portfolio", "none"))
                        blueprint = manager.final_exam_blueprint(course.as_dict())
                        self.assertTrue(blueprint["label"])
                        self.assertEqual(sum(s["weight"] for s in blueprint["sections"]), 100)

    def test_certificates_only_require_courses_in_the_program(self):
        for template in catalog.PROGRAM_TEMPLATES.values():
            index = template.course_index()
            for certificate in template.certificates:
                with self.subTest(certificate=certificate.slug):
                    self.assertTrue(set(certificate.required_courses) <= set(index))
                    self.assertLessEqual(certificate.after_semester, len(template.semesters))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="atheniq-programs-")
        self.store = manager.ProgramStore(self.dir)

    def test_create_from_template(self):
        doc = self.store.create(Identity(), {"template": "criminal-justice",
                                             "startTerm": "Fall 2026"})
        self.assertEqual(doc["credential"], "Bachelor of Science in Criminal Justice")
        self.assertEqual(doc["startTerm"], "Fall 2026")
        self.assertEqual(len(doc["plan"]["semesters"]), 8)
        self.assertEqual(doc["plan"]["earnedCredits"], 120)
        self.assertEqual(len(doc["plan"]["finals"]), 39)

    def test_unknown_template_is_a_400(self):
        with self.assertRaises(manager.ProgramError) as caught:
            self.store.create(Identity(), {"template": "astrophysics"})
        self.assertEqual(caught.exception.status, 400)

    def test_custom_program_may_not_need_a_later_course(self):
        with self.assertRaises(manager.ProgramError) as caught:
            self.store.create(Identity(), {
                "name": "Broken", "credential": "Certificate", "level": "certificate",
                "semesters": [{"name": "One", "courses": [
                    {"code": "A101", "title": "First", "credits": 3,
                     "prerequisites": ["A102"]},
                    {"code": "A102", "title": "Second", "credits": 3},
                ]}],
            })
        self.assertEqual(caught.exception.status, 400)
        self.assertIn("A102", str(caught.exception))

    def test_custom_program_round_trips(self):
        doc = self.store.create(Identity(), {
            "name": "Forensics Certificate", "credential": "Certificate in Forensics",
            "credentialKind": "certificate", "level": "certificate", "totalCredits": 6,
            "semesters": [
                {"name": "Term 1", "courses": [
                    {"code": "F101", "title": "Scene", "credits": 3}]},
                {"name": "Term 2", "courses": [
                    {"code": "F102", "title": "Lab", "credits": 3,
                     "prerequisites": ["F101"]}]},
            ],
        })
        reread = self.store.get(doc["id"])
        self.assertEqual([s["number"] for s in reread["plan"]["semesters"]], [1, 2])
        self.assertEqual(self.store.list_programs()[0]["courses"], 2)

    def test_delete_moves_the_program_out_of_the_catalogue(self):
        """The console's Delete is an archive: the file survives, the listing does not.

        Conferrals and enrolments may point at a program that has been retired;
        erasing the file would take the only record of them.
        """
        doc = self.store.create(Identity(), {"template": "nursing"})
        self.assertEqual([doc["id"]], [p["id"] for p in self.store.list_programs()])
        answer = self.store.archive(doc["id"])
        self.assertTrue(answer["ok"])
        self.assertIn(".archive", answer["archived"])
        self.assertTrue(os.path.isfile(answer["archived"]))
        self.assertEqual([], self.store.list_programs())
        with self.assertRaises(manager.ProgramError) as caught:
            self.store.get(doc["id"])
        self.assertEqual(caught.exception.status, 404)

    def test_store_write_failure_is_a_500_not_a_dropped_request(self):
        blocker = os.path.join(tempfile.mkdtemp(), "not-a-dir")
        open(blocker, "w").close()
        store = manager.ProgramStore(os.path.join(blocker, "programs"))
        self.assertFalse(store.writable()["ok"])
        with self.assertRaises(manager.ProgramError) as caught:
            store.create(Identity(), {"template": "nursing"})
        self.assertEqual(caught.exception.status, 500)

    def test_prerequisites_gate_completion(self):
        doc = self.store.create(Identity(), {"template": "criminal-justice"})
        self.store.enroll(doc["id"], STUDENT)
        with self.assertRaises(manager.ProgramError) as caught:
            self.store.record_completion(doc["id"], STUDENT, "CJ450", 96, True)
        self.assertEqual(caught.exception.status, 409)

    def test_progress_unlocks_the_next_course(self):
        doc = self.store.create(Identity(), {"template": "criminal-justice"})
        self.store.enroll(doc["id"], STUDENT)
        state = self.store.progress(doc["id"], STUDENT)
        self.assertNotIn("CJ102", {c["code"] for c in state["available"]})
        self.store.record_completion(doc["id"], STUDENT, "CJ101", 91, True)
        state = self.store.progress(doc["id"], STUDENT)
        self.assertIn("CJ102", {c["code"] for c in state["available"]})
        self.assertEqual(state["creditsEarned"], 3)

    def test_a_failing_grade_does_not_earn_credits(self):
        doc = self.store.create(Identity(), {"template": "criminal-justice"})
        self.store.enroll(doc["id"], STUDENT)
        self.store.record_completion(doc["id"], STUDENT, "CJ101", 42, False)
        state = self.store.progress(doc["id"], STUDENT)
        self.assertEqual(state["creditsEarned"], 0)
        self.assertEqual([c["code"] for c in state["failed"]], ["CJ101"])

    def test_full_program_confers_a_degree_and_its_certificate(self):
        doc = self.store.create(Identity(), {"template": "business-administration"})
        self.store.enroll(doc["id"], STUDENT)
        for semester in doc["semesters"]:
            for course in semester["courses"]:
                self.store.record_completion(doc["id"], STUDENT, course["code"], 90, True)
        state = self.store.progress(doc["id"], STUDENT)
        self.assertTrue(state["eligible"], state["blockers"])
        self.assertEqual(state["creditsEarned"], 120)
        self.assertEqual([c["slug"] for c in state["certificates"]], ["business-foundations"])

        answer = self.store.confer(doc["id"], STUDENT)
        self.assertEqual(answer["conferred"]["credential"], "Bachelor of Business Administration")
        self.assertTrue(answer["conferred"]["finalExaminationsPassed"])
        self.assertTrue(self.store.confer(doc["id"], STUDENT)["alreadyConferred"])

    def test_conferral_is_refused_while_requirements_are_open(self):
        doc = self.store.create(Identity(), {"template": "nursing"})
        self.store.enroll(doc["id"], STUDENT)
        with self.assertRaises(manager.ProgramError) as caught:
            self.store.confer(doc["id"], STUDENT)
        self.assertEqual(caught.exception.status, 409)

    def test_generation_plan_is_ordered_and_submittable(self):
        doc = self.store.create(Identity(), {"template": "criminal-justice"})
        plan = self.store.generate_plan(self.store._read(doc["id"]), semester=1)
        self.assertEqual([item["course"]["code"] for item in plan],
                         ["CJ101", "ENGL101", "MATH110", "PSYC101", "CJ110"])
        for item in plan:
            self.assertGreaterEqual(len(item["brief"]), 80)
            self.assertLessEqual(len(item["brief"]), 6000)

    def test_generate_records_runs_and_refuses_to_double_submit(self):
        doc = self.store.create(Identity(), {"template": "nursing"})
        submitted = []

        def submit(brief):
            submitted.append(brief)
            return f"run-{len(submitted)}"

        first = self.store.generate(doc["id"], {"semester": 1}, submit)
        self.assertEqual(len(first["started"]), 4)
        self.assertEqual(len(submitted), 4)
        second = self.store.generate(doc["id"], {"semester": 1}, submit)
        self.assertEqual(second["started"], [])
        self.assertTrue(all("already" in item["reason"] for item in second["skipped"]))

    def test_sync_records_finished_classrooms(self):
        doc = self.store.create(Identity(), {"template": "nursing"})
        runs = iter(["run-1", "run-2"])
        self.store.generate(doc["id"], {"semester": 1}, lambda brief: next(runs))

        def status(run_id):
            return {"state": "completed", "classroomId": f"stage-{run_id}"}

        answer = self.store.sync(doc["id"], status)
        self.assertEqual(len(answer["recorded"]), 2)
        reread = self.store.get(doc["id"])
        sem1 = reread["plan"]["semesters"][0]
        self.assertEqual([c["classroomIds"] for c in sem1["courses"]],
                         [["stage-run-1"], ["stage-run-2"], [], []])
        self.assertEqual(self.store.sync(doc["id"], status)["recorded"], [])


class ConsoleProgramTests(unittest.TestCase):
    """The seam a request hits: console methods over the store, no socket."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="atheniq-console-")
        self.console = console.Console(console.Config(root=self.dir), builder=object())

    def test_program_lifecycle_through_the_console(self):
        listing = self.console.programs_list()
        self.assertEqual(len(listing["templates"]), 3)

        doc = self.console.program_create(Identity(), {"template": "business-administration"})
        self.assertEqual(len(self.console.program_get(doc["id"])["plan"]["semesters"]), 8)

        self.console.program_enroll(doc["id"], {"student": STUDENT})
        self.console.program_complete(doc["id"], {
            "student": STUDENT, "course": "BUS101", "score": 88, "finalPassed": True})
        state = self.console.program_progress(doc["id"], STUDENT)
        self.assertEqual(state["creditsEarned"], 3)

        with self.assertRaises(console.Bad) as caught:
            self.console.program_confer(doc["id"], {"student": STUDENT})
        self.assertEqual(caught.exception.status, 409)

    def test_course_materials_load_outside_a_package(self):
        """The console's material generator must not need package-relative imports."""
        out = self.console._generate_course_materials({
            "requirement": "A criminal justice course on evidence and procedure. " * 3,
            "title": "CJ101",
        })
        self.assertEqual(out["syllabus"]["title"], "CJ101")
        self.assertEqual(len(out["quizQuestions"]), 5)

    def test_generation_turns_a_rate_limit_into_a_named_skip(self):
        doc = self.console.program_create(Identity(), {"template": "nursing"})

        def limited(identity, body):
            raise console.Bad(429, "10 classrooms an hour is the limit for one person")

        self.console.submit = limited
        answer = self.console.program_generate(Identity(), doc["id"], {"semester": 1})
        self.assertEqual(answer["started"], [])
        self.assertIn("limit", answer["blocked"])
        self.assertEqual(len(answer["skipped"]), 4)


if __name__ == "__main__":
    unittest.main()
