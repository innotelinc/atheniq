"""The certificate renderer must sign the names the platform actually uses.

A credential is not ASCII: `FAST AI — Applied AI Skills` carries an em dash, and
learners' names carry accents and the occasional curly quote. The renderer wrote
the document as ISO-8859-1, where the em dash does not exist, so the first
conferral of that program ended with `'latin-1' codec can't encode character`
and no signature. These tests pin the encoding to the one the fonts declare.
"""
import os
import tempfile
import unittest

from _loader import load

bridge = load("cert-bridge.py")

EM_DASH = "\u2014"
CERT = {
    "org": "Innotel Labs",
    "course_id": "course-v1:InnotelLabs+FAI101+2026_T4",
    "course_name": "FAI101 " + EM_DASH + " Applied AI Foundations for Work",
    "grade": "GPA 3.30",
    "created_date": "2026-10-23 03:15:32",
    "verify_uuid": "fast-ai::learner",
    "heading": "FAST AI " + EM_DASH + " Applied AI Skills",
    "statement": "has completed every requirement of the program and is awarded",
    "award": "0 credits \u00b7 grade point average 3.30 \u00b7 conferred 2026-10-23",
    "learner_name": "Zo\u00eb \u201cZo\u201d O'Hara",
}


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="atheniq-cert-")

    def render(self, cert):
        out = os.path.join(self.dir, "certificate.pdf")
        bridge.render_cert_pdf(cert, "D. Hunter", "Founder - Innotel", out)
        with open(out, "rb") as fh:
            return fh.read()

    def test_a_credential_with_an_em_dash_renders(self):
        blob = self.render(CERT)
        self.assertTrue(blob.startswith(b"%PDF-1.4"))
        # cp1252, the encoding the fonts are declared with: 0x97 is the em dash.
        self.assertIn(bytes([0x97]), blob)
        # ...and the accented name survives rather than crashing the document.
        self.assertIn(b"Zo\xeb", blob)

    def test_a_character_outside_the_encoding_is_replaced_not_fatal(self):
        cert = dict(CERT, learner_name="Learner \U0001f600")
        blob = self.render(cert)
        self.assertTrue(blob.startswith(b"%PDF-1.4"))
        self.assertNotIn("\U0001f600".encode("utf-8"), blob)


if __name__ == "__main__":
    unittest.main()
