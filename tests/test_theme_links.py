"""The theme's footer and Studio header link only to names that answer.

Both themes ship a footer on every LMS page and a platform strip in Studio's
header, and both used to point at hosts this deployment has retired:

  * `apps.learn.innotel.us` — no longer resolves (the learner MFEs are served
    from the LMS host now, at `/catalog/` and `/learning/`);
  * `lms.innotel.us` — answers on no zone here at all (the learner portal is
    `atheniq.courses`);
  * `learn.innotel.us/programs.html` — a 301 onto `atheniq.courses` and then a
    404, because the programs pages live on the product site;
  * `ai.lms.innotel.us/…` — a 301 onto the authoring home;
  * `studio.innotel.us` — a 301 onto `studio.atheniq.courses`.

The footer is the one element on every page, so a retired host there is a dead
end one click from anywhere. These checks are textual and offline: they assert
the templates name the addresses the platform serves, and that the two theme
copies link the same places.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
THEMES = ("atheniq-theme", "openedx-theme-unity")

#: Hosts that do not answer, or answer only with a redirect somewhere else.
RETIRED = (
    "apps.learn.innotel.us",
    "lms.innotel.us",
    "ai.lms.innotel.us",
    "learn.innotel.us",
    "studio.innotel.us",
)

#: Where each footer entry goes, and why that is the right address.
FOOTER_TARGETS = {
    "Course catalog": "https://atheniq.courses/catalog/",
    "My courses": "https://atheniq.courses/learning/",
    "Programs": "https://atheniq.institute/#programs",
    "Platform Services": "https://ai.atheniq.courses/programs.html",
    "Studio": "https://studio.atheniq.courses/",
}

LINK_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
LABEL_RE = re.compile(r"\$\{_\(\s*'([^']+)'\s*\)\}")


def theme_file(theme: str, relative: str) -> pathlib.Path:
    return ROOT / "contrib" / theme / relative


def markup(text: str) -> str:
    """The template without its `##` comments.

    The comments explain which hosts were retired, so they name them; only what
    the page renders is what a reader can click.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("##"))


def links(text: str):
    """Every `(href, label)` in a template, with Mako's `_()` unwrapped."""
    found = []
    for href, inner in LINK_RE.findall(markup(text)):
        match = LABEL_RE.search(inner)
        label = match.group(1) if match else inner.strip()
        found.append((href, label))
    return found


class FooterLinks(unittest.TestCase):
    def setUp(self):
        self.footers = {theme: theme_file(theme, "lms/templates/footer.html")
                        for theme in THEMES}

    def test_no_footer_links_a_retired_host(self):
        for theme, path in self.footers.items():
            rendered = markup(path.read_text())
            for host in RETIRED:
                with self.subTest(theme=theme, host=host):
                    self.assertNotIn(host, rendered)

    def test_each_entry_is_where_the_platform_serves_it(self):
        for theme, path in self.footers.items():
            found = {label: href for href, label in links(path.read_text())}
            for label, href in FOOTER_TARGETS.items():
                with self.subTest(theme=theme, entry=label):
                    self.assertEqual(found.get(label), href)

    def test_the_two_theme_copies_link_the_same_places(self):
        """Two copies of one theme, so a fix in one has to reach the other."""
        first, second = (links(self.footers[theme].read_text()) for theme in THEMES)
        self.assertEqual(first, second)


class StudioHeaderLinks(unittest.TestCase):
    def setUp(self):
        self.headers = {theme: theme_file(theme, "cms/templates/widgets/header.html")
                        for theme in THEMES}

    def test_the_platform_entry_opens_the_console(self):
        for theme, path in self.headers.items():
            with self.subTest(theme=theme):
                self.assertIn('href="https://ai.atheniq.courses/programs.html"',
                              path.read_text())

    def test_the_learner_entry_opens_the_lms(self):
        for theme, path in self.headers.items():
            with self.subTest(theme=theme):
                self.assertIn('href="https://atheniq.courses/"', path.read_text())

    def test_no_header_links_a_retired_host(self):
        for theme, path in self.headers.items():
            rendered = markup(path.read_text())
            for host in RETIRED:
                with self.subTest(theme=theme, host=host):
                    self.assertNotIn(host, rendered)

    def test_the_two_theme_copies_link_the_same_places(self):
        for theme, path in self.headers.items():
            with self.subTest(theme=theme):
                self.assertEqual(
                    [href for href, _ in links(path.read_text())
                     if href.startswith("https://")],
                    ["https://ai.atheniq.courses/programs.html",
                     "https://atheniq.courses/"])


if __name__ == "__main__":
    unittest.main()
