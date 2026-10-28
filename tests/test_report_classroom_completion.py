"""Unit tests for scripts/report-classroom-completion.py (no socket, no ITS).

The body builder, the derived idempotency key and the door's answers are all
values, so every case here is offline: the transport is a function this file
supplies, and it records the request instead of sending it.
"""
import io
import json
import os
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _loader import load

report = load("report-classroom-completion.py")


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Recorder:
    """A transport that keeps the request and answers whatever it was given."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response
        self.error = error

    def __call__(self, request, timeout=15):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def body(**overrides):
    values = dict(
        classroom="cls-1042", learner="Ada@Acme.Test", lesson="chapter-3",
        course_ref="ITSP101", course_title="IT Support Foundations",
        lesson_title="Accounts and access", score=8, max_score=10,
        completed_at="2026-10-05T09:20:00+00:00",
        checks=[{"checkId": "quiz-1", "label": "Reset the password",
                 "passed": True, "points": 1, "maxPoints": 1}],
        skills=["Account administration"],
    )
    values.update(overrides)
    return report.build_body(**values)


class TheBody(unittest.TestCase):
    def test_the_key_is_derived_from_the_three_ids(self):
        self.assertEqual(
            report.completion_key("cls-1042", "ada@acme.test", "chapter-3"),
            "openmaic:cls-1042:ada@acme.test:chapter-3")

    def test_the_key_is_stable_across_retries(self):
        self.assertEqual(body()["completionId"], body()["completionId"])

    def test_the_key_folds_the_address_case(self):
        self.assertEqual(
            report.completion_key("cls-1", "Ada@Acme.Test", "l-1"),
            report.completion_key("cls-1", "ada@acme.test", "l-1"),
            "a change of case must not make a second record")
        self.assertEqual(body()["completionId"],
                         "openmaic:cls-1042:ada@acme.test:chapter-3")

    def test_an_empty_part_is_refused(self):
        with self.assertRaises(report.CompletionError):
            report.completion_key("cls-1042", "", "chapter-3")

    def test_a_minimal_body_is_the_shape_its_accepts(self):
        built = body()
        self.assertEqual(built["format"], report.FORMAT)
        self.assertEqual(report.FORMAT, "ontrak.classroom.completion/v1")
        self.assertEqual(built["learnerEmail"], "ada@acme.test",
                         "the email is lower-cased like every other door")
        self.assertEqual(built["course"], {"ref": "ITSP101",
                                           "title": "IT Support Foundations"})
        self.assertEqual(built["lesson"]["ref"], "chapter-3")
        self.assertEqual(built["lesson"]["title"], "Accounts and access")
        self.assertEqual(built["score"], 8)
        self.assertEqual(built["maxScore"], 10)
        self.assertEqual(built["completedAt"], "2026-10-05T09:20:00Z",
                         "the instant is normalised so two retries are byte-identical")
        self.assertEqual(built["checks"][0]["checkId"], "quiz-1")
        self.assertEqual(built["skills"], ["Account administration"])

    def test_the_lesson_ref_falls_back_to_the_lesson_id(self):
        built = body(lesson_title=None)
        self.assertEqual(built["lesson"]["ref"], "chapter-3")
        self.assertEqual(built["lesson"]["title"], "chapter-3")

    def test_a_score_above_the_maximum_is_refused(self):
        with self.assertRaises(report.CompletionError):
            body(score=11)

    def test_a_zero_maximum_is_refused(self):
        with self.assertRaises(report.CompletionError):
            body(max_score=0)

    def test_an_email_that_is_not_one_is_refused(self):
        with self.assertRaises(report.CompletionError):
            body(learner="ada")

    def test_a_pass_mark_is_a_percentage(self):
        self.assertEqual(body(pass_score=70)["passScore"], 70)
        with self.assertRaises(report.CompletionError):
            body(pass_score=101)

    def test_a_start_after_the_finish_is_refused(self):
        with self.assertRaises(report.CompletionError):
            body(started_at="2026-10-05T10:00:00Z")

    def test_a_check_cannot_award_more_than_it_offers(self):
        with self.assertRaises(report.CompletionError):
            body(checks=[{"checkId": "a", "label": "A", "passed": True,
                          "points": 2, "maxPoints": 1}])


class TheJsonPath(unittest.TestCase):
    def test_a_complete_body_is_kept(self):
        built = report.body_from_json(body())
        self.assertEqual(built["completionId"], body()["completionId"])
        self.assertEqual(built["checks"][0]["label"], "Reset the password")

    def test_the_wrong_format_is_refused(self):
        with self.assertRaises(report.CompletionError):
            report.body_from_json({**body(), "format": "something/else"})

    def test_a_missing_completion_id_is_refused(self):
        payload = body()
        payload.pop("completionId")
        with self.assertRaises(report.CompletionError):
            report.body_from_json(payload)

    def test_a_non_object_is_refused(self):
        with self.assertRaises(report.CompletionError):
            report.body_from_json([])


class TheDoor(unittest.TestCase):
    def test_a_201_is_a_new_record(self):
        transport = Recorder(FakeResponse(201, {"ok": True, "id": "cmp_1", "created": True}))
        result = report.post(body(), base="https://its.test", token="tok", transport=transport)
        self.assertTrue(result.ok)
        self.assertTrue(result.created)
        self.assertEqual(result.record_id, "cmp_1")
        self.assertEqual(result.status, 201)

    def test_a_200_is_an_already_recorded_completion(self):
        transport = Recorder(FakeResponse(200, {"ok": True, "id": "cmp_1", "created": False}))
        result = report.post(body(), base="https://its.test", token="tok", transport=transport)
        self.assertTrue(result.ok)
        self.assertFalse(result.created)

    def test_the_verify_code_comes_back_with_the_record(self):
        # ITS answers with the stored record's short code on a pass, so the sender
        # can hand the learner something to check at `/verify`.
        transport = Recorder(FakeResponse(
            201, {"ok": True, "id": "cmp_1", "created": True,
                  "code": "ONTRAK-1A2B-3C4D-5E6F"}))
        result = report.post(body(), base="https://its.test", token="tok", transport=transport)
        self.assertEqual(result.code, "ONTRAK-1A2B-3C4D-5E6F")

    def test_the_request_is_the_one_the_door_documents(self):
        transport = Recorder(FakeResponse(201, {"ok": True, "id": "cmp_1", "created": True}))
        report.post(body(), base="https://its.test/", token="tok", transport=transport)
        request = transport.calls[0]
        self.assertEqual(request.full_url, "https://its.test/api/v1/classroom/completions")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer tok")
        sent = json.loads(request.data.decode())
        self.assertEqual(sent["completionId"], body()["completionId"])

    def test_a_422_keeps_the_doors_own_issues(self):
        failure = urllib.error.HTTPError(
            "https://its.test/api/v1/classroom/completions", 422, "Unprocessable",
            {}, io.BytesIO(json.dumps({
                "error": "The classroom completion is not usable.",
                "issues": ["`lesson` names no lesson."],
            }).encode()))
        transport = Recorder(error=failure)
        result = report.post(body(), base="https://its.test", token="tok", transport=transport)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 422)
        self.assertEqual(result.issues, ["`lesson` names no lesson."])
        self.assertIn("not usable", result.error)

    def test_an_unreachable_its_is_an_outcome(self):
        transport = Recorder(error=urllib.error.URLError("connection refused"))
        result = report.post(body(), base="https://its.test", token="tok", transport=transport)
        self.assertFalse(result.ok)
        self.assertIn("unreachable", result.error)


class TheConfiguration(unittest.TestCase):
    def test_no_token_is_refused_and_nothing_is_dialled(self):
        transport = Recorder(FakeResponse(201, {"ok": True, "id": "x", "created": True}))
        result = report.send(body(), base="https://its.test", token="", transport=transport)
        self.assertFalse(result.ok)
        self.assertEqual(transport.calls, [])
        self.assertIn("ONTRAK_API_TOKEN", result.error)

    def test_a_dry_run_needs_no_token_and_dials_nothing(self):
        transport = Recorder(FakeResponse(201, {"ok": True, "id": "x", "created": True}))
        result = report.send(body(), token="", dry_run=True, transport=transport)
        self.assertTrue(result.ok)
        self.assertEqual(transport.calls, [])


class TheCommand(unittest.TestCase):
    def test_dry_run_prints_the_body_and_succeeds(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = report.main([
                "--classroom", "cls-1", "--learner", "ada@acme.test", "--lesson", "l-1",
                "--course-ref", "ITSP101", "--course-title", "IT Support Foundations",
                "--score", "8", "--max-score", "10", "--dry-run",
            ])
        self.assertEqual(code, 0)
        printed = json.loads(out.getvalue())
        self.assertEqual(printed["completionId"], "openmaic:cls-1:ada@acme.test:l-1")
        self.assertIn("dry run", err.getvalue())

    def test_a_missing_flag_is_refused_before_anything_is_built(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = report.main(["--classroom", "cls-1"])
        self.assertEqual(code, 2)
        self.assertIn("missing", err.getvalue())

    def test_a_completion_with_no_token_fails_with_the_reason(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"ONTRAK_API_TOKEN": ""}, clear=False):
            with redirect_stdout(out), redirect_stderr(err):
                code = report.main([
                    "--classroom", "cls-1", "--learner", "ada@acme.test", "--lesson", "l-1",
                    "--course-ref", "ITSP101", "--course-title", "IT Support Foundations",
                    "--score", "8", "--max-score", "10",
                ])
        self.assertEqual(code, 1)
        self.assertIn("ONTRAK_API_TOKEN", err.getvalue())

    def test_a_check_flag_is_parsed(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = report.main([
                "--classroom", "cls-1", "--learner", "ada@acme.test", "--lesson", "l-1",
                "--course-ref", "ITSP101", "--course-title", "IT Support Foundations",
                "--score", "1", "--max-score", "2", "--dry-run",
                "--check", '{"checkId":"q1","label":"Q1","passed":true,"points":1,"maxPoints":1}',
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["checks"][0]["checkId"], "q1")


if __name__ == "__main__":
    unittest.main()
