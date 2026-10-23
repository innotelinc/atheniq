"""The host-trust checker's verdicts, decided from headers we hand it.

The point of the check is to fail for the right reasons, and every reason it has
— no allow-origin at all, a wildcard, an answer for a different origin, a missing
credentials allowance — is a decision about response headers, not about the
network. So the decisions are tested here with hand-built headers, and the one
thing that has to reach out (the deployed Studio) is not called at all.
"""
import io
import json
import unittest
from contextlib import redirect_stdout

from _loader import load

trust = load("check-host-trust.py")

ORIGIN = "https://atheniq.courses"

GOOD = {
    "access-control-allow-origin": ORIGIN,
    "access-control-allow-credentials": "true",
}


class Origins(unittest.TestCase):
    def test_a_url_reduces_to_its_origin(self):
        self.assertEqual(trust.origin_of("https://atheniq.courses/authoring/home"),
                         "https://atheniq.courses")

    def test_a_non_default_port_is_kept(self):
        self.assertEqual(trust.origin_of("http://127.0.0.1:18080/authoring"),
                         "http://127.0.0.1:18080")

    def test_an_origin_is_already_an_origin(self):
        self.assertEqual(trust.origin_of("https://studio.atheniq.courses/"),
                         "https://studio.atheniq.courses")


class Verdicts(unittest.TestCase):
    def test_a_trusted_origin_passes(self):
        result = trust.verdict(ORIGIN, 401, GOOD)
        self.assertTrue(result.ok, result.failures)

    def test_the_401_is_the_expected_answer_not_a_failure(self):
        """The probe is anonymous; only the headers are being judged."""
        self.assertTrue(trust.verdict(ORIGIN, 401, GOOD).ok)

    def test_no_allow_origin_is_the_failure_this_exists_for(self):
        result = trust.verdict(ORIGIN, 401, {"access-control-allow-credentials": "true"})
        self.assertFalse(result.ok)
        self.assertIn("CORS_ORIGIN_WHITELIST", " ".join(result.failures))

    def test_a_wildcard_does_not_count(self):
        """A wildcard is refused by the browser whenever cookies are sent."""
        result = trust.verdict(ORIGIN, 401, {"access-control-allow-origin": "*",
                                             "access-control-allow-credentials": "true"})
        self.assertFalse(result.ok)
        self.assertIn("wildcard", " ".join(result.failures))

    def test_an_answer_meant_for_another_origin_does_not_count(self):
        result = trust.verdict(ORIGIN, 401, {"access-control-allow-origin":
                                             "https://apps.atheniq.courses",
                                             "access-control-allow-credentials": "true"})
        self.assertFalse(result.ok)
        self.assertIn("different origin", " ".join(result.failures))

    def test_credentials_must_be_allowed(self):
        result = trust.verdict(ORIGIN, 401, {"access-control-allow-origin": ORIGIN})
        self.assertFalse(result.ok)
        self.assertIn("Credentials", " ".join(result.failures))

    def test_no_answer_is_a_failure(self):
        result = trust.verdict(ORIGIN, None, {})
        self.assertFalse(result.ok)
        self.assertIn("no answer", " ".join(result.failures))


class NegativeControl(unittest.TestCase):
    def test_an_unconfigured_origin_must_be_refused(self):
        original = trust.fetch
        trust.fetch = lambda studio, origin, timeout=15.0: (401, {})
        try:
            self.assertTrue(trust.check_stranger("https://studio.test").ok)
        finally:
            trust.fetch = original

    def test_an_allow_all_configuration_is_caught(self):
        original = trust.fetch
        trust.fetch = lambda studio, origin, timeout=15.0: (
            401, {"access-control-allow-origin": origin})
        try:
            result = trust.check_stranger("https://studio.test")
            self.assertFalse(result.ok)
            self.assertIn("allows every origin", " ".join(result.failures))
        finally:
            trust.fetch = original


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.original = trust.fetch
        self.seen = []

        def fake(studio, origin, timeout=15.0):
            self.seen.append(origin)
            if origin == trust.STRANGER:
                return 401, {}
            return 401, {"access-control-allow-origin": origin,
                         "access-control-allow-credentials": "true"}

        trust.fetch = fake

    def tearDown(self):
        trust.fetch = self.original

    def test_it_checks_the_platforms_origins_and_the_stranger(self):
        with redirect_stdout(io.StringIO()):
            status = trust.main(["--studio", "https://studio.test"])
        self.assertEqual(status, 0)
        self.assertIn(trust.origin_of("https://atheniq.courses"), self.seen)
        self.assertIn(trust.STRANGER, self.seen)

    def test_a_refused_origin_fails_the_run(self):
        trust.fetch = lambda studio, origin, timeout=15.0: (401, {})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(trust.main(["--studio", "https://studio.test", ORIGIN]), 1)

    def test_json_output_is_machine_readable(self):
        out = io.StringIO()
        with redirect_stdout(out):
            trust.main(["--studio", "https://studio.test", "--json", ORIGIN])
        payload = json.loads(out.getvalue())
        self.assertTrue(payload[0]["ok"])
        self.assertEqual(payload[0]["origin"], ORIGIN)


if __name__ == "__main__":
    unittest.main()
