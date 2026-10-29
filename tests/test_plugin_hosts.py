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
        for app in ("catalog", "learning", "dashboard", "profile",
                    "account", "discussions", "authoring", "communications",
                    "gradebook", "ora-grading", "admin-console",
                    "instructor-dashboard", "authn"):
            self.assertIn(f"handle /{app}* {{\n    reverse_proxy mfe:8002\n}}",
                          self.caddy)

    def test_the_dashboard_is_proxied_at_the_address_the_platform_links_to(self):
        """The app's public path is moved to `/dashboard`; this is its door."""
        self.assertIn("dashboard", self.module.MFE_PATHS)
        self.assertNotIn("learner-dashboard", self.module.MFE_PATHS)

    def test_the_old_dashboard_path_redirects_to_the_new_one(self):
        """A link or a bookmark from before the move still lands on the page."""
        self.assertIn("@atheniq_old_dashboard path_regexp ^/learner-dashboard(/.*)?$",
                      self.caddy)
        self.assertIn("redir @atheniq_old_dashboard /dashboard{re.atheniq_old_dashboard.1} 302",
                      self.caddy)

    def test_the_dashboard_redirect_keeps_the_rest_of_the_path(self):
        """A deep link lands on the same route inside the app."""
        rule = re.search(r"@atheniq_old_dashboard path_regexp (\S+)", self.caddy).group(1)
        match = re.match(rule, "/learner-dashboard/programs")
        self.assertEqual(match.group(1), "/programs")
        self.assertIsNone(re.match(rule, "/learner-dashboardx"))

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

    def test_a_studio_alias_serves_the_cms_as_the_cms(self):
        """The CMS is keyed to `CMS_HOST` and 404s a name it was not told about."""
        block = self._studio_block()
        self.assertIn("reverse_proxy cms:8000 {", block)
        self.assertIn("header_up Host {{ CMS_HOST }}", block)

    def test_a_studio_alias_asks_the_lms_as_the_lms(self):
        """`CMS_HOST` is not in the LMS's ALLOWED_HOSTS: `/api/mfe_config` 400s.

        The sign-in page Studio redirects to is the LMS's authn MFE, and the
        configuration that page reads comes from the LMS. Presenting it the CMS
        host — the name the CMS answers on — was a 400 on every request, so the
        login page loaded with no configuration behind it.
        """
        block = self._studio_block()
        lms_handler = block.split("handle /api/mfe_config*")[1]
        self.assertIn("reverse_proxy lms:8000 {", lms_handler)
        self.assertIn("header_up Host {{ LMS_HOST }}", lms_handler)
        self.assertNotIn("{{ CMS_HOST }}", lms_handler.split("handle /api/user*")[0])

    def test_a_studio_alias_carries_the_sign_in_page_and_its_bundles(self):
        """The authn shell is the MFE's; its scripts live at the origin root."""
        block = self._studio_block()
        self.assertIn("handle /authn* {", block)
        # The authn app's own shell and chunks are under `/authn/`, so the app
        # handler carries them; the root-level bundles are the asset matcher's.
        authn = block.split("handle /authn* {")[1].split("}")[0]
        self.assertIn("reverse_proxy mfe:8002", authn)
        pattern = re.search(r"@atheniq_studio_assets path_regexp (\S+)", block).group(1)
        compiled = re.compile(pattern)
        for asset in ("/778.bcf50168f6a7d190079c.css",
                      "/site/atheniq-unity.css", "/asset-manifest.json"):
            self.assertRegex(asset, compiled)
        for path in ("/home/", "/api/mfe_config/v1",
                     "/static/atheniq/images/courses/FAI101.jpg"):
            self.assertNotRegex(path, compiled)

    def test_a_second_spelling_redirects_to_the_canonical_host(self):
        """`www.<host>` keeps the path, so a printed link still lands on the page."""
        self.assertIn("{% for host in ATHENIQ_REDIRECT_HOSTS %}", self.hosts)
        block = self.hosts.split("{% for host in ATHENIQ_REDIRECT_HOSTS %}")[1].split("{% endfor %}")[0]
        self.assertIn("redir https://{{ LMS_HOST }}{uri} permanent", block)
        self.assertNotIn("reverse_proxy", block)

    def _studio_block(self):
        self.assertIn("{% for host in ATHENIQ_STUDIO_ALIAS_HOSTS %}", self.hosts)
        return self.hosts.split("{% for host in ATHENIQ_STUDIO_ALIAS_HOSTS %}")[1].split("{% endfor %}")[0]

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

        The guard must match the bare form too: `AUTHN_MICROFRONTEND_DOMAIN` is
        `apps.<host>/authn`, with no scheme, and it is what the password-reset
        mail is built from. Requiring `https://` there skipped it, so every
        reset link named a host nothing answers.
        """
        self.assertIn('and "{{ MFE_HOST }}" in _atheniq_value', self.lms)
        self.assertNotIn('and "https://{{ MFE_HOST }}" in _atheniq_value', self.lms)
        self.assertNotIn("apps.learn.innotel.us", self.lms)
        self.assertNotIn("innotel", self.lms)

    def test_the_reset_link_is_built_from_the_lms_host(self):
        """The password-reset mail's host, proved by running the patch's rewrite.

        `AUTHN_MICROFRONTEND_DOMAIN` is the bare `apps.<host>/authn` — no scheme —
        and it is what the authn MFE pastes into the reset mail. A guard that only
        matched `https://` left it on a name with no DNS record, so every learner
        was mailed a link to a host nothing answers. This executes the rewrite the
        patch actually ships, with a bare value, rather than grepping for it.
        """
        marker = "for _atheniq_name, _atheniq_value in list(globals().items()):"
        self.assertIn(marker, self.lms)
        loop = self.lms[self.lms.index(marker):]
        # The patch runs on Tutor's *template* text, so the value it sees is the
        # placeholder, not the rendered host: `AUTHN_MICROFRONTEND_DOMAIN` is
        # `{{ MFE_HOST }}/authn` with no scheme, which is exactly the form the
        # old guard skipped.
        settings = {
            "AUTHN_MICROFRONTEND_DOMAIN": "{{ MFE_HOST }}/authn",
            # URL form, which must not come out with a doubled scheme.
            "INSTRUCTOR_MICROFRONTEND_URL": "https://{{ MFE_HOST }}/instructor",
            # Nothing to do with the apps host: must be left alone.
            "LMS_ROOT_URL": "https://learn.innotel.us",
        }
        exec(loop, settings)
        self.assertEqual(settings["AUTHN_MICROFRONTEND_DOMAIN"], "{{ LMS_HOST }}/authn")
        self.assertEqual(settings["INSTRUCTOR_MICROFRONTEND_URL"], "https://{{ LMS_HOST }}/instructor")
        self.assertEqual(settings["LMS_ROOT_URL"], "https://learn.innotel.us")
        # And with the host filled in, that is the reset link a learner receives.
        rendered = settings["AUTHN_MICROFRONTEND_DOMAIN"].replace("{{ LMS_HOST }}", "learn.innotel.us")
        self.assertEqual(rendered, "learn.innotel.us/authn")

    def test_nothing_is_left_for_jinja_or_a_doubled_brace(self):
        """The patch is a plain string by the time Tutor sees it."""
        self.assertNotIn("{{", self.caddy)
        self.assertNotIn("{%", self.caddy)
        self.assertNotIn("{path}", self.caddy)


if __name__ == "__main__":
    unittest.main()
