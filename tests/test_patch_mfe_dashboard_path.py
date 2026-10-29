"""The dashboard routing patch, checked against the shapes Tutor renders.

Both edits are string surgery on generated files, so what is worth testing is
that each one matches the text the deployment actually holds and that it cannot
match anything else: the `mfe` site block is rendered from a loop that still
writes a `/learner-dashboard` handle, and the LMS site block's two rules are
written by `atheniqhosts/plugin.py`.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "patch-mfe-dashboard-path.py"
_spec = importlib.util.spec_from_file_location("patch_mfe_dashboard_path", _MODULE_PATH)
paths = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paths)


#: The `mfe` site block as Tutor renders it: the patch point, the trailing-slash
#: rule, then the loop's own `/learner-dashboard` handle below it.
MFE = """\
:8002 {
    log {
        output stdout
    }

    # An MFE path without its trailing slash is not the app's own URL: the
    # router's basename strips the prefix and the path left over is "", which
    # matches no route - the shell loads and stays blank.
    @mfe_no_trailing_slash path_regexp mfe_noslash ^/(account|admin-console|authn|authoring|catalog|communications|discussions|gradebook|learner-dashboard|learning|ora-grading|profile|site)$
    redir @mfe_no_trailing_slash /{re.mfe_noslash.1}/ 308

    @mfe_learner-dashboard {
        path /learner-dashboard /learner-dashboard/*
    }
    handle @mfe_learner-dashboard {
        uri strip_prefix /learner-dashboard
        root * /openedx/dist/learner-dashboard
        try_files /{path} /index.html
        file_server
    }
}
"""

#: The LMS site block's rules, as the plugin wrote them before the move.
LMS = """\
atheniq.courses{$default_site_port} {
    handle /catalog* {
        reverse_proxy mfe:8002
    }
    # AthenIQ: the learner app lives on the university host, not a second domain.
    handle /learner-dashboard* {
        reverse_proxy mfe:8002
    }
    # AthenIQ: /dashboard is the URL the platform links to; the app is served
    # at /learner-dashboard in the mfe container.
    @atheniq_dashboard path_regexp ^/dashboard(/.*)?$
    redir @atheniq_dashboard /learner-dashboard{re.atheniq_dashboard.1} 302
}
"""


class MfeBlock(unittest.TestCase):
    def setUp(self):
        self.text, self.result = paths.patch_mfe(MFE)

    def test_the_dist_is_served_at_the_new_address(self):
        self.assertEqual(self.result, "patched")
        self.assertIn("@atheniq_dashboard path /dashboard /dashboard/*", self.text)
        self.assertIn("uri strip_prefix /dashboard", self.text)
        # The directory keeps the name the app was built as.
        self.assertIn("root * /openedx/dist/learner-dashboard", self.text)

    def test_the_old_path_is_redirected_rather_than_served(self):
        self.assertIn("@atheniq_old_dashboard path_regexp ^/learner-dashboard(/.*)?$",
                      self.text)
        self.assertIn("redir @atheniq_old_dashboard /dashboard{re.atheniq_old_dashboard.1} 302",
                      self.text)
        # The block the loop still writes stays below ours; ours wins on order,
        # and the trailing-slash rule has to know the new name.
        self.assertLess(self.text.index("@atheniq_dashboard path /dashboard"),
                        self.text.index("@mfe_learner-dashboard"))
        self.assertIn("|dashboard|", self.text)
        self.assertNotIn("|learner-dashboard|", self.text)

    def test_a_second_run_changes_nothing(self):
        again, result = paths.patch_mfe(self.text)
        self.assertEqual(result, "already patched")
        self.assertEqual(again, self.text)

    def test_a_rendering_without_the_anchor_is_refused(self):
        _text, result = paths.patch_mfe(":8002 {\n}\n")
        self.assertEqual(result, "anchor missing — left alone")


class LmsBlock(unittest.TestCase):
    def setUp(self):
        self.text, self.result = paths.patch_lms(LMS)

    def test_the_app_is_proxied_at_the_address_the_platform_links_to(self):
        self.assertEqual(self.result, "patched")
        self.assertIn("handle /dashboard* {\n        reverse_proxy mfe:8002\n    }",
                      self.text)
        self.assertNotIn("handle /learner-dashboard*", self.text)

    def test_the_old_address_is_sent_to_the_new_one(self):
        self.assertIn("@atheniq_old_dashboard path_regexp ^/learner-dashboard(/.*)?$",
                      self.text)
        self.assertIn("redir @atheniq_old_dashboard /dashboard{re.atheniq_old_dashboard.1} 302",
                      self.text)
        self.assertNotIn("redir @atheniq_dashboard /learner-dashboard", self.text)

    def test_a_second_run_changes_nothing(self):
        again, result = paths.patch_lms(self.text)
        self.assertEqual(result, "already patched")
        self.assertEqual(again, self.text)

    def test_a_rendering_without_the_anchor_is_refused(self):
        _text, result = paths.patch_lms("atheniq.courses {\n}\n")
        self.assertEqual(result, "anchor missing — left alone")


if __name__ == "__main__":
    unittest.main()
