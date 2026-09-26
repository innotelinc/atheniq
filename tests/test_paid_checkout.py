"""Unit tests for scripts/paid-course-checkout.py."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from _loader import ROOT, load

checkout = load("paid-course-checkout.py")

CATALOG = {
    "subscribe_url": "https://subscribe.atheniq.innotel.us",
    "courses": {
        "course-v1:O+PLAN+1": {"name": "Plan course", "plan": "premium"},
        "course-v1:O:ONE+OFF": {"name": "One-off course", "amount_cents": 4900},
        "course-v1:O+FREE+1": {"name": "Free course", "plan": None},
    },
}


class CheckoutAction(unittest.TestCase):
    def test_unknown_course(self):
        action, entry = checkout.checkout_action(CATALOG, "course-v1:O+NOPE+1")
        self.assertEqual(action, "unknown")
        self.assertIsNone(entry)

    def test_plan_course_subscribes(self):
        action, _ = checkout.checkout_action(CATALOG, "course-v1:O+PLAN+1")
        self.assertEqual(action, "subscribe")

    def test_priced_course_checkouts(self):
        action, entry = checkout.checkout_action(CATALOG, "course-v1:O:ONE+OFF")
        self.assertEqual(action, "checkout")
        self.assertEqual(entry["amount_cents"], 4900)

    def test_free_course(self):
        action, _ = checkout.checkout_action(CATALOG, "course-v1:O+FREE+1")
        self.assertEqual(action, "free")

    def test_subscribe_url_carries_identity(self):
        _, entry = checkout.checkout_action(CATALOG, "course-v1:O+PLAN+1")
        url = checkout.subscribe_redirect(CATALOG, entry, "course-v1:O+PLAN+1", "learner")
        self.assertTrue(url.startswith("https://subscribe.atheniq.innotel.us?"))
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["plan"], ["premium"])
        self.assertEqual(query["course"], ["course-v1:O+PLAN+1"])
        self.assertEqual(query["user"], ["learner"])


class RepositoryCatalog(unittest.TestCase):
    def test_shipped_price_map_parses(self):
        doc = json.loads((ROOT / "config" / "course-prices.json").read_text())
        self.assertIn("courses", doc)
        for key, entry in doc["courses"].items():
            self.assertTrue(key.startswith("course-v1:"), key)
            self.assertTrue(entry.get("name"), key)


class _MagnateStub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    calls = []

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        _MagnateStub.calls.append(json.loads(self.rfile.read(length) or b"{}"))
        self._send(200, {"url": "https://checkout.stripe.test/session/abc",
                         "id": "cs_test", "item": {}})


class CreateCheckout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _MagnateStub)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_posts_item_and_identity_to_magnate(self):
        _MagnateStub.calls = []
        import os
        os.environ["MAGNATE_API_URL"] = f"http://127.0.0.1:{self.server.server_port}"
        entry = {"name": "One-off course", "amount_cents": 4900}
        url = checkout.create_checkout(entry, "course-v1:O:ONE+OFF", "learner", "x@y.z")
        self.assertEqual(url, "https://checkout.stripe.test/session/abc")
        sent = _MagnateStub.calls[-1]
        self.assertEqual(sent["item"]["unitAmountCents"], 4900)
        self.assertEqual(sent["metadata"]["course_key"], "course-v1:O:ONE+OFF")
        self.assertEqual(sent["metadata"]["username"], "learner")


if __name__ == "__main__":
    unittest.main()
