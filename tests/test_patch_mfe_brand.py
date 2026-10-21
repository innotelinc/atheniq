"""The MFE brand patch, checked against the shapes the bundles actually use.

The patch rewrites *compiled* assets, so the only thing worth testing is that
each rule recognises the code it was written for and that the rewrite cannot
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

    def test_a_second_run_changes_nothing(self):
        brand.main([str(self.dir), "--app", "authoring"])
        before = {p.name: p.read_text(encoding="utf-8") for p in self.dir.iterdir()}
        self.assertEqual(brand.main([str(self.dir), "--app", "authoring"]), 0)
        after = {p.name: p.read_text(encoding="utf-8") for p in self.dir.iterdir()}
        # The css marker is the one thing appending twice would duplicate.
        self.assertEqual(before, after)


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
