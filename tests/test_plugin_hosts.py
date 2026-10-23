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
        cls.cms = "\n".join(
            text for name, text in cls.sinks["ENV_PATCHES"].items
            if name == "openedx-cms-production-settings"
        )
        cls.lms = "\n".join(
            text for name, text in cls.sinks["ENV_PATCHES"].items
            if name == "openedx-lms-production-settings"
        )
        # Additional site blocks (the legacy names), which are appended to the
        # whole Caddyfile rather than to the LMS site block.
        cls.hosts = "\n".join(
            text for name, text in cls.sinks["ENV_PATCHES"].items
            if name == "caddyfile"
        )

    def test_studio_trusts_the_host_that_serves_the_authoring_app(self):
        """The authoring app lives on the LMS host and calls Studio's APIs.

        Tutor whitelists `studio.<host>` and `apps.<host>` only, so a call from
        `https://<host>/authoring` came back without
        `Access-Control-Allow-Origin` and the app reported that it could not
        load Studio home.
        """
        self.assertIn('CORS_ORIGIN_WHITELIST.append("https://{{ LMS_HOST }}")', self.cms)
        self.assertIn('CSRF_TRUSTED_ORIGINS.append("https://{{ LMS_HOST }}")', self.cms)

    def test_studio_trusts_the_legacy_names_too(self):
        """Old bookmarks sign in on the same session as the new address."""
        for hosts in ("ATHENIQ_LEGACY_LMS_HOSTS", "ATHENIQ_LEGACY_MFE_HOSTS"):
            self.assertIn("{% for host in " + hosts + " %}", self.cms)
        self.assertIn('CORS_ORIGIN_WHITELIST.append("https://{{ host }}")', self.cms)
        self.assertIn('CSRF_TRUSTED_ORIGINS.append("https://{{ host }}")', self.cms)

    def test_every_learner_app_is_proxied_from_the_university_host(self):
        for app in ("catalog", "learning", "learner-dashboard", "profile",
                    "account", "discussions", "authoring", "communications",
                    "gradebook", "ora-grading", "admin-console",
                    "instructor-dashboard", "authn"):
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

    def test_a_legacy_mfe_host_sends_its_bookmarks_to_the_university_host(self):
        """`apps.lms.innotel.us/authoring/home` belongs at the same page on the
        renamed host, not on a second copy of the bundle."""
        self.assertIn('redir https://{{ LMS_HOST }}{uri} 301', self.hosts)

    def test_the_legacy_hosts_are_no_longer_a_proxy(self):
        """A host that serves the bundle also serves a second, stale origin."""
        legacy_block = self.hosts.split("{% for host in ATHENIQ_LEGACY_MFE_HOSTS %}")[1]
        legacy_block = legacy_block.split("{% endfor %}")[0]
        self.assertNotIn("reverse_proxy", legacy_block)

    def test_mfe_config_is_rewritten_with_or_without_a_scheme(self):
        """`BASE_URL` names the host bare; every other key is a URL."""
        self.assertIn('.replace("https://{{ MFE_HOST }}", "https://{{ LMS_HOST }}")', self.lms)
        self.assertIn('.replace("{{ MFE_HOST }}", "{{ LMS_HOST }}")', self.lms)

    def test_the_lms_own_app_urls_move_with_the_apps(self):
        """The LMS builds links from module-level settings, not from MFE_CONFIG.

        `INSTRUCTOR_MICROFRONTEND_URL` and its neighbours are generated from
        `MFE_HOST`, so rewriting only `MFE_CONFIG` left every one of them — and
        the `/login` redirect — pointing at `apps.<host>`.
        """
        self.assertIn('and "https://{{ MFE_HOST }}" in _atheniq_value', self.lms)
        self.assertNotIn("apps.learn.innotel.us", self.lms)
        self.assertNotIn("innotel", self.lms)

    def test_nothing_is_left_for_jinja_or_a_doubled_brace(self):
        """The patch is a plain string by the time Tutor sees it."""
        self.assertNotIn("{{", self.caddy)
        self.assertNotIn("{%", self.caddy)
        self.assertNotIn("{path}", self.caddy)


if __name__ == "__main__":
    unittest.main()
