"""The certificate checker's decisions, made against certificates we hand it.

A TLS check is only useful if it fails for the right reasons, and every reason
it has — an uncovered name, a chain with nothing but the leaf, a renewal that
has crept inside the warning window — is a decision about bytes, not about the
network. So the decisions are tested here with hand-built inputs, and the one
call that has to reach out uses a name RFC 2606 guarantees will not resolve.
"""
import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

from _loader import load

cert = load("cert-check.py")

LEAF = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
ISSUER = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


class HostMatching(unittest.TestCase):
    def test_an_exact_name_covers_itself(self):
        self.assertTrue(cert.host_matches("lms.innotel.us", "lms.innotel.us"))

    def test_names_are_case_insensitive_and_ignore_the_root_dot(self):
        self.assertTrue(cert.host_matches("LMS.Innotel.US", "lms.innotel.us."))

    def test_a_wildcard_covers_one_label(self):
        self.assertTrue(cert.host_matches("*.innotel.us", "studio.innotel.us"))
        self.assertTrue(cert.host_matches("*.learn.innotel.us", "apps.learn.innotel.us"))

    def test_a_wildcard_does_not_cover_the_apex(self):
        self.assertFalse(cert.host_matches("*.innotel.us", "innotel.us"))

    def test_a_wildcard_does_not_cover_more_than_one_label(self):
        self.assertFalse(cert.host_matches("*.innotel.us", "apps.lms.innotel.us"))

    def test_a_different_name_is_not_covered(self):
        self.assertFalse(cert.host_matches("lms.innotel.us", "lms.innotel.com"))


class SanCoverage(unittest.TestCase):
    def test_it_reads_ssl_style_san_entries(self):
        san = (("DNS", "lms.innotel.us"), ("DNS", "apps.lms.innotel.us"))
        self.assertTrue(cert.certificate_covers("apps.lms.innotel.us", san))

    def test_it_accepts_a_name_a_wildcard_covers(self):
        self.assertTrue(cert.certificate_covers("learn.innotel.us",
                                                (("DNS", "*.innotel.us"),)))

    def test_it_ignores_non_dns_entries(self):
        self.assertFalse(cert.certificate_covers("lms.innotel.us",
                                                 (("IP Address", "73.68.203.71"),)))

    def test_no_san_entries_cover_nothing(self):
        self.assertFalse(cert.certificate_covers("lms.innotel.us", ()))
        self.assertFalse(cert.certificate_covers("lms.innotel.us", None))


class ChainDepth(unittest.TestCase):
    def test_it_counts_the_certificates_in_a_bundle(self):
        self.assertEqual(cert.count_certificates(LEAF), 1)
        self.assertEqual(cert.count_certificates(LEAF + ISSUER), 2)

    def test_a_pem_chain_is_measured_without_the_network(self):
        """With the bytes in hand, no openssl call is made — host is irrelevant."""
        self.assertEqual(cert.chain_depth("not-a-host", 443, 1.0, LEAF + ISSUER), 2)

    def test_a_leaf_only_chain_is_a_failure(self):
        result = cert.Result(host="lms.innotel.us")
        cert._finish(result, "lms.innotel.us", 443, 1.0, cert.WARN_DAYS, LEAF)
        self.assertFalse(result.ok)
        self.assertEqual(result.chain, 1)
        self.assertTrue(any("incomplete chain" in f for f in result.failures))

    def test_a_complete_chain_passes(self):
        result = cert.Result(host="lms.innotel.us")
        cert._finish(result, "lms.innotel.us", 443, 1.0, cert.WARN_DAYS, LEAF + ISSUER)
        self.assertTrue(result.ok)
        self.assertEqual(result.chain, 2)


class Expiry(unittest.TestCase):
    def now(self):
        return datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)

    def test_openssl_timestamps_parse_as_utc(self):
        self.assertEqual(cert.parse_openssl_time("Jan 15 17:43:31 2027 GMT"),
                         datetime(2027, 1, 15, 17, 43, 31, tzinfo=timezone.utc))

    def test_days_until_counts_forward_and_back(self):
        self.assertAlmostEqual(cert.days_until(self.now() + timedelta(days=30), self.now()), 30.0)
        self.assertAlmostEqual(cert.days_until(self.now() - timedelta(days=1), self.now()), -1.0)

    def test_an_expired_certificate_fails(self):
        result = cert.Result(host="lms.innotel.us")
        stale = self.now() - timedelta(days=3)
        cert._finish(result, "lms.innotel.us", 443, 1.0, cert.WARN_DAYS, LEAF + ISSUER,
                     {"notAfter": stale.strftime("%b %d %H:%M:%S %Y GMT"),
                      "subjectAltName": (("DNS", "lms.innotel.us"),)}, now=self.now())
        self.assertFalse(result.ok)
        self.assertTrue(any("expired" in f for f in result.failures))

    def test_a_renewal_inside_the_window_warns_but_passes(self):
        result = cert.Result(host="lms.innotel.us")
        soon = self.now() + timedelta(days=5)
        cert._finish(result, "lms.innotel.us", 443, 1.0, cert.WARN_DAYS, LEAF + ISSUER,
                     {"notAfter": soon.strftime("%b %d %H:%M:%S %Y GMT")}, now=self.now())
        self.assertTrue(result.ok)
        self.assertTrue(any("renews in" in w for w in result.warnings))


class HttpVerdicts(unittest.TestCase):
    """Only a dead backend fails: these names redirect, and `/` is not a page on all."""

    def test_a_redirect_is_not_a_failure(self):
        self.assertIsNone(cert.http_failure(301))
        self.assertIsNone(cert.http_failure(302))

    def test_a_successful_page_is_not_a_failure(self):
        self.assertIsNone(cert.http_failure(200))

    def test_a_missing_page_is_not_a_failure(self):
        self.assertIsNone(cert.http_failure(404))

    def test_a_server_error_fails(self):
        self.assertIn("502", cert.http_failure(502) or "")
        self.assertIsNotNone(cert.http_failure(500))

    def test_no_response_fails(self):
        self.assertIsNotNone(cert.http_failure(None))

    def test_the_http_status_is_reported_in_the_line(self):
        result = cert.Result(host="lms.innotel.us", ok=True, chain=3, days_left=90.0,
                             subject="lms.innotel.us", status=301)
        self.assertIn("http=301", result.line())

    def test_the_http_verdict_fails_the_run(self):
        """A 502 is a failure the certificate alone would have called a pass."""
        result = cert.Result(host="atheniq.innotel.us", chain=3, days_left=57.0,
                             failures=[cert.http_failure(502)])
        self.assertFalse(result.ok)
        self.assertTrue(result.line().startswith("FAIL"))
        out = io.StringIO()
        with redirect_stdout(out):
            status = cert.summarize([result])
        self.assertEqual(status, 1)

    def test_an_unreachable_http_probe_returns_none(self):
        self.assertIsNone(cert.check_http("cert-check.invalid", timeout=2.0))


class Reporting(unittest.TestCase):
    def test_the_line_names_the_state_and_the_measurements(self):
        ok = cert.Result(host="lms.innotel.us", ok=True, chain=3, days_left=90.4,
                         subject="lms.innotel.us")
        self.assertTrue(ok.line().startswith("OK"))
        self.assertIn("chain=3", ok.line())
        self.assertIn("expires=90d", ok.line())
        bad = cert.Result(host="apps.lms.innotel.us", chain=1, failures=["incomplete chain: 1"])
        self.assertTrue(bad.line().startswith("FAIL"))
        self.assertIn("incomplete chain", bad.line())

    def _summary(self, results):
        out = io.StringIO()
        with redirect_stdout(out):
            status = cert.summarize(results)
        return status, out.getvalue()

    def test_a_clean_run_exits_zero(self):
        status, text = self._summary([cert.Result(host="lms.innotel.us", ok=True)])
        self.assertEqual(status, 0)
        self.assertIn("0 failure(s)", text)

    def test_any_failure_exits_one(self):
        status, _ = self._summary([cert.Result(host="lms.innotel.us", ok=True),
                                   cert.Result(host="x", failures=["boom"])])
        self.assertEqual(status, 1)

    def test_reported_names_are_the_ones_asked_for(self):
        self.assertEqual(list(cert.PLATFORM_HOSTS),
                         list(dict.fromkeys(cert.PLATFORM_HOSTS)))
        # Canonical names first, then the aliases that must keep answering.
        self.assertEqual(cert.PLATFORM_HOSTS[:4],
                         ("atheniq.innotel.us", "learn.innotel.us",
                          "apps.learn.innotel.us", "lms.innotel.us"))
        self.assertIn("apps.lms.innotel.us", cert.PLATFORM_HOSTS)
        self.assertIn("atheniq.innotel.us", cert.PLATFORM_HOSTS)
        # The staff generation console: a public name like any other, even
        # though an SSO proxy stands in front of it.
        self.assertIn("ai.lms.innotel.us", cert.PLATFORM_HOSTS)


class UnreachableName(unittest.TestCase):
    def test_an_unresolvable_name_is_a_failure_not_a_crash(self):
        """.invalid never resolves (RFC 2606), so this needs no network of its own."""
        result = cert.check_host("cert-check.invalid", timeout=2.0)
        self.assertFalse(result.ok)
        self.assertTrue(result.failures)


if __name__ == "__main__":
    unittest.main()
