"""Unit tests for scripts/entitlement-sync.py.

Covers the pure decision table and, with a stub Authentik/Magnate server, the
real HTTP path: group lookup, membership reads, and add/remove calls.
"""
import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from _loader import load

es = load("entitlement-sync.py")


class DecisionTable(unittest.TestCase):
    def test_add_only_when_entitled_and_absent(self):
        self.assertEqual(es.reconciliation_action(False, True), "add")

    def test_remove_only_when_not_entitled_and_present(self):
        self.assertEqual(es.reconciliation_action(True, False), "remove")

    def test_no_change_when_aligned(self):
        self.assertIsNone(es.reconciliation_action(True, True))
        self.assertIsNone(es.reconciliation_action(False, False))

    def test_unknown_entitlement_never_changes_membership(self):
        self.assertIsNone(es.reconciliation_action(False, None))
        self.assertIsNone(es.reconciliation_action(True, None))


LEARNERS = "uuid-learners"
PAID = "uuid-paid"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    groups = {"learners": LEARNERS, "paid_users": PAID}
    users = []
    entitlement = {}
    calls = []

    def log_message(self, *args):  # keep the test output clean
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/api/v3/core/groups/":
            name = qs.get("name", [""])[0]
            uuid = _Handler.groups.get(name)
            results = [{"pk": uuid, "name": name}] if uuid else []
            self._send(200, {"pagination": {"next": None}, "results": results})
        elif parsed.path == "/api/v3/core/users/":
            if "username" in qs:
                results = [u for u in _Handler.users if u["username"] == qs["username"][0]]
            else:
                results = list(_Handler.users)
            self._send(200, {"pagination": {"next": None}, "results": results})
        elif parsed.path == "/api/entitlements":
            user = qs.get("user", [""])[0]
            self._send(200, {"entitled": _Handler.entitlement.get(user), "reason": "ok"})
        else:
            self._send(404, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        _Handler.calls.append((self.path, json.loads(raw or b"{}")))
        self._send(200, {})


class ReconcileOverHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        _Handler.calls = []
        _Handler.entitlement = {
            "paid-up": True,
            "expired": False,
            "stays": True,
            "unknown": None,
            "inactive": True,
        }
        _Handler.users = [
            {"pk": 1, "username": "paid-up", "is_active": True, "groups": [LEARNERS]},
            {"pk": 2, "username": "expired", "is_active": True, "groups": [LEARNERS, PAID]},
            {"pk": 3, "username": "stays", "is_active": True, "groups": [LEARNERS, PAID]},
            {"pk": 4, "username": "unknown", "is_active": True, "groups": [LEARNERS, PAID]},
            {"pk": 5, "username": "inactive", "is_active": False, "groups": [LEARNERS]},
        ]
        self.auth = es.Authentik(self.base, "test-token")
        self.mag = es.Magnate(self.base, "", "premium")

    def test_group_lookup_and_membership(self):
        self.assertEqual(self.auth.group_uuid("learners"), LEARNERS)
        self.assertEqual(self.auth.group_uuid("paid_users"), PAID)

    def test_reconcile_adds_removes_and_ignores(self):
        users = [u for u in _Handler.users
                 if LEARNERS in (u.get("groups") or [])]
        with contextlib.redirect_stdout(io.StringIO()):
            added, removed, unchanged, unknown = es.reconcile(
                self.auth, self.mag, LEARNERS, PAID, users, dry_run=False)

        self.assertEqual((added, removed, unchanged, unknown), (1, 1, 2, 1))
        endpoints = [path for path, _ in _Handler.calls]
        self.assertIn(f"/api/v3/core/groups/{PAID}/add_user/", endpoints)
        self.assertIn(f"/api/v3/core/groups/{PAID}/remove_user/", endpoints)
        # The add targets the newly entitled learner, the remove the expired one.
        by_path = dict(_Handler.calls)
        self.assertEqual(by_path[f"/api/v3/core/groups/{PAID}/add_user/"]["pk"], 1)
        self.assertEqual(by_path[f"/api/v3/core/groups/{PAID}/remove_user/"]["pk"], 2)

    def test_dry_run_makes_no_writes(self):
        users = [u for u in _Handler.users if LEARNERS in (u.get("groups") or [])]
        with contextlib.redirect_stdout(io.StringIO()):
            added, removed, unchanged, unknown = es.reconcile(
                self.auth, self.mag, LEARNERS, PAID, users, dry_run=True)
        self.assertEqual((added, removed), (1, 1))
        self.assertEqual(_Handler.calls, [])

    def test_inactive_users_are_skipped(self):
        users = [u for u in _Handler.users if u["username"] == "inactive"]
        with contextlib.redirect_stdout(io.StringIO()):
            added, removed, unchanged, unknown = es.reconcile(
                self.auth, self.mag, LEARNERS, PAID, users, dry_run=False)
        self.assertEqual((added, removed, unchanged, unknown), (0, 0, 0, 0))
        self.assertEqual(_Handler.calls, [])


if __name__ == "__main__":
    unittest.main()
