"""Unit tests for scripts/track-credential.py (detection only — no LMS/Signara)."""
import json
import unittest

from _loader import ROOT, load

cred = load("track-credential.py")


def track(tid, courses, ctype="certificate"):
    return {"id": tid, "title": tid.title(), "summary": "s", "status": "active",
            "courses": courses, "credential": {"type": ctype,
                                               "title": f"{tid} — Certification",
                                               "signara_template": "course-completion"}}


class Detection(unittest.TestCase):
    def test_completes_only_when_every_course_is_earned(self):
        doc = {"tracks": [track("a", ["course-v1:O+A1+1", "course-v1:O+A2+1"]),
                          track("b", ["course-v1:O+B1+1"])]}
        done = cred.completed_tracks(doc, ["course-v1:O+A1+1", "course-v1:O+B1+1"])
        self.assertEqual([t["id"] for t in done], ["b"])

    def test_completes_with_the_whole_ladder(self):
        doc = {"tracks": [track("a", ["course-v1:O+A1+1", "course-v1:O+A2+1"])]}
        done = cred.completed_tracks(doc, ["course-v1:O+A1+1", "course-v1:O+A2+1"])
        self.assertEqual([t["id"] for t in done], ["a"])

    def test_missing_courses_reports_the_gap(self):
        t = track("a", ["course-v1:O+A1+1", "course-v1:O+A2+1"])
        self.assertEqual(cred.missing_courses(t, ["course-v1:O+A1+1"]),
                         ["course-v1:O+A2+1"])

    def test_credential_for_skips_non_signing_types(self):
        self.assertIsNone(cred.credential_for(track("a", ["course-v1:O+A1+1"], "none")))
        self.assertIsNotNone(cred.credential_for(track("a", ["course-v1:O+A1+1"])))

    def test_empty_course_list_is_never_complete(self):
        self.assertEqual(cred.completed_tracks({"tracks": [track("a", [])]}, []), [])


class BridgeIntegration(unittest.TestCase):
    def test_cert_bridge_can_drive_track_credential_issuance(self):
        bridge = load("cert-bridge.py")
        self.assertTrue(callable(bridge.sync_track_credentials))
        tc = bridge._load_module("x_track_credential",
                                 str(ROOT / "scripts" / "track-credential.py"))
        self.assertTrue(callable(tc.completed_tracks))
        self.assertTrue(callable(tc.issue))


class ShippedCatalog(unittest.TestCase):
    def test_it_support_needs_all_four_courses(self):
        doc = json.loads((ROOT / "config" / "workforce-tracks.json").read_text())
        three = ["course-v1:InnotelLabs+ITSP101+2026_T1",
                 "course-v1:InnotelLabs+ITSP102+2026_T1",
                 "course-v1:InnotelLabs+ITSP103+2026_T1"]
        self.assertEqual(cred.completed_tracks(doc, three), [])
        four = three + ["course-v1:InnotelLabs+ITSP104+2026_T1"]
        done = cred.completed_tracks(doc, four)
        self.assertEqual([t["id"] for t in done], ["it-support"])


if __name__ == "__main__":
    unittest.main()
