"""The AthenIQ skin: the Unity stylesheets, and the plugin that installs them.

Two things are being held honest here.

The **stylesheets** are the seam between AthenIQ and the Indigo theme underneath
it. They carry the Innotel Platform Stack's Unity palette — the family's `desk`
register, which the training range wears — and the one rule that keeps another
platform's badge off the page. Both are cheap to check and expensive to notice:
a palette that drifts, or a stylesheet that stops hiding the Open edX lockup,
is only visible by looking at the running site.

The **plugin** is what turns those files from a copy in a container into part of
the image. Its hooks are declarative, so they can be asserted without Tutor
installed: a template target that renders the overlay into the build context, a
Dockerfile patch that copies it in *and* re-collects the static assets, and a
settings patch that re-points Paragon's brand override — leaving the compiled
theme as the default URL.
"""
import os
import re
import sys
import unittest
from pathlib import Path

from _loader import ROOT

THEME = ROOT / "contrib" / "atheniq-theme"
UNITY_THEME = ROOT / "contrib" / "openedx-theme-unity"
PLUGIN = ROOT / "contrib" / "tutor-atheniq-theme" / "atheniqtheme" / "plugin.py"

#: Unity's `desk` register, from the platform stack's `standards/unity` (the
#: same block every product vendors as `theme/unity-theme.css`).
UNITY_DESK = {
    "canvas": "#f7f6fb",
    "surface_muted": "#f1effa",
    "line": "#e4e0f0",
    "ink": "#191430",
    "brand": "#5f3fe6",
}
UNITY_DESK_DARK = {
    "canvas": "#100c22",
    "ink": "#f5f3ff",
    "brand": "#9b83ff",
}


def _css(name):
    return (THEME / "mfe" / f"unity-{name}.css").read_text(encoding="utf-8")


class Stylesheets(unittest.TestCase):
    def test_light_carries_the_unity_desk_palette(self):
        css = _css("light")
        for token, value in UNITY_DESK.items():
            self.assertIn(value, css, f"{token} ({value}) is not in the light skin")

    def test_dark_carries_the_unity_dark_palette(self):
        css = _css("dark")
        for token, value in UNITY_DESK_DARK.items():
            self.assertIn(value, css, f"{token} ({value}) is not in the dark skin")

    def test_the_brand_override_uses_paragon_variables(self):
        """The MFEs paint from `--pgn-*`; anything else would be cosmetic."""
        css = _css("light")
        for variable in ("--pgn-color-primary-base", "--pgn-color-primary-500",
                         "--pgn-color-text-base", "--pgn-color-bg-base",
                         "--pgn-color-link-base"):
            self.assertIn(variable, css)

    def test_no_other_platform_signs_the_page(self):
        """The Open edX and Tutor lockups, and the hover text that is an `alt`."""
        for name in ("light", "dark"):
            css = _css(name)
            self.assertIn('img[alt="Powered by Open edX"]', css)
            self.assertIn('img[alt="Runs on Tutor"]', css)
            self.assertIn(":has(> img", css)
            self.assertIn("display: none", css)

    def test_the_mark_states_its_own_attribution(self):
        self.assertIn("AthenIQ by Innotel Labs", _css("light"))

    def test_stylesheets_are_balanced(self):
        """A stray brace or comment silently mangles everything after it."""
        for name in ("light", "dark"):
            css = _css(name)
            self.assertEqual(css.count("/*"), css.count("*/"), name)
            self.assertEqual(css.count("{"), css.count("}"), name)

    def test_the_lms_copies_do_not_drift(self):
        """The installed theme's copy and the MFE source are one file."""
        for name in ("light", "dark"):
            lms = (UNITY_THEME / "lms" / "static" / "atheniq" /
                   f"unity-{name}.css").read_text()
            self.assertEqual(lms, _css(name),
                             f"unity-{name}.css differs between the theme and mfe/")

    def test_the_head_loads_unity_before_the_first_paint(self):
        """`head-extra.html` is the one hook in the LMS `<head>`."""
        head = (UNITY_THEME / "lms" / "templates" / "head-extra.html").read_text()
        self.assertIn("/static/atheniq/unity-theme.css", head)
        self.assertIn("/static/atheniq/atheniq-lms.css", head)
        self.assertIn("/static/atheniq/unity-theme.js", head)
        self.assertIn('setAttribute("data-scheme", "desk")', head)
        # The palette has to arrive before the skin that names its tokens.
        self.assertLess(head.index("unity-theme.css"), head.index("atheniq-lms.css"))

    def test_the_footer_no_longer_links_a_late_stylesheet(self):
        """A `<link>` at the end of the body is a flash of Indigo's colours."""
        footer = (UNITY_THEME / "lms" / "templates" / "footer.html").read_text()
        self.assertNotIn("unity-light.css", footer)
        self.assertNotIn("atheniq-lms.css", footer)

    def test_the_two_halves_share_one_theme(self):
        """LMS and Studio are two apps, so two copies — byte-identical ones."""
        for name in ("unity-theme.css", "unity-theme.js"):
            self.assertEqual(
                (UNITY_THEME / "lms" / "static" / "atheniq" / name).read_bytes(),
                (UNITY_THEME / "cms" / "static" / "atheniq" / name).read_bytes(),
                f"{name} differs between the LMS and the CMS",
            )

    def test_the_vendored_theme_is_the_canonical_one(self):
        css = (UNITY_THEME / "lms" / "static" / "atheniq" / "unity-theme.css").read_text()
        self.assertIn("UNITY — the shared theme.  THE canonical copy.", css)
        # `desk` is the bare `:root`; the other two registers are scoped.
        for scheme in (':root[data-scheme="operations"]', ':root[data-scheme="soc"]'):
            self.assertIn(scheme, css)
        self.assertIn(':root[data-mode="dark"]', css)

    def test_the_lms_skin_names_tokens_not_colours(self):
        """The point of adopting Unity is that the palette lives in one file."""
        css = (UNITY_THEME / "lms" / "static" / "atheniq" / "atheniq-lms.css").read_text()
        self.assertIn("var(--brand)", css)
        self.assertIn("var(--surface)", css)
        self.assertIn("html[data-mode=\"dark\"]", css)
        self.assertNotIn("#5f3fe6", css)
        self.assertNotIn("#10b981", css)


class PlatformPages(unittest.TestCase):
    """The console and the learner portal wear Unity, not a lookalike.

    The palette in the two pages is the family's `unity-theme.css` verbatim, and
the pages' own stylesheets only *name* its tokens. That split is what makes this
adoption rather than a second palette that happens to be green today: a change to
Unity reaches these pages by replacing one file, and these tests fail the moment
the copies stop being one file.
    """

    GENERATE = ROOT / "web" / "generate"
    STUDENT = ROOT / "web" / "student"

    def test_the_two_copies_are_one_file(self):
        for name in ("unity-theme.css", "unity-theme.js"):
            self.assertEqual((self.GENERATE / name).read_bytes(),
                             (self.STUDENT / name).read_bytes(),
                             f"{name} differs between the console and the portal")

    def test_the_copy_is_the_unity_palette(self):
        css = (self.GENERATE / "unity-theme.css").read_text(encoding="utf-8")
        for value in (*UNITY_DESK.values(), *UNITY_DESK_DARK.values()):
            self.assertIn(value, css)
        # All three registers ship, which is what lets each product declare one.
        for scheme in ('data-scheme="operations"', 'data-scheme="soc"'):
            self.assertIn(scheme, css)

    def test_every_page_declares_a_scheme_and_loads_the_switch(self):
        pages = sorted(self.GENERATE.glob("*.html")) + [self.STUDENT / "index.html"]
        self.assertGreaterEqual(len(pages), 8)
        for page in pages:
            html = page.read_text(encoding="utf-8")
            self.assertIn('data-scheme="operations"', html, page.name)
            self.assertIn("unity-theme.js", html, page.name)
            self.assertLess(html.index("unity-theme.js"),
                            html.index('rel="stylesheet"'),
                            f"{page.name}: the switch must run before the first paint")

    def test_the_pages_stylesheets_bridge_rather_than_repaint(self):
        console = (self.GENERATE / "console.css").read_text(encoding="utf-8")
        portal = (self.STUDENT / "student.css").read_text(encoding="utf-8")
        for css in (console, portal):
            self.assertIn('@import url("unity-theme.css")', css)
        self.assertIn("--p-accent: var(--brand)", console)
        self.assertIn("--accent: var(--brand)", portal)
        # The retired green palette must not survive as literals.
        self.assertNotIn("#10b981", console)
        self.assertNotIn("#10b981", portal)


class Plugin(unittest.TestCase):
    """The plugin's declared hooks, read without importing Tutor."""

    def setUp(self):
        self.text = PLUGIN.read_text(encoding="utf-8")

    def test_it_ships_the_theme_files_into_the_build_context(self):
        self.assertIn('("openedx-theme-unity", "build/openedx")', self.text)
        self.assertIn("ENV_TEMPLATE_ROOTS", self.text)

    def test_it_copies_them_into_the_image_and_recollects(self):
        self.assertIn('"openedx-dockerfile"', self.text)
        self.assertIn("COPY --chown=app:app ./openedx-theme-unity/lms/", self.text)
        # The collected copy is what a browser fetches, so it is re-collected.
        self.assertIn("collectstatic", self.text)
        self.assertIn("THEME_ROOT = f\"/openedx/themes/{THEME_NAME}\"", self.text)

    def test_it_ships_the_cms_half_too(self):
        """Studio's theme is part of the image, not a hand-applied copy."""
        self.assertIn("COPY --chown=app:app ./openedx-theme-unity/cms/", self.text)
        self.assertIn("{THEME_ROOT}/cms/", self.text)

    def test_the_static_copies_are_where_the_templates_look(self):
        """`/static/atheniq/…` and `/static/studio/unity/atheniq/…` are two namespaces."""
        self.assertIn("/openedx/staticfiles/atheniq", self.text)
        # Studio collects under `studio/` and the theme's files under `unity/`.
        self.assertIn("/openedx/staticfiles/studio/unity/atheniq", self.text)
        self.assertIn("lms/static/images/", self.text)
        self.assertIn("atheniq-theme/lms/static/images/courses/", self.text)

    def test_it_sets_the_site_theme(self):
        """Unity is the default for a site with no theme row, in both apps."""
        self.assertIn('DEFAULT_SITE_THEME = "unity"', self.text)
        self.assertIn("openedx-lms-common-settings", self.text)
        self.assertIn("openedx-cms-common-settings", self.text)

    def test_it_is_no_longer_an_indigo_overlay(self):
        """Indigo is neither installed nor patched by the theme plugin."""
        self.assertNotIn("tutorindigo", self.text)
        self.assertNotIn("/openedx/themes/indigo", self.text)
        self.assertNotIn("PARAGON_THEME_URLS", self.text)

    def test_it_names_the_platform_as_a_default_only(self):
        self.assertIn('CONFIG_DEFAULTS.add_item(("PLATFORM_NAME", "AthenIQ"))', self.text)
        self.assertNotIn("CONFIG_OVERRIDES", self.text)

    def test_the_packaging_points_at_the_module(self):
        pyproject = (PLUGIN.parent.parent / "pyproject.toml").read_text()
        self.assertIn('atheniqtheme = "atheniqtheme.plugin"', pyproject)
        self.assertIn('"tutor.plugin.v0"', pyproject)


class CmsOverlay(unittest.TestCase):
    """Studio's header: Unity in the operations register, linked predictably."""

    HEADER = UNITY_THEME / "cms" / "templates" / "widgets" / "header.html"

    def setUp(self):
        self.text = self.HEADER.read_text()

    def test_it_sets_the_operations_register_before_rendering(self):
        self.assertIn('window.UNITY_DEFAULT_SCHEME = "operations"', self.text)
        self.assertIn('setAttribute("data-scheme", "operations")', self.text)

    def test_it_links_the_unhashed_served_paths(self):
        """A manifest hash would survive a `make theme` copy and serve stale CSS."""
        for name in ("unity-theme.css", "unity-cms.css", "unity-theme.js"):
            self.assertIn(f'/static/studio/unity/atheniq/{name}', self.text)
        self.assertNotIn("static.url('indigo/atheniq", self.text)

    def test_it_keeps_the_platform_entry_point(self):
        self.assertIn("AthenIQ Platform Services", self.text)
        self.assertIn("ai.lms.innotel.us/programs.html", self.text)


class ThemeScript(unittest.TestCase):
    """`make theme` outlives the container it was applied to.

    A copy in the writable layer is what `tutor local launch` throws away when
    it recreates the LMS from the image, so the script has to bake the files in.
    These assertions are about that second half, not the copy itself.
    """

    SCRIPT = ROOT / "scripts" / "apply-atheniq-theme.sh"

    def setUp(self):
        self.text = self.SCRIPT.read_text(encoding="utf-8")

    def test_it_bakes_the_copies_into_the_compose_image(self):
        self.assertIn("docker build", self.text)
        self.assertIn('-t "${image}"', self.text)
        # Built from the compose image's own reference, which is what a recreate
        # starts, not from whatever container happens to be running.
        self.assertIn("{{.Config.Image}}", self.text)
        self.assertIn("COPY --chown=app:app openedx-theme-unity/lms/ ${THEME_ROOT}/lms/", self.text)
        self.assertIn("COPY --chown=app:app openedx-theme-unity/cms/ ${THEME_ROOT}/cms/", self.text)
        self.assertIn("COPY --chown=app:app openedx-theme-unity/lms/static/atheniq/ ${STATIC_TARGET}/", self.text)
        self.assertIn("COPY --chown=app:app openedx-theme-unity/lms/static/images/ ${STATIC_TARGET}/images/", self.text)
        self.assertIn("COPY --chown=app:app openedx-theme-unity/cms/static/atheniq/ ${CMS_STATIC_TARGET}/", self.text)
        self.assertIn("COPY --chown=app:app atheniq-theme/lms/static/images/courses/", self.text)
        self.assertIn("collectstatic", self.text)

    def test_the_base_image_is_kept_and_never_stacked_on(self):
        self.assertIn('atheniq/openedx-theme-base:${tag}', self.text)
        self.assertIn('atheniq.theme.base', self.text)
        # Retagging the upstream image is the documented rollback.
        self.assertIn("docker tag ${THEME_BASE} ${THEME_IMAGE}", self.text)

    def test_the_baked_image_is_verified_before_it_is_reported(self):
        self.assertIn('docker run --rm --entrypoint /bin/sh "${image}"', self.text)
        self.assertIn("${THEME_ROOT}/lms/templates/footer.html", self.text)
        self.assertIn("${THEME_ROOT}/lms/templates/head-extra.html", self.text)
        self.assertIn("${THEME_ROOT}/cms/templates/widgets/header.html", self.text)
        self.assertIn("${STATIC_TARGET}/atheniq-lms.css", self.text)
        self.assertIn("${CMS_STATIC_TARGET}/unity-cms.css", self.text)
        self.assertIn("staticfiles/${THEME_NAME}/css", self.text)

    def test_the_cms_half_is_applied_automatically(self):
        """Studio's half travels with the same theme directory, not by hand."""
        self.assertIn("cms/templates/widgets/header.html", self.text)
        self.assertIn("CMS_CONTAINER", self.text)
        self.assertIn('docker cp "${THEME_SRC}/cms/."', self.text)
        self.assertIn("--no-restart", self.text)
        self.assertIn("--force-recreate", self.text)

    def test_no_bake_is_the_opt_out_and_says_what_it_costs(self):
        self.assertIn("--no-bake", self.text)
        self.assertIn("writable layer only", self.text)


class HeaderLinks(unittest.TestCase):
    """The MFE plugin adds no header nav at all."""

    MFE_PLUGIN = ROOT / "contrib" / "tutor-atheniq-mfe" / "atheniqmfe" / "plugin.py"

    def setUp(self):
        self.text = self.MFE_PLUGIN.read_text(encoding="utf-8")

    def test_no_learner_links_are_slotted_into_the_header(self):
        self.assertNotIn("LEARNER_SECTIONS", self.text)
        self.assertNotIn('("Courses", "https://apps.learn.innotel.us/")', self.text)
        self.assertNotIn('"https://lms.innotel.us/"', self.text)
        self.assertNotIn('("Discover New"', self.text)
        self.assertNotIn("atheniq-nav", self.text)

    def test_the_workspace_menu_is_gone_from_the_header(self):
        for label in ("Programs", "Classrooms", "Studio", "Platform"):
            self.assertNotIn(f'("{label}", ', self.text)
        self.assertNotIn("PLATFORM_SECTIONS", self.text)
        self.assertNotIn("path.startsWith('/authoring')", self.text)

    def test_the_header_slot_is_not_registered(self):
        self.assertNotIn("HEADER_SLOT", self.text)
        self.assertNotIn("HEADER_COMPONENT", self.text)
        self.assertNotIn("header_desktop_main_menu", self.text)


class Wordmark(unittest.TestCase):
    """The header wordmark opens the portal, and the plugin owns that link.

    Indigo inlines its components into `env.config.jsx` at render time, so the
    link cannot be fixed by editing `tutorindigo` in site-packages: the next
    render, or any reinstall of the theme, restores `${BASE_URL}/dashboard`.
    The plugin replaces Indigo's `custom_logo` in the `logo_slot` instead, which
    is why these assertions are about the slot registration and not the theme.
    """

    MFE_PLUGIN = ROOT / "contrib" / "tutor-atheniq-mfe" / "atheniqmfe" / "plugin.py"

    def setUp(self):
        self.text = self.MFE_PLUGIN.read_text(encoding="utf-8")

    def test_the_brand_url_is_the_portal(self):
        self.assertIn('BRAND_URL = "https://atheniq.institute"', self.text)

    def test_the_logo_is_rendered_from_the_plugin(self):
        self.assertIn("LOGO_COMPONENT", self.text)
        self.assertIn("const AthenIQLibLogo = ", self.text)
        self.assertIn("RenderWidget: AthenIQLibLogo,", self.text)

    def test_the_component_does_not_fall_back_to_the_dashboard(self):
        start = self.text.index("LOGO_COMPONENT")
        component = self.text[start:self.text.index("LOGO_SLOT_CONFIG")]
        self.assertIn("href=\"{BRAND_URL}\"", component)
        self.assertNotIn("/dashboard", component)

    def test_indigos_logo_is_hidden_and_ours_inserted(self):
        start = self.text.index("LOGO_SLOT_CONFIG")
        config = self.text[start:self.text.index("\"\"\"", start + 20)]
        self.assertIn("PLUGIN_OPERATIONS.Hide", config)
        self.assertIn("widgetId: 'custom_logo'", config)
        self.assertIn("PLUGIN_OPERATIONS.Insert", config)
        self.assertIn("id: 'atheniq_logo'", config)
        self.assertIn("DIRECT_PLUGIN", config)

    def test_every_app_indigo_styles_gets_the_override(self):
        self.assertIn('LOGO_SLOT = "logo_slot"', self.text)
        start = self.text.index("LOGO_MFES = [")
        apps = self.text[start:self.text.index("]", start)]
        # Indigo registers its logo in twelve apps, not only the six it gives a
        # footer; missing one leaves that app linking to the course list.
        for app in ("authn", "learning", "learner-dashboard", "catalog",
                    "profile", "account", "discussions", "authoring",
                    "admin-console", "communications", "gradebook", "ora-grading"):
            self.assertIn(f'"{app}"', apps)
        self.assertIn("(mfe, LOGO_SLOT, LOGO_SLOT_CONFIG)", self.text)

    def test_the_remediation_is_not_a_site_packages_patch(self):
        # The comment above LOGO_COMPONENT names the old path to explain why it
        # was abandoned; only executable lines matter here.
        code = "\n".join(line for line in self.text.splitlines()
                         if not line.lstrip().startswith("#"))
        self.assertNotIn("tutorindigo/components/ThemedLogo.jsx", code)
        self.assertNotIn("orig-logo", code)


class HeaderNavSkin(unittest.TestCase):
    """The skins reach every app, including bundles built before the plugin fix."""

    def test_both_skins_row_the_nav_and_drop_the_workspace_links(self):
        for name in ("unity-light.css", "unity-dark.css"):
            css = (ROOT / "contrib" / "atheniq-theme" / "mfe" / name).read_text(encoding="utf-8")
            # An emptied nav renders no links but is still a landmark; hidden.
            self.assertIn("nav.atheniq-nav:empty {", css, name)
            self.assertIn("nav.atheniq-nav {", css, name)
            self.assertIn("display: flex !important;", css, name)
            self.assertIn("display: inline-flex;", css, name)
            self.assertIn('a.nav-link[href*="ai.lms.innotel.us"]', css, name)
            self.assertIn('a.nav-link[href*="studio.innotel.us"]', css, name)
            self.assertIn("display: none !important;", css, name)


if __name__ == "__main__":
    unittest.main()
