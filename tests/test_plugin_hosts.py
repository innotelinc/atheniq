"""`contrib/tutor-atheniq-hosts` — the platform answers on one host.

The plugin is read as source, not imported: `atheniqhosts.plugin` imports Tutor,
which the test environment does not have. What is worth asserting is the shape
of the configuration it emits, which is text either way.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "contrib" / "tutor-atheniq-hosts" / "atheniqhosts" / "plugin.py"


class LearnerApps(unittest.TestCase):
    """The MFEs live at paths on the LMS host, and their files have to follow."""

    def setUp(self):
        self.text = PLUGIN.read_text(encoding="utf-8")

    def test_every_learner_app_has_its_own_handle(self):
        """The paths the `mfe` container actually serves the apps on.

        `learner-dashboard`, not `dashboard`: the container routes by the app's
        own base path, and `/dashboard` is the platform's name for it (handled
        by the redirect below).
        """
        paths = re.search(r"MFE_PATHS = \((.*?)\)", self.text, re.S).group(1)
        for app in ("catalog", "learning", "learner-dashboard", "profile",
                    "account", "discussions", "authoring", "communications",
                    "gradebook", "ora-grading", "admin-console", "authn"):
            self.assertIn(f'"{app}"', paths)
        self.assertNotIn('"dashboard"', paths)

    def test_dashboard_redirects_to_the_app_the_container_serves(self):
        """`/dashboard` is a 200 with an empty root div unless it redirects."""
        self.assertIn('DASHBOARD_FROM = "dashboard"', self.text)
        self.assertIn('DASHBOARD_TO = "learner-dashboard"', self.text)
        # The suffix is carried over, so a deep link keeps its route. The
        # doubled braces are the f-string's escape for Caddy's `{uri}`.
        self.assertIn("@atheniq_dashboard path_regexp ^/{DASHBOARD_FROM}(/.*)?$", self.text)
        self.assertIn("redir @atheniq_dashboard /{DASHBOARD_TO}{{re.atheniq_dashboard.1}} 302",
                      self.text)

    def test_the_handles_proxy_to_the_mfe_container(self):
        self.assertIn("reverse_proxy mfe:8002", self.text)
        # A `handle` without a matcher would swallow the LMS's own paths.
        self.assertIn("handle /{path}*", self.text)

    def test_the_mfe_bundles_are_proxied_too(self):
        """The app path serves the shell; its scripts live at the origin root.

        Pointing only `/dashboard` at the MFE returns `index.html`, which then
        asks for `/runtime.<hash>.js` and `/app.<hash>.js`. Those match no
        `handle`, fall through to the LMS and 404 — the page loads and renders
        nothing, which is exactly the bug this pins.
        """
        self.assertIn("MFE_ASSET_PATTERN", self.text)
        self.assertIn("path_regexp {MFE_ASSET_PATTERN}", self.text)
        pattern = re.search(r'MFE_ASSET_PATTERN = r"(.*?)"', self.text).group(1)
        compiled = re.compile(pattern)
        for asset in ("/runtime.67b72a9958ef92f010af.js",
                      "/app.49406393ada8e94ce8c2.js",
                      "/778.bcf50168f6a7d190079c.css",
                      "/cssLayerOrder.2953d0c76f7c61ac484f.css",
                      "/site/atheniq-unity.css",
                      "/asset-manifest.json"):
            self.assertRegex(asset, compiled)

    def test_the_bundle_matcher_leaves_the_lms_alone(self):
        """Course photographs, the login page and the API stay with the LMS."""
        pattern = re.search(r'MFE_ASSET_PATTERN = r"(.*?)"', self.text).group(1)
        compiled = re.compile(pattern)
        for path in ("/login", "/api/courses/v1/courses/", "/courses",
                     "/static/atheniq/images/courses/ACCT201.jpg",
                     "/static/atheniq/unity-theme.css", "/theming/asset/logo.png",
                     "/dashboard", "/learner-dashboard/"):
            self.assertNotRegex(path, compiled)

    def test_the_bundle_handle_is_in_the_same_site_block(self):
        """Every patch targets `caddyfile-lms`, so none can land elsewhere."""
        self.assertEqual(self.text.count('"caddyfile-lms"'), 3)
        # The asset handle comes after the app handles: order is precedence.
        self.assertLess(self.text.index("MFE_PATHS = ("),
                        self.text.index("MFE_ASSET_PATTERN ="))


if __name__ == "__main__":
    unittest.main()
