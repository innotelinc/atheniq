"""Unit tests for scripts/student-portal.py.

The portal is public, so the tests are about the boundary: what it serves, and
what it must never serve. A catalog that leaks a gradebook is worse than no
catalog, and the leak would not be visible in the page — only in the JSON.
"""
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from _loader import ROOT, load

portal = load("student-portal.py")
manager = load("program-manager.py")


class Identity:
    user = "dana"
    email = "dana@innotel.us"


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="atheniq-portal-")
        os.symlink(os.path.join(ROOT, "courses"), os.path.join(cls.root, "courses"))
        os.symlink(os.path.join(ROOT, "web"), os.path.join(cls.root, "web"))
        store = manager.ProgramStore(os.path.join(cls.root, "programs"))
        cls.doc = store.create(Identity(), {"template": "criminal-justice"})
        store.enroll(cls.doc["id"], "learner@example.org")
        store.record_completion(cls.doc["id"], "learner@example.org", "CJ101", 91, True)

        cls.server, cls.catalog = portal.make_server(
            portal.Config(bind="127.0.0.1", port=0, root=cls.root))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_health_is_a_process_check_only(self):
        status, body = get(self.base, "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})

    def test_public_programs_lists_the_running_program(self):
        status, body = get(self.base, "/api/public/programs")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["programs"])
        card = payload["programs"][0]
        self.assertEqual(card["credential"], "Bachelor of Science in Criminal Justice")
        self.assertEqual(card["semesters"], 8)
        self.assertEqual(len(payload["templates"]), 3)

    def test_program_detail_never_carries_learner_data(self):
        status, body = get(self.base, f"/api/public/programs/{self.doc['id']}")
        self.assertEqual(status, 200)
        doc = json.loads(body)
        self.assertNotIn("enrollments", doc)
        self.assertNotIn("createdBy", doc)
        text = body.decode()
        self.assertNotIn("learner@example.org", text)
        self.assertNotIn("\"grades\"", text)
        # ...and the catalog itself is intact.
        self.assertEqual(len(doc["semesters"]), 8)
        self.assertEqual(doc["semesters"][0]["courses"][0]["code"], "CJ101")

    def test_unknown_program_is_a_404(self):
        status, body = get(self.base, "/api/public/programs/no-such-program")
        self.assertEqual(status, 404)
        self.assertIn("no program", json.loads(body)["error"])

    def test_courses_are_listed_with_their_classrooms(self):
        status, body = get(self.base, "/api/public/courses")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["courses"])
        self.assertIn("classroomsLive", payload)

    def test_courses_of_a_new_program_are_listed_before_they_are_built(self):
        """A program carries its curriculum from the moment it is saved.

        Without this, a program created today listed its courses inside the
        program and none of them under Courses — which reads as "the course was
        not created". They are listed as `planned`, pointing at the program.
        """
        status, body = get(self.base, "/api/public/courses")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        planned = [c for c in payload["courses"] if c.get("planned")]
        self.assertTrue(planned, "a program's unbuilt courses should still be listed")
        entry = next(c for c in planned if c["code"] == "CJ101")
        self.assertEqual(entry["program"]["id"], self.doc["id"])
        self.assertEqual((entry["generated"], entry["total"]), (0, 0))
        # One card per course: a code with a spec is the spec, not a second
        # planned entry beside it.
        codes = [c["code"] for c in payload["courses"] if c.get("code")]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(any(c["slug"] for c in payload["courses"]),
                        "built specs still carry their slug")

    def test_portal_page_is_served(self):
        status, body = get(self.base, "/")
        self.assertEqual(status, 200)
        self.assertIn(b"AthenIQ", body)
        self.assertIn(b"Programs and courses", body)

    def test_the_catalog_is_read_only(self):
        request = urllib.request.Request(self.base + "/api/public/programs",
                                         data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(caught.exception.code, 405)

    def test_path_traversal_never_reaches_disk(self):
        status, body = get(self.base, "/../../etc/passwd")
        # The URL is normalized by the client/server before it arrives; either
        # way the answer is the portal, never a file outside web/student.
        self.assertIn(status, (200, 404))
        self.assertNotIn(b"root:x:0:0", body)


if __name__ == "__main__":
    unittest.main()
