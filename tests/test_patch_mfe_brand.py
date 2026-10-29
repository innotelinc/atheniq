"""The MFE brand patch, checked against the shapes the bundles actually use.

The patch rewrites *compiled* assets, so the only thing worth testing is that
each rule recognizes the code it was written for and that the rewrite cannot
reach anything else: an i18n table, a `defaultMessage`, an exact literal, and
the Studio home's action list. The identifier cases are here because "edX" is a
substring of `movedXBlockParams` — a replacement that ignores that would rename
a reducer.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "patch-mfe-brand.py"
_spec = importlib.util.spec_from_file_location("patch_mfe_brand", _MODULE_PATH)
brand = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brand)


def patch(text, app="authoring"):
    counts = brand.Counter()
    return brand.patch_text(text, app, counts), counts


class Copy(unittest.TestCase):
    def test_a_locale_table_loses_the_product_name(self):
        source = '{"header.user.menu.studio":"Studio Home","footer.logo.altText":"Powered by Open edX"}'
        result, counts = patch(source)
        self.assertNotIn("edX", result)
        self.assertNotIn("Studio Home", result)
        self.assertIn('"header.user.menu.studio":"AthenIQ Studio"', result)
        self.assertIn('"footer.logo.altText":"AthenIQ"', result)
        # Both keys are set outright, so they are counted per key rather than as
        # token replacements.
        self.assertEqual(counts["key:header.user.menu.studio"], 1)
        self.assertEqual(counts["key:footer.logo.altText"], 1)

    def test_the_heading_is_the_product_not_a_short_name(self):
        source = 'headingTitle:{id:"course-authoring.studio-home.heading.title",defaultMessage:"{studioShortName} home"}'
        result, _ = patch(source)
        self.assertIn('defaultMessage:"AthenIQ Studio"', result)

    def test_the_trademark_notice_is_removed_rather_than_translated(self):
        source = 'defaultMessage:"edX and Open edX are registered trademarks of edX LLC."'
        result, counts = patch(source)
        self.assertEqual(result, 'defaultMessage:""')
        self.assertEqual(counts["trademark-notices"], 1)

    def test_a_double_escaped_locale_value_is_still_branded(self):
        # These sit inside JSON.parse('…'), where the value is escaped twice and
        # the table matcher stops early; the literal rule is what reaches them.
        source = ('JSON.parse(\'{"footer.socialLinks.srText.facebook":'
                  '"Поставить \\\\\\"Нравится\\\\\\" edX на Facebook"}\')')
        result, _ = patch(source)
        self.assertNotIn("edX", result)
        self.assertIn("AthenIQ на Facebook", result)

    def test_an_identifier_that_contains_the_name_is_left_alone(self):
        source = 'movedXBlockParams:{isSuccess:!1},blockType:"advancedXBlock"'
        result, _ = patch(source)
        self.assertEqual(result, source)

    def test_a_footer_link_points_at_this_platform(self):
        source = 'href:"https://open.edx.org",title:"Open edX"'
        result, counts = patch(source)
        self.assertNotIn("edx.org", result)
        self.assertIn('title:"AthenIQ"', result)
        self.assertEqual(counts["edx-links"], 1)


class StudioHome(unittest.TestCase):
    ANCHOR = brand.HOME_ACTIONS_ANCHOR

    def test_the_two_stock_buttons_become_four_create_actions(self):
        result, counts = patch("f();" + self.ANCHOR + ";g()")
        self.assertEqual(counts["home-actions"], 1)
        self.assertNotIn(self.ANCHOR, result)
        for label, href in brand.CREATE_ACTIONS:
            self.assertIn(f'children:"{label}"', result)
            self.assertIn(f'href:"{href}"', result)
        # The stock labels are gone, not merely supplemented.
        self.assertNotIn("addNewCourseBtnText", result)
        self.assertNotIn("addNewLibraryBtnText", result)

    def test_the_rewrite_keeps_the_program_shape(self):
        # The first version of this patch replaced the course and library pushes
        # together and swallowed the `){` between them: the bundle stopped
        # parsing and the page rendered nothing. Delimiters are the invariant.
        source = "if(a&&f()," + self.ANCHOR + ",b&&!c||c&&d){const t=()=>{i(!0)};" \
                 + brand.HOME_LIBRARY_ANCHOR + "}"
        result, counts = patch(source)
        self.assertEqual(brand.imbalance(result), brand.imbalance(source))
        self.assertEqual(counts["home-library-button"], 1)
        self.assertIn("const t=()=>{i(!0)};", result)
        self.assertNotIn("addNewLibraryBtnText", result)

    def test_a_patched_bundle_is_not_patched_twice(self):
        once, _ = patch("x;" + self.ANCHOR)
        twice, counts = patch(once)
        self.assertEqual(once, twice)
        self.assertEqual(counts.get("home-actions", 0), 0)
        self.assertIn(brand.HOME_MARKER, once)

    def test_another_app_does_not_get_the_authoring_actions(self):
        result, counts = patch("x;" + self.ANCHOR, app="learning")
        self.assertEqual(result, "x;" + self.ANCHOR)
        self.assertEqual(counts.get("home-actions", 0), 0)


class OnDisk(unittest.TestCase):
    """The filesystem path: the rules above are only worth anything if written.

    A stray early return once made the script exit 1 without touching a single
    file, which no test of `patch_text` could have caught.
    """

    def setUp(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp()) / "authoring"
        self.dir.mkdir()
        (self.dir / "index.html").write_text(
            "<html><head><title>Course Authoring |</title></head></html>", encoding="utf-8")
        (self.dir / "app.deadbeef.js").write_text(
            '"header.user.menu.studio":"Studio Home",' + brand.HOME_ACTIONS_ANCHOR
            + ",x&&y){const t=()=>{i(!0)};" + brand.HOME_LIBRARY_ANCHOR + "}",
            encoding="utf-8")
        (self.dir / "app.deadbeef.css").write_text(".btn{color:red}", encoding="utf-8")

    def test_it_writes_every_rule_to_disk(self):
        code = brand.main([str(self.dir), "--app", "authoring"])
        self.assertEqual(code, 0)
        html = (self.dir / "index.html").read_text(encoding="utf-8")
        js = (self.dir / "app.deadbeef.js").read_text(encoding="utf-8")
        css = (self.dir / "app.deadbeef.css").read_text(encoding="utf-8")
        self.assertIn("<title>AthenIQ Studio</title>", html)
        self.assertIn('"header.user.menu.studio":"AthenIQ Studio"', js)
        self.assertIn(brand.HOME_MARKER, js)
        self.assertEqual(brand.imbalance(js), brand.imbalance(
            ',x&&y){const t=()=>{i(!0)};}'.replace("}", "}")))
        self.assertIn(brand.STUDIO_CSS, css)

    def test_the_unity_skin_is_installed_and_linked(self):
        css_dir = Path(__file__).resolve().parents[1] / "contrib" / "atheniq-theme" / "mfe"
        code = brand.main([str(self.dir), "--app", "authoring", "--unity-css", str(css_dir)])
        self.assertEqual(code, 0)
        skin = (self.dir / "atheniq-unity.css").read_text(encoding="utf-8")
        dark = (self.dir / "atheniq-unity-dark.css").read_text(encoding="utf-8")
        canonical = (css_dir / "unity-light.css").read_text(encoding="utf-8")
        # The installed copy is the canonical skin plus importance on its tokens:
        # Paragon mounts its own stylesheet after ours, so a tie loses.
        self.assertEqual(skin, brand.harden(canonical))
        self.assertIn("--pgn-color-primary-base: #5f3fe6 !important;", skin)
        self.assertEqual(dark, brand.harden((css_dir / "unity-dark.css").read_text(encoding="utf-8")))
        html = (self.dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('/authoring/atheniq-unity.css', html)
        self.assertIn('/authoring/atheniq-unity-dark.css', html)
        self.assertIn("prefers-color-scheme: dark", html)

    def test_a_second_run_changes_nothing(self):
        brand.main([str(self.dir), "--app", "authoring"])
        before = {p.name: p.read_text(encoding="utf-8") for p in self.dir.iterdir()}
        self.assertEqual(brand.main([str(self.dir), "--app", "authoring"]), 0)
        after = {p.name: p.read_text(encoding="utf-8") for p in self.dir.iterdir()}
        # The css marker is the one thing appending twice would duplicate.
        self.assertEqual(before, after)


class HeaderNav(unittest.TestCase):
    """No AthenIQ nav in a header: every list the bundles carry is emptied.

    The workspace menu, the dashboard's two learner links, and the older
    `Discover New` spelling all go to `[]`, because the list is what the header
    renders and a nav nobody asked for is not left behind on the page.
    """

    def test_the_five_workspace_links_become_an_empty_list(self):
        source = 'p=' + brand.sections_literal(brand.PLATFORM_SECTIONS) + ',b=()=>1'
        result, counts = patch(source, app="learner-dashboard")
        self.assertEqual(counts["header-nav"], 1)
        self.assertEqual(result, "p=[],b=()=>1")
        for gone in ("programs.html", "index.html", "studio.innotel.us", "platform.html"):
            self.assertNotIn(gone, result)

    def test_every_app_loses_the_workspace_nav(self):
        source = 'p=' + brand.sections_literal(brand.PLATFORM_SECTIONS)
        for app in ("learning", "learner-dashboard", "authoring"):
            result, counts = patch(source, app=app)
            self.assertEqual(result, "p=[]")
            self.assertEqual(counts.get("header-nav", 0), 1)

    def test_each_learner_array_the_dashboard_shipped_is_removed(self):
        """`Discover New`, `Catalogue` and `Catalog` are all the same nav."""
        self.assertEqual(len(brand.LEGACY_LEARNER_ANCHORS), 3)
        for shipped in brand.LEGACY_LEARNER_ANCHORS:
            source = "p=" + shipped
            result, counts = patch(source, app="learner-dashboard")
            self.assertEqual(result, "p=[]")
            self.assertEqual(counts["header-nav"], 1)
            self.assertNotIn("innotel.us/", result)

    def test_an_empty_list_is_already_what_the_header_carries(self):
        """Idempotent: a second pass over an emptied array is a no-op."""
        source = "p=[]"
        result, counts = patch(source, app="learner-dashboard")
        self.assertEqual(result, source)
        self.assertEqual(counts.get("header-nav", 0), 0)


class HeaderMenu(unittest.TestCase):
    """The top of the dashboard: Courses and Discover New, and nothing else.

    `mainMenu` is built from three spreads — Courses, Programs, Discover New —
    and `secondaryMenu` from Help. The two flagged ones become `[]`, so the
    array literal keeps its shape and the header draws the two that stay.
    """

    PROGRAMS = ('...(0,m.zj)().ENABLE_PROGRAMS?[{type:"item",href:`${rs.programsUrl()}`,'
                'content:e($l.program)}]:[]')
    HELP = ('...(0,m.zj)().SUPPORT_URL?[{type:"item",href:`${(0,m.zj)().SUPPORT_URL}`,'
            'content:e($l.help)}]:[]')

    def test_programs_goes_and_the_array_stays_an_array(self):
        source = 'mainMenu:[{type:"item",href:"/",content:e($l.course),isActive:!0},' \
                 + self.PROGRAMS + '],secondaryMenu:[' + self.HELP + ']'
        result, counts = patch(source, app="learner-dashboard")
        self.assertEqual(counts["header-menu"], 2)
        self.assertIn('mainMenu:[{type:"item",href:"/",content:e($l.course),'
                      'isActive:!0},...[]]', result)
        self.assertIn("secondaryMenu:[...[]]", result)
        for gone in ("programsUrl", "$l.program", "$l.help"):
            self.assertNotIn(gone, result)

    def test_the_account_menu_is_emptied_whole(self):
        """Profile, account, order history and sign out: the array goes."""
        source = ('userMenu:[{heading:"",items:[{type:"item",href:`${(0,m.zj)().ACCOUNT_PROFILE_URL}`,'
                  'content:e($l.profile)},...(0,m.zj)().ORDER_HISTORY_URL?[{type:"item",'
                  'href:(0,m.zj)().ORDER_HISTORY_URL,content:e($l.orderHistory)}]:[]]},'
                  '{heading:"",items:[{type:"item",href:`${(0,m.zj)().LOGOUT_URL}`,'
                  'content:e($l.signOut)}]}]}))(n,e,r,a)')
        result, counts = patch(source, app="learner-dashboard")
        self.assertEqual(counts["header-account-menu"], 1)
        self.assertEqual(result, "userMenu:[]}))(n,e,r,a)")
        for gone in ("$l.profile", "$l.orderHistory", "$l.signOut", "LOGOUT_URL"):
            self.assertNotIn(gone, result)

    def test_an_already_empty_account_menu_is_not_a_change(self):
        source = 'userMenu:[]}))(n,e,r,a)'
        result, counts = patch(source, app="learner-dashboard")
        self.assertEqual(result, source)
        self.assertNotIn("header-account-menu", counts)

    def test_another_app_keeps_its_account_menu(self):
        source = 'userMenu:[{heading:"",items:[{type:"item",href:"x",content:e($l.signOut)}]}]'
        self.assertEqual(patch(source, app="authoring")[0], source)

    def test_another_app_keeps_its_menu(self):
        source = 'mainMenu:[' + self.PROGRAMS + ']'
        self.assertEqual(patch(source, app="authoring")[0], source)

    def test_the_console_links_follow_the_console_to_its_new_name(self):
        """The create actions open the console on the atheniq.courses zone.

        `ai.lms.innotel.us` redirects to the authoring home now, so a button
        still pointing at it would bounce the author straight back.
        """
        source = 'r.push({href:"https://ai.lms.innotel.us/course-create.html"})'
        result, counts = patch(source, app="authoring")
        self.assertEqual(result, 'r.push({href:"https://ai.atheniq.courses/course-create.html"})')
        self.assertEqual(counts["console-url"], 1)
        self.assertIn("https://ai.atheniq.courses/", brand.WORKSPACE)

    def test_the_nav_is_still_matched_on_the_old_name(self):
        """The rewrite runs last: the nav anchors hold the name it replaces."""
        result, counts = patch("p=" + brand.sections_literal(brand.PLATFORM_SECTIONS),
                               app="learner-dashboard")
        self.assertEqual(result, "p=[]")
        self.assertEqual(counts["header-nav"], 1)

    def test_a_second_pass_has_nothing_left_to_reduce(self):
        source = 'secondaryMenu:[' + self.HELP + ']'
        once, _ = patch(source, app="learner-dashboard")
        twice, counts = patch(once, app="learner-dashboard")
        self.assertEqual(twice, once)
        self.assertNotIn("header-menu", counts)


class Dashboard(unittest.TestCase):
    """The dashboard's address is `/dashboard`, and it carries one link.

    The public path is baked in the bundle in three places — frontend-platform's
    `PUBLIC_PATH` (which is the router's basename), webpack's
    `__webpack_public_path__`, and the shell's script tags — and the app id is
    the same word without a slash, so the rewrite has to be by path.
    """

    def test_the_public_path_moves_and_takes_the_basename_with_it(self):
        source = 'BASE_URL:"",PUBLIC_PATH:"/learner-dashboard/",APP_ID:"learner-dashboard"'
        result, counts = patch(source, app="learner-dashboard")
        self.assertIn('PUBLIC_PATH:"/dashboard/"', result)
        self.assertEqual(counts["dashboard-path"], 1)

    def test_the_webpack_public_path_moves(self):
        source = 'a.p="/learner-dashboard/"'
        result, _ = patch(source, app="learner-dashboard")
        self.assertEqual(result, 'a.p="/dashboard/"')

    def test_the_app_id_is_not_a_path(self):
        """`APP_ID` and the i18n namespace name the app, not where it sits."""
        source = '{APP_ID:"learner-dashboard",all:["learner-dashboard"]}'
        result, counts = patch(source, app="learner-dashboard")
        self.assertEqual(result, source)
        self.assertEqual(counts.get("dashboard-path", 0), 0)

    def test_another_app_keeps_its_path(self):
        source = 'PUBLIC_PATH:"/learner-dashboard/"'
        result, _ = patch(source, app="learning")
        self.assertEqual(result, source)

    def test_the_dark_mode_switch_is_turned_off_at_its_flag(self):
        """Both shapes the app uses: `const e=` and a bare assignment."""
        source = ('const e=(0,s.zj)().INDIGO_ENABLE_DARK_TOGGLE;'
                  'm=(0,r.zj)().INDIGO_ENABLE_DARK_TOGGLE;')
        result, counts = patch(source, app="learner-dashboard")
        self.assertEqual(result, "const e=(!1);m=(!1);")
        self.assertEqual(counts["dashboard-dark-toggle"], 2)

    def test_another_app_keeps_the_switch(self):
        source = 'const e=(0,s.zj)().INDIGO_ENABLE_DARK_TOGGLE;'
        self.assertEqual(patch(source, app="learning")[0], source)


class DashboardOnDisk(unittest.TestCase):
    """Written, not just computed: the shell and the link are files."""

    def setUp(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp()) / "learner-dashboard"
        self.dir.mkdir()
        (self.dir / "index.html").write_text(
            '<html><head><script defer="defer" '
            'src="/learner-dashboard/runtime.deadbeef.js"></script></head>'
            '<body><div id="root"></div></body></html>', encoding="utf-8")
        (self.dir / "runtime.deadbeef.js").write_text(
            'a.p="/learner-dashboard/";', encoding="utf-8")
        (self.dir / "app.deadbeef.js").write_text(
            'PUBLIC_PATH:"/learner-dashboard/",APP_ID:"learner-dashboard";', encoding="utf-8")

    def test_the_shell_asks_for_its_scripts_at_the_new_address(self):
        self.assertEqual(brand.main([str(self.dir), "--app", "learner-dashboard"]), 0)
        html = (self.dir / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("/learner-dashboard/", html)
        self.assertIn("/dashboard/runtime.deadbeef.js", html)
        self.assertIn('a.p="/dashboard/"', (self.dir / "runtime.deadbeef.js").read_text())

    def test_the_stylesheet_asks_for_its_files_at_the_new_address(self):
        (self.dir / "app.deadbeef.css").write_text(
            '@font-face{src:url("/learner-dashboard/font.woff2")}', encoding="utf-8")
        self.assertEqual(brand.main([str(self.dir), "--app", "learner-dashboard"]), 0)
        css = (self.dir / "app.deadbeef.css").read_text(encoding="utf-8")
        self.assertIn("/dashboard/font.woff2", css)
        self.assertNotIn("/learner-dashboard/", css)

    def test_the_institute_pill_is_taken_out_of_the_shell(self):
        shell = self.dir / "index.html"
        html = shell.read_text(encoding="utf-8")
        pill = ('<div id="atheniq-institute" style="max-width:1240px">'
                '<a href="https://atheniq.institute/" target="_blank" rel="noopener" '
                'data-atheniq="institute">AthenIQ Institute'
                '<span aria-hidden="true">&#8599;</span></a></div>')
        shell.write_text(html.replace("</body>", pill + "</body>"), encoding="utf-8")
        self.assertEqual(brand.main([str(self.dir), "--app", "learner-dashboard"]), 0)
        cleaned = shell.read_text(encoding="utf-8")
        self.assertNotIn("atheniq-institute", cleaned)
        self.assertNotIn('data-atheniq="institute"', cleaned)
        # The header rule for the duplicate logo keeps its selector: only the
        # pill in the body is removed.
        self.assertIn('a.logo[href*="atheniq.institute"]', cleaned)
        # The root element and the closing body survive the removal.
        self.assertIn('<div id="root"></div></body>', cleaned)
        # A second pass is a no-op: the pill is page markup, not a rewrite.
        self.assertEqual(brand.main([str(self.dir), "--app", "learner-dashboard"]), 0)
        self.assertEqual(shell.read_text(encoding="utf-8"), cleaned)

    def test_the_stock_wordmark_is_hidden_in_the_shell(self):
        """Header = the AthenIQ logo, Courses, Discover New — nothing else."""
        self.assertEqual(brand.main([str(self.dir), "--app", "learner-dashboard"]), 0)
        html = (self.dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="atheniq-header"', html)
        self.assertIn('a.logo[title="Open edX"]', html)
        # One logo: the copy linking to the institute goes, the home one stays.
        self.assertIn('a.logo[href*="atheniq.institute"]', html)
        # The AthenIQ logo is a different anchor and is deliberately not touched.
        self.assertNotIn('title="AthenIQ"]{display:none', html)
        self.assertEqual(brand.main([str(self.dir), "--app", "learner-dashboard"]), 0)
        self.assertEqual((self.dir / "index.html").read_text(encoding="utf-8"), html)

    def test_the_skin_is_linked_from_the_address_the_app_is_served_at(self):
        css_dir = Path(__file__).resolve().parents[1] / "contrib" / "atheniq-theme" / "mfe"
        code = brand.main([str(self.dir), "--app", "learner-dashboard",
                           "--unity-css", str(css_dir)])
        self.assertEqual(code, 0)
        html = (self.dir / "index.html").read_text(encoding="utf-8")
        self.assertIn("/dashboard/atheniq-unity.css", html)
        self.assertIn("/dashboard/atheniq-unity-dark.css", html)

    def test_a_bundle_that_still_names_the_old_path_fails_the_run(self):
        """A half-moved dashboard renders nothing; the run must not say it is done."""
        (self.dir / "chunk.deadbeef.js").write_text(
            'fetch("/learner-dashboard/programs.json")', encoding="utf-8")
        self.assertEqual(brand.main([str(self.dir), "--app", "learner-dashboard"]), 0)
        self.assertNotIn("/learner-dashboard/",
                         (self.dir / "chunk.deadbeef.js").read_text(encoding="utf-8"))


class Rewrite(unittest.TestCase):
    def test_tokens_are_replaced_in_order(self):
        self.assertEqual(brand.rewrite_value("Open edX (legacy)"), "AthenIQ (legacy)")
        self.assertEqual(brand.rewrite_value("Powered by Open edX"), "Powered by AthenIQ")
        self.assertEqual(brand.rewrite_value("Back to Studio Home"), "Back to AthenIQ Studio")

    def test_a_replaced_value_is_stable(self):
        once = brand.rewrite_value("edX and Open edX")
        self.assertEqual(brand.rewrite_value(once), once)


if __name__ == "__main__":
    unittest.main()
