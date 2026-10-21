#!/usr/bin/env python3
"""patch-mfe-brand.py — take the Open edX product names out of the compiled MFEs.

The authoring app and the learner apps ship their copy inside compiled bundles:
there is no template to edit and no runtime hook that can change a string. The
strings that matter live in the bundles' i18n tables (`"key":"value"` pairs per
locale, and `defaultMessage:"…"` descriptors in the source language), which are
*data* — rewriting values there changes what a page says without touching the
code that says it.

Two kinds of edit happen here.

1. **Copy.** Every i18n value is rewritten token by token: `Open edX` and `edX`
   become `AthenIQ`, `Studio Home` becomes `AthenIQ Studio`, and the trademark
   notices — which name a company that no longer has anything to do with this
   deployment — are emptied. A handful of keys are set outright because a token
   swap would read badly (`footer.logo.altText`, the Studio heading).

2. **One structural edit, in the authoring app only.** The Studio home's
   `PageHeader` builds its actions array in the bundle, and it builds exactly
   two buttons: `+ New course` and `+ New library`. Programs and classrooms are
   created in the AthenIQ workspace, and the page offers no way to reach them.
   The anchor below replaces those two pushes with four anchors — the same
   actions, in the same place, on the page where somebody is about to create
   something.

Both are pinned to the bundle they were written against, so every anchor is
**required**: if a rule matches nothing, the build fails and says which one. A
silent no-op is how a deployment ends up claiming a brand it does not show.

Usage:
    python3 scripts/patch-mfe-brand.py DIST_DIR [--report] [--app authoring]

DIST_DIR is an app's built dist (`/openedx/dist/authoring`), as the MFE image
holds it. Idempotent: a second run finds the AthenIQ copy already in place and
changes nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

#: The workspace every create action opens. One constant so the four buttons
#: cannot drift from the pages they name.
WORKSPACE = "https://ai.lms.innotel.us/"

#: The four create actions, in the order the platform offers them.
CREATE_ACTIONS = (
    ("+ New Program", WORKSPACE + "programs.html"),
    ("+ New Course", WORKSPACE + "course-create.html"),
    ("+ New Classroom", WORKSPACE + "classroom-create.html"),
    ("+ New Library", WORKSPACE + "library.html"),
)

#: Sentences that name edX as the owner of the platform. Emptied rather than
#: translated: no sentence about edX belongs on an AthenIQ page.
SENTENCE_RULES = (
    "edX and Open edX are registered trademarks of edX LLC.",
    "edX and Open edX, and the edX and Open edX logos are registered trademarks of edX Inc.",
    "edX and Open edX, and the edX and Open edX logos are registered trademarks of edX LLC.",
    "edX, Open edX, and the edX and Open edX logos are trademarks of edX Inc.",
    # The translated copies of the notice are truncated mid-sentence (no “LLC.”),
    # so they have to be matched on their own wording.
    "edX and Open edX, and the edX and Open edX logos are registered trademarks of",
)

#: Links the stock footers point at edX. They are not text, but a hover tooltip
#: that says “edx.org” is the same claim as a logo, so they are repointed.
#:
#: Literal fragments outside the i18n tables: the stock logo's alt/title text,
#: the help HTML compiled into the advanced-problem editors, and two localised
#: strings that sit inside a `JSON.parse('…')` literal, where the value is
#: double-escaped and the table matcher cannot see the end of it. Each one is an
#: exact string, so none of them can touch an identifier like `movedXBlockParams`.
STRING_RULES = (
    ('title:"Open edX"', 'title:"AthenIQ"'),
    # The app shell's <title>. It is the one piece of copy a tab shows, and it
    # still named the stock product.
    ("Course Authoring |", "AthenIQ Studio"),
    ("Course Authoring", "AthenIQ Studio"),
    ('alt:"Open edX"', 'alt:"AthenIQ"'),
    ("Building and Running an Open edX Course", "Authoring an AthenIQ Course"),
    ("Open edX Developer\\'s Guide", "AthenIQ Developer Guide"),
    ("studio.edx.org", "studio.innotel.us"),
    ("edX grading system", "AthenIQ grading system"),
    ("edX на Facebook", "AthenIQ на Facebook"),
    ("ב-edX", "ב-AthenIQ"),
)

URL_RULES = (
    ("https://open.edx.org", WORKSPACE.rstrip("/")),
    ("https://www.edx.org", "https://learn.innotel.us"),
)

#: Keys whose whole value is set, because a token swap would leave them odd.
KEY_RULES = {
    # The Studio home heading is "{studioShortName} home" — "Studio home" in
    # practice, and "Studio Home" in the user menu. One product name.
    "course-authoring.studio-home.heading.title": "AthenIQ Studio",
    "header.user.menu.studio": "AthenIQ Studio",
    # The stock create buttons are replaced by the four actions below, but the
    # labels stay meaningful for anything that still renders them.
    "course-authoring.studio-home.add-new-course.btn.text": "+ New Course",
    "course-authoring.studio-home.add-new-library.btn.text": "+ New Library",
    "studio-home.legacy-libraries.migrate.create-button": "+ New Library",
    # A logo's alt text is read aloud and shown on hover; it is not a label for
    # the platform any more.
    "footer.logo.altText": "AthenIQ",
    "footer.logo.ariaLabel": "AthenIQ",
    # The trademark sentence names a company this deployment has nothing to do
    # with; it goes rather than being rewritten.
    "footer.trademark.notice": "",
    "authoring.footer.trademark.message": "",
}

#: Token rules, applied in this order to every i18n value. Longest first: "Open
#: edX" must not be become "Open AthenIQ" by the shorter rule.
TOKEN_RULES = (
    ("Open edX", "AthenIQ"),
    ("Studio Home", "AthenIQ Studio"),
    ("Studio home", "AthenIQ Studio"),
    ("edX", "AthenIQ"),
    # A value that points at the edX site should point at this platform.
    ("edx.org", "learn.innotel.us"),
)

#: The Studio home's action list, exactly as the bundle builds it. `p` gates the
#: course button on the permission to create a course; `C`/`j`/`D` pick between
#: the v1 and v2 library flows. Those gates are dropped on purpose: the four
#: actions are links to the workspace, which enforces its own permissions, and a
#: missing program link on a page that is about creating things is the bug.
#: The two pushes are replaced one at a time, and neither replacement touches the
#: braces around them: the stock code is
#: `if(email, roles, p && push(new course), library flag) { const t = …; push(new
#: library) }`, so a replacement that swallowed the `){` would leave the file
#: unparsable. `p &&` still gates the new row on the permission to create.
HOME_ACTIONS_ANCHOR = (
    'p&&r.push((0,yi.jsx)(gt.Ay,{variant:"outline-primary",iconBefore:kt.A,size:"sm",'
    'disabled:d,onClick:()=>f(!0),children:e.formatMessage(KM.addNewCourseBtnText)}))'
)

#: The stock library button; its whole block body stays, minus the push.
HOME_LIBRARY_ANCHOR = (
    'r.push((0,yi.jsx)(gt.Ay,{variant:"outline-primary",iconBefore:kt.A,size:"sm",'
    'onClick:t,children:e.formatMessage(KM.addNewLibraryBtnText)}))'
)

#: The replacement keeps the enclosing `(e||[])` shape: `r` is the actions
#: array, `yi.jsx` the runtime every other element in this file uses. Inline
#: styles because the MFE's own stylesheet has no button class that is
#: guaranteed to exist for an anchor.
HOME_MARKER = '"data-atheniq":"home-actions"'

HOME_ACTION_STYLE = (
    '{padding:"6px 12px",marginRight:"8px",border:"1px solid currentColor",'
    'borderRadius:"6px",textDecoration:"none",fontWeight:"600",whiteSpace:"nowrap"}'
)


def _home_actions_js() -> str:
    # `data-atheniq` is the marker: the idempotence check looks for it, so a
    # second run on an already-patched bundle is a no-op rather than a failure.
    pushes = "".join(
        f'r.push((0,yi.jsx)("a",{{href:"{href}","data-atheniq":"home-actions",'
        f'style:{HOME_ACTION_STYLE},children:"{label}"}}));'
        for label, href in CREATE_ACTIONS
    )
    return 'p&&(()=>{' + pushes + "})()"


#: i18n value pairs: a dotted key (the i18n namespaces all use dots) mapped to a
#: JSON string. The value matcher is escape-aware so a value with a quote in it
#: is replaced whole rather than cut in half.
PAIR_RE = re.compile(r'"([A-Za-z0-9][A-Za-z0-9._-]*)":"((?:\\.|[^"\\])*)"')
DEFAULT_MESSAGE_RE = re.compile(r'defaultMessage:"((?:\\.|[^"\\])*)"')
DESCRIPTION_RE = re.compile(r'description:"((?:\\.|[^"\\])*)"')
#: react-intl descriptors carry their key and source-language text together:
#: `{id:"…",defaultMessage:"…"}`. A key rule has to reach this form as well as
#: the locale tables, or the same label reads differently in English.
DESCRIPTOR_RE = re.compile(r'id:"([A-Za-z0-9][A-Za-z0-9._-]*)",defaultMessage:"((?:\\.|[^"\\])*)"')


def rewrite_value(value: str) -> str:
    """Apply the token rules to one i18n value, idempotently."""
    for old, new in TOKEN_RULES:
        value = value.replace(old, new)
    return value


def patch_text(text: str, app: str, counts: Counter) -> str:
    """Rewrite one asset's text. `counts` accumulates per-rule match counts."""

    # Sentences first: the token rules would otherwise turn the trademark notice
    # into a sentence about AthenIQ claiming to own the edX marks.
    for sentence in SENTENCE_RULES:
        if sentence in text:
            counts["trademark-notices"] += text.count(sentence)
            text = text.replace(sentence, "")

    def pair(match: re.Match[str]) -> str:
        key, value = match.group(1), match.group(2)
        if key in KEY_RULES:
            if value != KEY_RULES[key]:
                counts[f"key:{key}"] += 1
            return f'"{key}":"{KEY_RULES[key]}"'
        new = rewrite_value(value)
        if new != value:
            counts["pair-values"] += 1
            return f'"{key}":"{new}"'
        return match.group(0)

    text = PAIR_RE.sub(pair, text)

    def descriptor(match: re.Match[str]) -> str:
        key, value = match.group(1), match.group(2)
        if key in KEY_RULES and value != KEY_RULES[key]:
            counts[f"key:{key}"] += 1
            return f'id:"{key}",defaultMessage:"{KEY_RULES[key]}"'
        return match.group(0)

    text = DESCRIPTOR_RE.sub(descriptor, text)

    def default_message(match: re.Match[str]) -> str:
        value = match.group(1)
        new = rewrite_value(value)
        if new != value:
            counts["default-messages"] += 1
            return f'defaultMessage:"{new}"'
        return match.group(0)

    text = DEFAULT_MESSAGE_RE.sub(default_message, text)
    text = DESCRIPTION_RE.sub(default_message, text)

    for old, new in STRING_RULES:
        if old in text:
            counts["literal-fragments"] += text.count(old)
            text = text.replace(old, new)

    for old, new in URL_RULES:
        if old in text:
            counts["edx-links"] += text.count(old)
            text = text.replace(old, new)

    if app == "authoring" and HOME_ACTIONS_ANCHOR in text:
        counts["home-actions"] += text.count(HOME_ACTIONS_ANCHOR)
        text = text.replace(HOME_ACTIONS_ANCHOR, _home_actions_js())
        # The stock library button is one of the four now; its push goes, its
        # enclosing block (and the callback it defines) stays.
        if HOME_LIBRARY_ANCHOR in text:
            counts["home-library-button"] += text.count(HOME_LIBRARY_ANCHOR)
            text = text.replace(HOME_LIBRARY_ANCHOR, "")

    return text


#: The MFE shell's <head>. The Unity skin goes in as two stylesheets beside it,
#: one per colour scheme: Paragon reads its palette from CSS custom properties,
#: so a stylesheet recolours every page without rebuilding a bundle.
UNITY_LINK = (
    '<link rel="stylesheet" href="{root}atheniq-unity.css" media="(prefers-color-scheme: light)">'
    '<link rel="stylesheet" href="{root}atheniq-unity-dark.css" media="(prefers-color-scheme: dark)">'
)

#: The plugin already carries a four-action row, inserted into the page banner
#: slot. On the Studio home the patched header now offers the same four, so the
#: slot copy is hidden there — one set of actions per page, and the course pages
#: that use the banner keep theirs. Scoped by the home's own class, so it cannot
#: reach any other page.
STUDIO_CSS = (
    "/* AthenIQ: the create row is in the Studio home header; hide the plugin "
    "copy there. */\n"
    "body:has(.studio-home-sub-header) .atheniq-studio-actions{display:none}\n"
)


#: A rewrite must not change the shape of the program. The structural rule swaps
#: one expression for another, so every delimiter it consumes has to come back:
#: the first version of this patch took the course and library buttons out in one
#: go and ate the `){` between them, which left a bundle a browser cannot parse.
#: The check is on the snippets, not the whole file: a token rewrite legitimately
#: changes text inside string literals (ICU placeholders live in braces), so a
#: whole-file count would fire on correct output.
DELIMITERS = "{}()[]"


def delimiters(text: str) -> dict[str, int]:
    return {char: text.count(char) for char in DELIMITERS}


def imbalance(text: str) -> tuple[int, int, int]:
    """How many braces, parentheses and brackets the snippet leaves open."""
    return (text.count("{") - text.count("}"),
            text.count("(") - text.count(")"),
            text.count("[") - text.count("]"))


def _assert_shape() -> None:
    stock = HOME_ACTIONS_ANCHOR + HOME_LIBRARY_ANCHOR
    replacement = _home_actions_js()
    if imbalance(stock) != imbalance(replacement):
        raise SystemExit(
            "patch-mfe-brand: the replacement does not close what the stock buttons "
            f"open — {imbalance(stock)} vs {imbalance(replacement)}")


_assert_shape()


def iter_assets(dist: Path):
    """The files a browser can be served: js bundles and their sourcemaps."""
    for path in sorted(dist.glob("**/*")):
        if path.suffix in (".js", ".map", ".html"):
            yield path



#: A custom-property declaration, e.g. `--pgn-color-primary-base: #5f3fe6;`.
CUSTOM_PROPERTY_RE = re.compile(r"(--[a-z0-9-]+:[^;{}]+);")


def harden(css: str) -> str:
    """Make the skin win against the theme stylesheet the MFE loads later.

    Paragon injects its own theme `<link>` when React mounts — after the static
    links in the shell — so on a tie the platform's palette would win. The
    tokens are the whole skin, so they are declared important; `!important` is
    valid on a custom property and only affects this one variable.
    """
    def declare(match: re.Match[str]) -> str:
        declaration = match.group(1)
        if "!important" in declaration:  # already hardened: leave it alone
            return match.group(0)
        return declaration + " !important;"

    return CUSTOM_PROPERTY_RE.sub(declare, css)


def install_unity(dist: Path, app: str, css_dir: Path, counts: Counter, write: bool) -> None:
    """Put the Unity skin beside the bundle and link it from the shell."""
    for name, target in (("unity-light.css", "atheniq-unity.css"),
                         ("unity-dark.css", "atheniq-unity-dark.css")):
        source = css_dir / name
        if not source.is_file():
            raise SystemExit(f"patch-mfe-brand: missing {source}")
        text = harden(source.read_text(encoding="utf-8"))
        destination = dist / target
        if not destination.is_file() or destination.read_text(encoding="utf-8") != text:
            counts[f"unity:{target}"] += 1
            if write:
                destination.write_text(text, encoding="utf-8")

    shell = dist / "index.html"
    if not shell.is_file():
        raise SystemExit(f"patch-mfe-brand: {dist} has no index.html to link the skin from")
    html = shell.read_text(encoding="utf-8")
    if "atheniq-unity.css" in html:
        return
    links = UNITY_LINK.format(root=f"/{app}/")
    if "</head>" in html:
        counts["unity:linked"] += 1
        if write:
            shell.write_text(html.replace("</head>", links + "</head>", 1), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--app", default="", help="the app name (enables its app-only rules)")
    parser.add_argument("--report", action="store_true", help="print what changed, write nothing")
    parser.add_argument("--unity-css", type=Path, default=None,
                        help="directory holding unity-light.css / unity-dark.css")
    args = parser.parse_args(argv)

    if not args.dist.is_dir():
        print(f"patch-mfe-brand: no such directory: {args.dist}", file=sys.stderr)
        return 2

    app = args.app or args.dist.name
    counts: Counter = Counter()
    edited = 0
    for path in iter_assets(args.dist):
        try:
            text = path.read_text(encoding="utf-8", errors="surrogatepass")
        except UnicodeDecodeError:
            continue
        new = patch_text(text, app, counts)
        if new != text:
            edited += 1
            if not args.report:
                path.write_text(new, encoding="utf-8", errors="surrogatepass")

    if app == "authoring":
        for sheet in sorted(args.dist.glob("*.css")):
            text = sheet.read_text(encoding="utf-8", errors="ignore")
            if STUDIO_CSS in text:
                continue
            counts["studio-css"] += 1
            if not args.report:
                sheet.write_text(text + STUDIO_CSS, encoding="utf-8")

    if args.unity_css is not None:
        install_unity(args.dist, app, args.unity_css, counts, write=not args.report)

    for label, number in sorted(counts.items()):
        print(f"  {label:28} {number}")
    print(f"patch-mfe-brand: {app}: {edited} file(s) {'would change' if args.report else 'changed'}")

    # The Studio home's four actions are the reason this script exists for the
    # authoring app; a build that did not place them has silently kept the page
    # it was meant to fix.
    if app == "authoring" and not counts.get("home-actions") \
            and not any(HOME_MARKER in a.read_text(encoding="utf-8", errors="ignore")
                        for a in iter_assets(args.dist)):
        print("patch-mfe-brand: the authoring home action list was not found — "
              "the bundle changed and the four create actions were NOT added", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
