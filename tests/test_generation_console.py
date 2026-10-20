"""Unit tests for scripts/generation-console.py.

Two levels, because the console has two kinds of failure. The `Console` class is
driven directly for what it decides — which classrooms exist, what a brief says,
what it refuses, when it writes a classroom back into a spec. The HTTP layer is
driven through a real socket for what it enforces — the SSO headers, the CSRF
guard, the static-file boundary — against a fake OpenMAIC that answers the same
shapes the real one does.
"""
import http.server
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from _loader import ROOT, load

console = load("generation-console.py")

ALLOWED = {"X-Auth-Request-User": "dana", "X-Auth-Request-Email": "dana@innotel.us",
           "X-Auth-Request-Groups": "atheniq-admins,AthenIQ LMS"}
WRONG_GROUP = {"X-Auth-Request-User": "sam", "X-Auth-Request-Email": "sam@innotel.us",
               "X-Auth-Request-Groups": "learners"}

SPEC = {
    "version": 1,
    "provider": "openmaic",
    "source_course": "course-v1:InnotelLabs+DEMO101+2026_T1",
    "locale": "en",
    "defaults": {
        "teacher_persona": "A patient lead.",
        "classmates": ["A sceptic"],
        "interaction": "Hands-on.",
        "assessment": "Three checks.",
    },
    "classrooms": [
        {
            "id": "demo-ch01",
            "chapter": "ch01",
            "linked_units": ["u1"],
            "title": "Read a Queue",
            "prompt": "Work a small ticket queue out loud.",
            "objectives": ["Prioritise by impact"],
            "activities": [{"type": "slides", "title": "The queue"}],
        },
        {
            "id": "demo-ch02",
            "chapter": "ch02",
            "linked_units": ["u2"],
            "title": "Close the Ticket",
            "prompt": "Close the same ticket with a handover note.",
            "objectives": ["Write a handover"],
            "activities": [{"type": "exercise", "title": "Write it"}],
            "classroom_id": "stage-already",
        },
    ],
}


class FakeOpenMAIC(http.server.BaseHTTPRequestHandler):
    """The subset of OpenMAIC's HTTP API the console calls."""

    runs = {}
    submissions = []
    stages = {}

    def log_message(self, *args):
        pass

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    ACTIVE = ("generating", "paused", "outlining")

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/api/health":
            return self._json(200, {"success": True, "version": "test-1",
                                    "capabilities": {"webSearch": True}})
        if url.path == "/api/model-config":
            return self._json(200, {"revision": 7, "slots": [
                {"slot": "llm", "assignment": "omniroute:auto/best-chat"},
                {"slot": "classroom", "assignment": "omniroute:codex/gpt-5.6-luna-medium"},
                {"slot": "tts", "assignment": "omniroute:gtts/default"},
            ]})
        if url.path == "/api/generation-runs":
            if url.query != "active=1":
                return self._json(400, {"success": False, "error": "pass active=1"})
            active = [r for r in type(self).runs.values() if r.get("state") in self.ACTIVE]
            return self._json(200, {"success": True, "runs": active})
        if url.path.startswith("/api/generation-runs/"):
            run = type(self).runs.get(url.path.rsplit("/", 1)[-1])
            return self._json(200, {"run": run}) if run else self._json(404, {"error": "no run"})
        return self._json(404, {"error": "no endpoint"})

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if url.path == "/api/generate-classroom":
            type(self).submissions.append(body.get("requirement"))
            run_id = f"run-{len(type(self).submissions)}"
            type(self).runs[run_id] = {"id": run_id, "state": "generating",
                                       "step": "outline", "seq": 1,
                                       "progress": {"completed": 0, "total": 4},
                                       "createdAt": "2026-10-18T06:00:00Z"}
            return self._json(202, {"jobId": run_id})
        if url.path.endswith("/retry"):
            run_id = url.path.split("/")[3]
            if run_id not in type(self).runs:
                return self._json(404, {"error": "no run"})
            type(self).runs[run_id]["state"] = "generating"
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "no endpoint"})

    def do_DELETE(self):
        run_id = urllib.parse.urlsplit(self.path).path.rsplit("/", 1)[-1]
        run = type(self).runs.get(run_id)
        if not run:
            return self._json(404, {"error": "no run"})
        if run.get("stageId"):
            return self._json(409, {"error": "run has a classroom"})
        del type(self).runs[run_id]
        return self._json(200, {"ok": True})


def start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class GatewayCase(unittest.TestCase):
    """A console + a fake OpenMAIC, both on ephemeral ports."""

    def setUp(self):
        FakeOpenMAIC.runs = {}
        FakeOpenMAIC.submissions = []
        self.gateway = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenMAIC)
        start(self.gateway)

        self.root = tempfile.mkdtemp(prefix="atheniq-console-")
        os.makedirs(os.path.join(self.root, "courses", "demo", "openmaic"))
        self.spec_path = os.path.join(self.root, "courses", "demo", "openmaic", "classrooms.json")
        with open(self.spec_path, "w") as fh:
            json.dump(SPEC, fh, indent=2)
        shutil.copytree(os.path.join(ROOT, "web", "generate"),
                        os.path.join(self.root, "web", "generate"))

        self.config = console.Config(
            base_url=f"http://127.0.0.1:{self.gateway.server_address[1]}",
            bind="127.0.0.1", port=0, root=self.root,
            allowed_groups=("atheniq-admins", "instructors"),
            max_requirement=400, submits_per_hour=20,
        )
        self.server, self.console = console.make_server(self.config)
        start(self.server)
        self.port = self.server.server_address[1]

    def tearDown(self):
        for server in (self.server, self.gateway):
            server.shutdown()
            server.server_close()
        shutil.rmtree(self.root, ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def call(self, path, method="GET", body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                ctype = response.headers.get("Content-Type", "")
                payload = json.loads(raw) if "json" in ctype and raw else raw
                return response.status, payload, dict(response.headers)
        except urllib.error.HTTPError as err:
            try:
                raw = err.read()
                payload = json.loads(raw) if raw else None
                return err.code, payload, dict(err.headers)
            finally:
                err.close()

    def signed(self, extra=None, groups=None):
        headers = dict(ALLOWED)
        if groups is not None:
            headers["X-Auth-Request-Groups"] = groups
        headers.update(extra or {})
        return headers

    def mutate(self, path, method="POST", body=None, headers=None):
        return self.call(path, method=method, body=body or {},
                         headers={"X-Atheniq-Console": "1", **self.signed(headers)})


class DirectConsole(unittest.TestCase):
    """The decisions, without a socket."""

    def setUp(self):
        FakeOpenMAIC.runs = {}
        FakeOpenMAIC.submissions = []
        self.gateway = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenMAIC)
        start(self.gateway)
        self.root = tempfile.mkdtemp(prefix="atheniq-console-")
        os.makedirs(os.path.join(self.root, "courses", "demo", "openmaic"))
        self.spec_path = os.path.join(self.root, "courses", "demo", "openmaic", "classrooms.json")
        with open(self.spec_path, "w") as fh:
            json.dump(SPEC, fh, indent=2)
        self.config = console.Config(
            base_url=f"http://127.0.0.1:{self.gateway.server_address[1]}",
            root=self.root, max_requirement=400, submits_per_hour=20,
        )
        self.console = console.Console(self.config)
        self.dana = console.Identity("dana", "dana@innotel.us", ("atheniq-admins",))

    def tearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()
        shutil.rmtree(self.root, ignore_errors=True)

    def read_spec(self):
        with open(self.spec_path) as fh:
            return json.load(fh)

    def test_courses_report_what_the_specs_record(self):
        courses = self.console.courses()
        self.assertEqual(len(courses), 1)
        course = courses[0]
        self.assertEqual(course["slug"], "demo")
        self.assertEqual((course["generated"], course["total"]), (1, 2))
        first, second = course["classrooms"]
        self.assertFalse(first["generated"])
        self.assertIsNone(first["url"])
        self.assertTrue(second["generated"])
        self.assertEqual(second["classroomId"], "stage-already")
        self.assertTrue(second["url"].endswith("/classroom/stage-already"))

    def test_a_spec_brief_carries_the_whole_design(self):
        source = self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch01"})["source"]
        self.assertEqual(source["kind"], "spec")
        sent = FakeOpenMAIC.submissions[-1]
        for piece in ("Work a small ticket queue", "A patient lead", "A sceptic",
                      "Hands-on", "Three checks", "Prioritise by impact", "slides"):
            self.assertIn(piece, sent)

    def test_a_classroom_that_already_exists_is_not_regenerated(self):
        with self.assertRaises(console.Bad) as caught:
            self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch02"})
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(FakeOpenMAIC.submissions, [])

    def test_unknown_course_or_classroom_is_a_404(self):
        with self.assertRaises(console.Bad) as caught:
            self.console.submit(self.dana, {"course": "nope", "classroom": "demo-ch01"})
        self.assertEqual(caught.exception.status, 404)

    def test_free_form_needs_substance_and_a_length_limit(self):
        with self.assertRaises(console.Bad) as short:
            self.console.submit(self.dana, {"requirement": "teach ai"})
        self.assertEqual(short.exception.status, 400)
        with self.assertRaises(console.Bad) as long:
            self.console.submit(self.dana, {"requirement": "x" * 401})
        self.assertEqual(long.exception.status, 400)
        source = self.console.submit(self.dana, {"title": "Ad hoc", "requirement": "y" * 120})["source"]
        self.assertEqual(source["kind"], "free")
        self.assertEqual(FakeOpenMAIC.submissions[-1], "y" * 120)

    def test_the_hourly_limit_is_per_person(self):
        self.console.config.submits_per_hour = 2
        for _ in range(2):
            self.console.submit(self.dana, {"requirement": "z" * 120})
        with self.assertRaises(console.Bad) as caught:
            self.console.submit(self.dana, {"requirement": "z" * 120})
        self.assertEqual(caught.exception.status, 429)
        other = console.Identity("sam", "sam@innotel.us", ("instructors",))
        self.console.submit(other, {"requirement": "z" * 120})

    def test_recording_writes_the_id_only_when_the_run_finished(self):
        answer = self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch01"})
        run_id = answer["runId"]
        with self.assertRaises(console.Bad) as early:
            self.console.record(run_id)
        self.assertEqual(early.exception.status, 409)

        FakeOpenMAIC.runs[run_id].update({"state": "completed", "step": None,
                                          "stageId": "stage-new"})
        recorded = self.console.record(run_id)
        self.assertEqual(recorded["classroomId"], "stage-new")
        self.assertEqual(self.read_spec()["classrooms"][0]["classroom_id"], "stage-new")
        # Idempotent: recording twice writes the same value, not a second one.
        self.console.record(run_id)
        self.assertEqual(self.read_spec()["classrooms"][0]["classroom_id"], "stage-new")

    def test_recording_refuses_to_overwrite_a_different_classroom(self):
        answer = self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch01"})
        run_id = answer["runId"]
        FakeOpenMAIC.runs[run_id].update({"state": "completed", "stageId": "stage-new"})
        doc = self.read_spec()
        doc["classrooms"][0]["classroom_id"] = "stage-someone-else"
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        with self.assertRaises(console.Bad) as caught:
            self.console.record(run_id)
        self.assertEqual(caught.exception.status, 409)

    def test_a_free_form_run_has_nothing_to_record(self):
        answer = self.console.submit(self.dana, {"requirement": "q" * 120})
        FakeOpenMAIC.runs[answer["runId"]].update({"state": "completed", "stageId": "stage-x"})
        with self.assertRaises(console.Bad) as caught:
            self.console.record(answer["runId"])
        self.assertEqual(caught.exception.status, 400)

    def test_a_finished_classroom_is_recorded_and_leaves_the_list(self):
        """The click is gone: the poll itself writes the spec and drops the run."""
        answer = self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch01"})
        run_id = answer["runId"]
        # A finished run leaves OpenMAIC's active list but is still readable by id.
        FakeOpenMAIC.runs[run_id].update({"state": "completed", "stageId": "stage-new"})
        self.assertEqual([], self.console.runs())
        self.assertEqual(self.read_spec()["classrooms"][0]["classroom_id"], "stage-new")
        # And the page can say what happened rather than just showing an empty list.
        self.assertEqual(self.console.recent_recordings()[-1]["classroomId"], "stage-new")

    def test_a_run_still_generating_stays_listed_with_its_source(self):
        answer = self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch01"})
        runs = self.console.runs()
        self.assertEqual([answer["runId"]], [run["id"] for run in runs])
        self.assertEqual(runs[0]["source"]["title"], "Read a Queue")
        # The spec path stays on this side: the page needs the label, not the file.
        self.assertNotIn("spec", runs[0]["source"])
        self.assertIsNone(self.read_spec()["classrooms"][0].get("classroom_id"))

    def test_a_spec_that_moved_on_keeps_the_run_and_the_reason(self):
        """Overwriting would silently repoint a course's embeds, so it is a person's
        decision and the run stays visible until they make it."""
        answer = self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch01"})
        run_id = answer["runId"]
        FakeOpenMAIC.runs[run_id].update({"state": "completed", "stageId": "stage-new"})
        doc = self.read_spec()
        doc["classrooms"][0]["classroom_id"] = "stage-someone-else"
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        runs = self.console.runs()
        self.assertEqual([run_id], [run["id"] for run in runs])
        self.assertIn("stage-someone-else", runs[0]["recordError"])
        self.assertEqual(self.read_spec()["classrooms"][0]["classroom_id"], "stage-someone-else")

    def test_the_sweeper_records_without_a_page_being_open(self):
        answer = self.console.submit(self.dana, {"course": "demo", "classroom": "demo-ch01"})
        FakeOpenMAIC.runs[answer["runId"]].update({"state": "completed", "stageId": "stage-night"})
        recorded = self.console.sweep()
        self.assertEqual(["stage-night"], [item["classroomId"] for item in recorded])
        self.assertEqual(self.read_spec()["classrooms"][0]["classroom_id"], "stage-night")
        # Recorded once, not on every tick.
        self.assertEqual([], self.console.sweep())

    def test_generate_all_missing_submits_every_classroom_without_one(self):
        result = self.console.submit_missing(self.dana)
        self.assertEqual(1, result["missing"])
        self.assertEqual(["demo-ch01"], [item["classroom"] for item in result["started"]])
        self.assertEqual([], result["skipped"])
        self.assertEqual(1, len(FakeOpenMAIC.submissions))
        self.assertIn("Work a small ticket queue", FakeOpenMAIC.submissions[-1])

    def test_generate_all_missing_does_not_resubmit_what_is_in_flight(self):
        # The spec only learns a classroom's id when the run finishes, so the
        # console's own map is what stops a second run for the same classroom.
        self.console.submit_missing(self.dana)
        again = self.console.submit_missing(self.dana)
        self.assertEqual([], again["started"])
        self.assertEqual("already generating", again["skipped"][0]["reason"])
        self.assertEqual(1, len(FakeOpenMAIC.submissions))

    def test_generate_all_missing_queues_what_the_limit_would_have_dropped(self):
        """A ceiling is not a reason to forget classrooms the operator asked for."""
        doc = self.read_spec()
        doc["classrooms"][1]["classroom_id"] = None
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        self.console.config.submits_per_hour = 1
        result = self.console.submit_missing(self.dana)
        self.assertEqual(2, result["missing"])
        self.assertEqual(1, len(result["started"]))
        self.assertEqual([], result["skipped"])
        self.assertEqual(1, result["queued"])
        self.assertIn("limit", result["blocked"])
        self.assertEqual(1, len(FakeOpenMAIC.submissions))
        self.assertEqual(["demo-ch02"], [item["classroom"] for item in self.console.queued()])

    def test_the_queue_starts_the_next_classroom_when_a_slot_frees(self):
        doc = self.read_spec()
        doc["classrooms"][1]["classroom_id"] = None
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        self.console.config.submits_per_hour = 1
        self.console.submit_missing(self.dana)
        self.assertEqual(1, len(self.console.runs()))
        # The ceiling lifts and the sweeper's next pass is what starts the one
        # that did not fit — the operator does not click again.
        self.console.config.submits_per_hour = 0
        self.console.sweep()
        self.assertEqual([], self.console.queued())
        self.assertEqual(2, len(FakeOpenMAIC.submissions))
        sources = {run["source"]["classroom"] for run in self.console.runs()}
        self.assertEqual({"demo-ch01", "demo-ch02"}, sources)
        # A classroom off the queue is mapped to its spec like any other run, so
        # the sweeper records it without a click.
        for run in self.console.runs():
            self.assertEqual("demo", run["source"]["course"])
        queued_run = [run for run in self.console.runs()
                      if run["source"]["classroom"] == "demo-ch02"][0]
        FakeOpenMAIC.runs[queued_run["id"]].update({"state": "completed",
                                                    "stageId": "stage-ch02"})
        self.assertEqual(["stage-ch02"], [item["classroomId"]
                                          for item in self.console.sweep()])

    def test_the_queue_leaves_a_classroom_the_spec_now_has(self):
        doc = self.read_spec()
        doc["classrooms"][1]["classroom_id"] = None
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        self.console.config.submits_per_hour = 1
        self.console.submit_missing(self.dana)
        doc = self.read_spec()
        doc["classrooms"][1]["classroom_id"] = "stage-elsewhere"
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        self.console.config.submits_per_hour = 0
        answer = self.console.pump()
        self.assertEqual([], self.console.queued())
        self.assertEqual(1, len(FakeOpenMAIC.submissions))
        self.assertIn("already has a classroom", answer["skipped"][0]["reason"])

    def test_the_queue_does_not_resubmit_the_same_classroom(self):
        doc = self.read_spec()
        doc["classrooms"][1]["classroom_id"] = None
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        self.console.config.submits_per_hour = 1
        self.console.submit_missing(self.dana)
        # Clicking the button again must not queue the waiting classroom twice.
        again = self.console.submit_missing(self.dana)
        self.assertEqual(1, again["queued"])
        self.assertEqual(1, len(self.console.queued()))
        self.console.config.submits_per_hour = 0
        self.console.pump()
        self.assertEqual(2, len(FakeOpenMAIC.submissions))

    def test_the_queue_survives_a_restart(self):
        doc = self.read_spec()
        doc["classrooms"][1]["classroom_id"] = None
        with open(self.spec_path, "w") as fh:
            json.dump(doc, fh)
        state_path = os.path.join(self.root, "runs.json")
        config = console.Config(
            base_url=f"http://127.0.0.1:{self.gateway.server_address[1]}",
            root=self.root, submits_per_hour=1, state_path=state_path)
        console.Console(config).submit_missing(self.dana)
        restarted = console.Console(config)
        self.assertEqual(["demo-ch02"], [item["classroom"] for item in restarted.queued()])

    def test_health_reports_only_the_slots_a_person_can_act_on(self):
        health = self.console.health()
        self.assertTrue(health["ok"])
        slots = {slot["slot"]: slot["model"] for slot in health["slots"]}
        self.assertEqual(slots["llm"], "omniroute:auto/best-chat")
        self.assertNotIn("tts", slots)

    def test_an_unreachable_generator_is_a_502_word_not_a_crash(self):
        dead = console.Console(console.Config(base_url="http://127.0.0.1:9", root=self.root))
        with self.assertRaises(console.Unavailable):
            dead.health()


class HttpSurface(GatewayCase):
    """What the socket enforces."""

    def test_no_identity_headers_is_a_401(self):
        status, body, _ = self.call("/api/me")
        self.assertEqual(status, 401)
        self.assertIn("sign in", body["error"])

    def test_the_wrong_group_is_a_403(self):
        status, body, _ = self.call("/api/me", headers=WRONG_GROUP)
        self.assertEqual(status, 403)
        self.assertIn("atheniq-admins", body["error"])

    def test_an_allowed_group_sees_who_it_is(self):
        status, body, _ = self.call("/api/me", headers=self.signed())
        self.assertEqual(status, 200)
        self.assertEqual(body["user"], "dana")
        self.assertTrue(body["mayGenerate"])
        self.assertTrue(body["classroomHost"].startswith("https://"))

    def test_the_forwarded_identity_headers_are_accepted(self):
        """The family oauth2-proxy actually puts on the upstream request.

        `--set-xauthrequest` writes X-Auth-Request-* to the *response*; the
        request that reaches this console carries X-Forwarded-* from
        `--pass-user-headers`. Accepting only the response family is what made
        a signed-in browser see the console's "signed out" state on every API
        call while the proxy logged an authenticated user.
        """
        headers = {"X-Forwarded-User": "dana",
                   "X-Forwarded-Email": "dana@innotel.us",
                   "X-Forwarded-Groups": "atheniq-admins,AthenIQ LMS"}
        status, body, _ = self.call("/api/me", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(body["user"], "dana")
        self.assertTrue(body["mayGenerate"])

    def test_a_forwarded_group_list_is_still_gated(self):
        headers = {"X-Auth-Request-User": "sam",
                   "X-Auth-Request-Email": "sam@innotel.us",
                   "X-Forwarded-Groups": "learners"}
        status, _, _ = self.call("/api/me", headers=headers)
        self.assertEqual(status, 403)

    def test_group_match_ignores_case(self):
        status, _, _ = self.call("/api/me", headers=self.signed(groups="ATHENIQ-ADMINS"))
        self.assertEqual(status, 200)

    def test_mutating_without_the_console_header_is_cross_site(self):
        status, body, _ = self.call("/api/generate", method="POST",
                                    body={"requirement": "r" * 120}, headers=self.signed())
        self.assertEqual(status, 403)
        self.assertIn("cross-site", body["error"])

    def test_mutating_with_a_foreign_origin_is_cross_site(self):
        status, _, _ = self.mutate("/api/generate", body={"requirement": "r" * 120},
                                   headers={"Origin": "https://evil.example"})
        self.assertEqual(status, 403)

    def test_mutating_from_the_same_origin_is_accepted(self):
        origin = f"http://127.0.0.1:{self.port}"
        status, body, _ = self.mutate("/api/generate", body={"requirement": "r" * 120},
                                      headers={"Origin": origin})
        self.assertEqual(status, 202)
        self.assertEqual(body["source"]["kind"], "free")

    def test_a_spec_submission_reaches_the_generator(self):
        status, body, _ = self.mutate("/api/generate",
                                      body={"course": "demo", "classroom": "demo-ch01"})
        self.assertEqual(status, 202)
        self.assertEqual(body["runId"], "run-1")
        self.assertIn("Work a small ticket queue", FakeOpenMAIC.submissions[-1])

    def test_a_bad_submission_is_refused_with_its_reason(self):
        status, body, _ = self.mutate("/api/generate", body={"course": "demo"})
        self.assertEqual(status, 400)
        self.assertIn("both course and classroom", body["error"])

    def test_courses_and_runs_are_served_with_course_metadata(self):
        self.mutate("/api/generate", body={"course": "demo", "classroom": "demo-ch01"})
        status, body, _ = self.call("/api/courses", headers=self.signed())
        self.assertEqual(status, 200)
        self.assertEqual(body["maxRequirement"], 400)
        self.assertEqual(body["courses"][0]["classrooms"][0]["id"], "demo-ch01")

        status, body, _ = self.call("/api/runs", headers=self.signed())
        self.assertEqual(status, 200)
        self.assertEqual(body["runs"][0]["state"], "generating")

    def test_generate_all_missing_is_one_authenticated_post(self):
        status, body, _ = self.mutate("/api/generate-missing")
        self.assertEqual(status, 202)
        self.assertEqual(1, body["missing"])
        self.assertEqual(["demo-ch01"], [item["classroom"] for item in body["started"]])
        # And it is a mutation: without the console header it is a cross-site request.
        status, _, _ = self.call("/api/generate-missing", method="POST", body={},
                                 headers=self.signed())
        self.assertEqual(status, 403)

    def test_a_recorded_classroom_is_reported_and_gone_from_the_runs(self):
        run_id = self.mutate("/api/generate",
                             body={"course": "demo", "classroom": "demo-ch01"})[1]["runId"]
        FakeOpenMAIC.runs[run_id].update({"state": "completed", "stageId": "stage-api"})
        status, body, _ = self.call("/api/runs", headers=self.signed())
        self.assertEqual(status, 200)
        self.assertEqual([], body["runs"])
        self.assertEqual("stage-api", body["recorded"][-1]["classroomId"])
        with open(self.spec_path) as fh:
            self.assertEqual(json.load(fh)["classrooms"][0]["classroom_id"], "stage-api")

    def test_retry_and_discard_reach_the_generator(self):
        run_id = self.mutate("/api/generate", body={"requirement": "d" * 120})[1]["runId"]
        status, _, _ = self.mutate(f"/api/runs/{run_id}/retry")
        self.assertEqual(status, 200)
        status, _, _ = self.mutate(f"/api/runs/{run_id}", method="DELETE")
        self.assertEqual(status, 200)

    def test_discarding_a_run_with_a_classroom_is_kept(self):
        run_id = self.mutate("/api/generate", body={"requirement": "d" * 120})[1]["runId"]
        FakeOpenMAIC.runs[run_id]["stageId"] = "stage-kept"
        status, body, _ = self.mutate(f"/api/runs/{run_id}", method="DELETE")
        self.assertEqual(status, 409)
        self.assertIn("kept", body["error"])

    def test_healthz_answers_without_an_identity(self):
        status, body, _ = self.call("/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_the_page_is_served_with_a_script_free_policy(self):
        status, body, headers = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Course generation", body)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, body, headers = self.call("/console.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])

    def test_a_path_cannot_escape_the_web_root(self):
        for path in ("/../scripts/generation-console.py", "/..%2f..%2fscripts%2fgeneration-console.py",
                     "/%2e%2e/%2e%2e/etc/passwd"):
            status, _, _ = self.call(path)
            self.assertEqual(status, 404, path)


if __name__ == "__main__":
    unittest.main()
