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
        """The LMS serves its own copy; a copy that differs is a bug."""
        for name in ("light", "dark"):
            lms = (THEME / "lms" / "static" / "atheniq" / f"unity-{name}.css").read_text()
            self.assertEqual(lms, _css(name), f"unity-{name}.css differs between lms/ and mfe/")

    def test_the_footer_links_the_skin(self):
        footer = (THEME / "lms" / "templates" / "footer.html").read_text()
        for name in ("light", "dark"):
            self.assertIn(f"/theming/asset/atheniq/unity-{name}.css", footer)


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
        self.assertIn('("atheniq-theme", "build/openedx")', self.text)
        self.assertIn("ENV_TEMPLATE_ROOTS", self.text)

    def test_it_copies_them_into_the_image_and_recollects(self):
        self.assertIn('"openedx-dockerfile"', self.text)
        self.assertIn("COPY --chown=app:app ./atheniq-theme/lms/", self.text)
        # The collected copy is what a browser fetches, so it is re-collected.
        self.assertIn("collectstatic", self.text)
        self.assertIn("/openedx/themes/indigo/lms", self.text)

    def test_it_repoints_only_the_brand_override(self):
        """The compiled theme stays the `default` URL: structure is not ours."""
        self.assertIn("mfe-lms-common-settings", self.text)
        self.assertIn('_atheniq_urls["brandOverride"]', self.text)
        self.assertIn("unity-{_atheniq_variant}.css", self.text)
        self.assertNotIn('_atheniq_urls["default"]', self.text)

    def test_it_names_the_platform_as_a_default_only(self):
        self.assertIn('CONFIG_DEFAULTS.add_item(("PLATFORM_NAME", "AthenIQ"))', self.text)
        self.assertNotIn("CONFIG_OVERRIDES", self.text)

    def test_the_packaging_points_at_the_module(self):
        pyproject = (PLUGIN.parent.parent / "pyproject.toml").read_text()
        self.assertIn('atheniqtheme = "atheniqtheme.plugin"', pyproject)
        self.assertIn('"tutor.plugin.v0"', pyproject)


class HeaderLinks(unittest.TestCase):
    """The MFE plugin's nav: two learner links on the dashboard, nothing elsewhere."""

    MFE_PLUGIN = ROOT / "contrib" / "tutor-atheniq-mfe" / "atheniqmfe" / "plugin.py"

    def setUp(self):
        self.text = self.MFE_PLUGIN.read_text(encoding="utf-8")

    def test_the_dashboard_gets_two_links_and_no_workspace_menu(self):
        self.assertIn("LEARNER_SECTIONS = (", self.text)
        self.assertIn('("Courses", "https://apps.learn.innotel.us/")', self.text)
        # The catalogue is the portal: it reads the program store, so a program
        # created in the console is listed there, which the LMS catalog is not.
        self.assertIn('("Catalogue", "https://lms.innotel.us/")', self.text)
        self.assertNotIn('("Discover New"', self.text)
        # Only the dashboard renders it; every other app gets nothing at all.
        self.assertIn("path.startsWith('/learner-dashboard')", self.text)
        self.assertNotIn("ATHENIQ_SECTIONS", self.text)

    def test_the_workspace_menu_is_gone_from_the_header(self):
        for label in ("Programs", "Classrooms", "Studio", "Platform"):
            self.assertNotIn(f'("{label}", ', self.text)
        self.assertNotIn("PLATFORM_SECTIONS", self.text)
        self.assertNotIn("path.startsWith('/authoring')", self.text)

    def test_the_nav_lays_itself_out_as_a_row(self):
        """Paragon's `.nav-link` is display:block; without this the nav is a column."""
        self.assertIn("nav.atheniq-nav {{ display: flex !important;", self.text)
        self.assertIn("nav.atheniq-nav a.nav-link {{ display: inline-flex;", self.text)


class HeaderNavSkin(unittest.TestCase):
    """The skins reach every app, including bundles built before the plugin fix."""

    def test_both_skins_row_the_nav_and_drop_the_workspace_links(self):
        for name in ("unity-light.css", "unity-dark.css"):
            css = (ROOT / "contrib" / "atheniq-theme" / "mfe" / name).read_text(encoding="utf-8")
            self.assertIn("nav.atheniq-nav {", css, name)
            self.assertIn("display: flex !important;", css, name)
            self.assertIn("display: inline-flex;", css, name)
            self.assertIn('a.nav-link[href*="ai.lms.innotel.us"]', css, name)
            self.assertIn('a.nav-link[href*="studio.innotel.us"]', css, name)
            self.assertIn("display: none !important;", css, name)


if __name__ == "__main__":
    unittest.main()
