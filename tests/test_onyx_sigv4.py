"""Unit tests for scripts/onyx-buckets.py's AWS SigV4 signer.

The signer is pinned to the same published AWS conformance values the ONYX
objectstore itself tests against (services/objectstore/testdata/sigv4), so a
misreading of the spec fails here rather than only against a live store.
"""
import unittest

from _loader import load

onyx = load("onyx-buckets.py")

ACCESS = "AKIDEXAMPLE"
SECRET = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"


class SigningKeyDerivation(unittest.TestCase):
    def test_matches_published_vector(self):
        # AWS documentation's worked example: 20150830 / us-east-1 / iam.
        key = onyx.signing_key(SECRET, "20150830", "us-east-1", "iam")
        self.assertEqual(
            key.hex(),
            "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9",
        )


class GetVanillaVector(unittest.TestCase):
    """The AWS suite's `get-vanilla` case, replayed exactly."""

    def test_authorization_matches_published_signature(self):
        auth = onyx.build_authorization(
            "GET", "example.amazonaws.com", "/", ACCESS, SECRET, "us-east-1",
            "service",
            {"host": "example.amazonaws.com", "x-amz-date": "20150830T123600Z"},
            onyx.EMPTY_SHA256, "20150830T123600Z",
        )
        self.assertIn("Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request", auth)
        self.assertIn("SignedHeaders=host;x-amz-date", auth)
        self.assertIn(
            "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
            auth,
        )

    def test_header_value_is_folded(self):
        # The suite's header-value cases fold whitespace; guard the behaviour.
        folded = onyx.build_authorization(
            "GET", "example.amazonaws.com", "/", ACCESS, SECRET, "us-east-1",
            "service",
            {"host": "  example.amazonaws.com  ", "x-amz-date": "20150830T123600Z"},
            onyx.EMPTY_SHA256, "20150830T123600Z",
        )
        self.assertIn("Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31",
                      folded)


class UriEncoding(unittest.TestCase):
    def test_aws_unreserved_and_escaping_rules(self):
        cases = [
            ("simple", "simple"),
            ("a b", "a%20b"),
            ("a+b", "a%2Bb"),
            ("~-._", "~-._"),
            ("\u00e9", "%C3%A9"),
            ("*'()", "%2A%27%28%29"),
            ("a/b", "a/b"),  # path separators are preserved
        ]
        for source, expected in cases:
            self.assertEqual(onyx._uri_encode(source), expected, source)


class S3RequestTarget(unittest.TestCase):
    def test_path_style_bucket_uri(self):
        # path-style addresses the bucket in the path, service root when empty.
        self.assertEqual(onyx._uri_encode("/atheniq-files"), "/atheniq-files")
        self.assertEqual(onyx._uri_encode("/"), "/")


if __name__ == "__main__":
    unittest.main()
