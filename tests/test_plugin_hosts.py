"""`contrib/tutor-atheniq-hosts` — the learner apps answer on the LMS host.

The plugin is imported against a stub `tutor` so the assertions run on the text
Tutor would actually be given, not on the source that builds it: a stray `{{`
in an f-string is invisible to a source grep and breaks Caddy at deploy time.
"""
import importlib.util
import pathlib
import re
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "contrib" / "tutor-atheniq-hosts" / "atheniqhosts" / "plugin.py"


class Sink:
    """Stands in for one of Tutor's filter lists."""

    def __init__(self):
        self.items = []

    def add_item(self, item, **_kwargs):
        self.items.append(item)

    def add_items(self, items, **_kwargs):
        self.items.extend(items)


def load_plugin():
    """Import the plugin with nothing of Tutor except the hooks it touches."""
    names = ("IS_FILE_RENDERED", "ENV_TEMPLATE_ROOTS", "ENV_TEMPLATE_TARGETS",
             "ENV_PATCHES", "CONFIG_DEFAULTS", "CONFIG_OVERRIDES")
    sinks = {name: Sink() for name in names}
    stub = types.ModuleType("tutor")
    stub.hooks = types.SimpleNamespace(
        Filters=types.SimpleNamespace(**sinks),
        priorities=types.SimpleNamespace(LOW=0, HIGH=100),
    )
    saved = sys.modules.get("tutor")
    sys.modules["tutor"] = stub
    try:
        spec = importlib.util.spec_from_file_location("atheniqhosts_plugin", PLUGIN)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("tutor", None)
        else:
            sys.modules["tutor"] = saved
    return module, sinks


class LearnerApps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module, cls.sinks = load_plugin()
        cls.caddy = "\n".join(
            text for name, text in cls.sinks["ENV_PATCHES"].items
            if name == "caddyfile-lms"
        )

    def test_every_learner_app_is_proxied_from_the_university_host(self):
        for app in ("catalog", "learning", "learner-dashboard", "profile",
                    "account", "discussions", "authoring", "communications",
                    "gradebook", "ora-grading", "admin-console", "authn"):
            self.assertIn(f"handle /{app}* {{\n    reverse_proxy mfe:8002\n}}",
                          self.caddy)

    def test_the_app_the_container_serves_is_the_one_proxied(self):
        """`/dashboard` is not an app path in the `mfe` container."""
        self.assertIn("learner-dashboard", self.module.MFE_PATHS)
        self.assertNotIn("dashboard", self.module.MFE_PATHS)

    def test_dashboard_redirects_to_the_app_the_container_serves(self):
        """`/dashboard` is a 200 with an empty `#root` unless it redirects."""
        self.assertIn("@atheniq_dashboard path_regexp ^/dashboard(/.*)?$", self.caddy)
        self.assertIn("redir @atheniq_dashboard /learner-dashboard{re.atheniq_dashboard.1} 302",
                      self.caddy)

    def test_the_dashboard_redirect_keeps_the_rest_of_the_path(self):
        """A deep link lands on the same route inside the app."""
        rule = re.search(r"@atheniq_dashboard path_regexp (\S+)", self.caddy).group(1)
        match = re.match(rule, "/dashboard/programs")
        self.assertEqual(match.group(1), "/programs")
        self.assertIsNone(re.match(rule, "/dashboardx"))

    def test_the_mfe_bundles_are_proxied_too(self):
        """The app path serves the shell; its scripts live at the origin root."""
        self.assertIn("@atheniq_mfe_assets path_regexp", self.caddy)
        pattern = re.search(r"@atheniq_mfe_assets path_regexp (\S+)", self.caddy).group(1)
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
        pattern = re.search(r"@atheniq_mfe_assets path_regexp (\S+)", self.caddy).group(1)
        compiled = re.compile(pattern)
        for path in ("/login", "/api/courses/v1/courses/", "/courses",
                     "/static/atheniq/images/courses/ACCT201.jpg",
                     "/static/atheniq/unity-theme.css", "/theming/asset/logo.png",
                     "/dashboard", "/learner-dashboard/app.js"):
            self.assertNotRegex(path, compiled)

    def test_nothing_is_left_for_jinja_or_a_doubled_brace(self):
        """The patch is a plain string by the time Tutor sees it."""
        self.assertNotIn("{{", self.caddy)
        self.assertNotIn("{%", self.caddy)
        self.assertNotIn("{path}", self.caddy)


if __name__ == "__main__":
    unittest.main()
