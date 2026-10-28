"""One app, two views: the learner sees the catalog, staff see it and the queue.

The two front ends disagreed — the console listed only the built course specs, so
the courses that live inside a program plan were missing, and the learner portal
was a second design. These tests pin the one page that replaces them: the catalog
is whole, the learner view carries nothing about a person, and the generation
actions answer only an allowed identity.
"""
import http.server
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from _loader import ROOT


def load_portal():
    import importlib.util
    path = ROOT / "scripts" / "atheniq-portal.py"
    name = "atheniq_portal_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PORTAL = load_portal()

PROGRAMS = {
    "programs": [
        {"id": "nursing-1", "name": "Nursing", "credential": "Associate of Science in Nursing",
         "credentialKind": "degree", "semesters": 2, "courses": 2, "generated": 1,
         "enrolled": 3},
    ],
    "templates": [],
}

PROGRAM_DETAIL = {
    "id": "nursing-1",
    "name": "Nursing",
    "startTerm": "Spring 2027",
    "plan": {"semesters": [
        {"name": "Semester 1", "courses": [{"code": "NUR101", "title": "Foundations"},
                                           {"code": "DEMO101", "title": "Demo Course"}]},
        {"name": "Semester 2", "courses": [{"code": "NUR110", "title": "Assessment"}]},
    ]},
}

COURSES = {
    "maxRequirement": 400,
    "courses": [
        {"slug": "demo", "course": "course-v1:InnotelLabs+DEMO101+2026_T1",
         "code": "DEMO101", "title": "Demo Course", "locale": "en",
         "classrooms": [{"id": "a", "generated": True}], "generated": 1, "total": 1},
        {"slug": None, "course": "NUR101", "code": "NUR101", "title": "Foundations",
         "locale": "", "classrooms": [], "generated": 0, "total": 0, "planned": True,
         "program": {"id": "nursing-1", "name": "Nursing"}},
    ],
}

RUNS = {"runs": [{"id": "run-1", "state": "paused", "step": "scene:7:narration",
                  "error": {"message": "no TTS"}}],
        "queued": [], "recorded": []}


class FakeConsole(http.server.BaseHTTPRequestHandler):
    """The console's read API, in memory, with the two shapes the portal uses."""

    seen_paths = []

    def log_message(self, *args):
        return

    def do_GET(self):
        FakeConsole.seen_paths.append(self.path)
        if self.path == "/api/programs":
            body = json.dumps(PROGRAMS).encode()
        elif self.path == "/api/programs/nursing-1":
            body = json.dumps(PROGRAM_DETAIL).encode()
        elif self.path == "/api/courses":
            body = json.dumps(COURSES).encode()
        elif self.path == "/api/runs":
            body = json.dumps(RUNS).encode()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class CatalogCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.console = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeConsole)
        threading.Thread(target=cls.console.serve_forever, daemon=True).start()
        cls.root = tempfile.mkdtemp(prefix="atheniq-portal-")
        os.makedirs(os.path.join(cls.root, "web", "portal"))
        for name in ("index.html", "portal.css", "portal.js"):
            shutil.copy(ROOT / "web" / "portal" / name,
                        os.path.join(cls.root, "web", "portal", name))
        cls.config = PORTAL.Config(
            root=cls.root, bind="127.0.0.1", port=0, view="both",
            console_url=f"http://127.0.0.1:{cls.console.server_address[1]}",
            admin_groups=("atheniq-admins",),
            lms_url="https://atheniq.courses", classroom_url="https://classroom.innotel.us")

    @classmethod
    def tearDownClass(cls):
        cls.console.shutdown()
        cls.console.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_every_course_the_catalog_carries_is_projected_once(self):
        payload = PORTAL.catalog(self.config)
        codes = [row["code"] for row in payload["courses"]]
        self.assertEqual(sorted(codes), ["DEMO101", "NUR101"])
        by_code = {row["code"]: row for row in payload["courses"]}
        # A built course knows its program from the plan that teaches it, and its
        # LMS run is linkable.
        self.assertEqual(by_code["DEMO101"]["program"], "Nursing")
        self.assertEqual(by_code["DEMO101"]["url"],
                         "https://atheniq.courses/courses/course-v1:InnotelLabs+DEMO101+2026_T1/about")
        # A planned one is still a course, and says so rather than pretending to
        # be an empty built one.
        self.assertTrue(by_code["NUR101"]["planned"])
        self.assertEqual(by_code["NUR101"]["program"], "Nursing")
        self.assertEqual(by_code["NUR101"]["url"], "")

    def test_the_program_carries_what_a_learner_asks_it(self):
        card = PORTAL.catalog(self.config)["programs"][0]
        self.assertEqual(card["name"], "Nursing")
        self.assertEqual(card["startTerm"], "Spring 2027")
        self.assertEqual((card["semesters"], card["courses"], card["generated"]), (2, 2, 1))
        # Counts are what a learner sees; who is enrolled is not.
        self.assertNotIn("enrollments", card)
        self.assertNotIn("createdBy", card)

    def test_the_queue_is_shaped_for_the_page(self):
        queue = PORTAL.runs(self.config, [("X-Auth-Request-Email", "staff@innotel.us")])
        self.assertEqual(queue["runs"][0]["error"], "no TTS")
        self.assertEqual(queue["runs"][0]["state"], "paused")


class ViewsCase(unittest.TestCase):
    """What each identity may see, over a real socket."""

    @classmethod
    def setUpClass(cls):
        cls.console = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeConsole)
        threading.Thread(target=cls.console.serve_forever, daemon=True).start()
        cls.root = tempfile.mkdtemp(prefix="atheniq-portal-views-")
        os.makedirs(os.path.join(cls.root, "web", "portal"))
        os.makedirs(os.path.join(cls.root, "web", "generate"), exist_ok=True)
        for name in ("index.html", "portal.css", "portal.js"):
            shutil.copy(ROOT / "web" / "portal" / name,
                        os.path.join(cls.root, "web", "portal", name))
        shutil.copy(ROOT / "web" / "generate" / "unity-theme.css",
                    os.path.join(cls.root, "web", "generate", "unity-theme.css"))
        config = PORTAL.Config(
            root=cls.root, bind="127.0.0.1", port=0, view="learner",
            console_url=f"http://127.0.0.1:{cls.console.server_address[1]}",
            admin_groups=("atheniq-admins",),
            lms_url="https://atheniq.courses", classroom_url="https://classroom.innotel.us")
        cls.server = PORTAL.make_server(config)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.console.shutdown()
        cls.console.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def call(self, path, headers=None, method="GET", body=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                         method=method, data=body)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def test_an_anonymous_visitor_gets_the_learner_view_and_nothing_else(self):
        status, body, _ = self.call("/api/me")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["admin"])
        status, body, _ = self.call("/api/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(sorted(row["code"] for row in json.loads(body)["courses"]),
                         ["DEMO101", "NUR101"])
        status, _, _ = self.call("/api/admin/runs")
        self.assertEqual(status, 403)

    def test_the_catalog_never_carries_a_person(self):
        status, body, _ = self.call("/api/catalog")
        self.assertEqual(status, 200)
        text = body.decode()
        self.assertNotIn("enrollments", text)
        self.assertNotIn("@innotel.us", text)

    def test_staff_may_read_the_queue(self):
        status, body, _ = self.call("/api/admin/runs",
                                    {"X-Auth-Request-Email": "staff@innotel.us",
                                     "X-Auth-Request-Groups": "atheniq-admins"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["runs"][0]["id"], "run-1")

    def test_a_group_outside_the_list_is_not_staff(self):
        status, _, _ = self.call("/api/admin/runs",
                                 {"X-Auth-Request-Email": "someone@innotel.us",
                                  "X-Auth-Request-Groups": "students"})
        self.assertEqual(status, 403)

    def test_an_action_needs_the_page_header(self):
        status, _, _ = self.call("/api/admin/generate-missing",
                                 {"X-Auth-Request-Email": "staff@innotel.us",
                                  "X-Auth-Request-Groups": "atheniq-admins"},
                                 method="POST", body=b"{}")
        self.assertEqual(status, 403)

    def test_the_page_itself_is_served_with_a_strict_policy(self):
        status, body, headers = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn("Programs and courses", body.decode())
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))

    def test_the_shared_theme_is_not_copied_into_the_portal(self):
        status, body, headers = self.call("/unity-theme.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("Content-Type", ""))
        self.assertGreater(len(body), 1000)
