#!/usr/bin/env python3
"""patch-mfe-brand.py — take the Open edX product names out of the compiled MFEs.

The authoring app and the learner apps ship their copy inside compiled bundles:
there is no template to edit and no runtime hook that can change a string. The
strings that matter live in the bundles' i18n tables (`"key":"value"` pairs per
locale, and `defaultMessage:"…"` descriptors in the source language), which are
*data* — rewriting values there changes what a page says without touching the
code that says it.

Three kinds of edit happen here.

1. **Copy.** Every i18n value is rewritten token by token: `Open edX` and `edX`
   become `AthenIQ`, `Studio Home` becomes `AthenIQ Studio`, and the trademark
   notices — which name a company that no longer has anything to do with this
   deployment — are emptied. A handful of keys are set outright because a token
   swap would read badly (`footer.logo.altText`, the Studio heading).2. **The header nav is emptied, in every app.** The learner dashboard once got
   two links (Courses, and the catalog — spelled `Catalogue` in the bundles that
   were built before the spelling was fixed) and every app once got the five-item
   workspace menu. Both lists are replaced with `[]`, so no page renders them and
   no rebuild is needed to take them out. Nothing is added back: the pages those
   links opened are reachable from the console and the dashboard itself.

3. **One structural edit, in the authoring app only.** The Studio home's
   `PageHeader` builds its actions array in the bundle, and it builds exactly
   two buttons: `+ New course` and `+ New library`. Programs and classrooms are
   created in the AthenIQ workspace, and the page offers no way to reach them.
   The anchor below replaces those two pushes with four anchors — the same
   actions, in the same place, on the page where somebody is about to create
   something.

4. **The dashboard is moved to `/dashboard`, and carries one link of its own.**
   The platform links to `/dashboard` (`student_dashboard`, every emailed course
   link, the account page) while the MFE was built with `/learner-dashboard` as
   its public path, so the app only ever rendered there and `/dashboard` had to
   redirect into it — leaving the shorter address visible for a moment and the
   app's own address in the bar. The public path is baked in three places
   (frontend-platform's `PUBLIC_PATH`, which is the router's basename; webpack's
   `__webpack_public_path__`; and the shell's script tags), so all three are
   rewritten here and the deployment serves the app at `/dashboard`. The one link
   added back to a page is at the foot of the dashboard: AthenIQ Institute, the
   institute that awards the courses.

Every anchor is pinned to the bundle it was written against, so each one is
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
#: cannot drift from the pages they name. The console answers on the
#: atheniq.courses zone now; the old `ai.lms.innotel.us` name redirects to the
#: authoring home, so a link left on it would come straight back.
WORKSPACE = "https://ai.atheniq.courses/"

#: The console's old public name, still baked into the bundles that were built
#: before the move. Rewritten last, after the header rules have matched the
#: strings those bundles actually hold (the nav arrays are anchored on it).
CONSOLE_URL_RULES = (
    ("https://ai.lms.innotel.us", "https://ai.atheniq.courses"),
)

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
#: the help HTML compiled into the advanced-problem editors, and two localized
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
#:
#: The header is the platform's. No nav is added to it — not the operator's five
#: workspace links and not the two learner links (Courses and the catalog) a
#: previous version of the env-config component slotted into the dashboard. Every
#: bundle is patched to the empty list: a learner's header carries no AthenIQ
#: menu, and the pages those links opened are reachable from the page itself.

#: The learner dashboard's address. The app name and the path it is served at are
#: not the same word: the platform and the LMS templates say `/dashboard`, the
#: MFE image was built for `/learner-dashboard`. The path is what this module
#: moves; the app name stays, because it is the id the runtime configuration is
#: fetched by (`APP_ID`, and the i18n namespace beside it).
DASHBOARD_APP = "learner-dashboard"
DASHBOARD_ROOT = "dashboard"
DASHBOARD_PATH_FROM = "/learner-dashboard/"
DASHBOARD_PATH_TO = "/dashboard/"


#: The AthenIQ Institute pill the shell used to carry under the page. It is
#: taken out: the footer names the institute, and the dashboard is a learner's
#: course list, not a place that advertises it. Matched by id so a shell that
#: never had it is left alone.
INSTITUTE_PILL_RE = re.compile(r'<div id="atheniq-institute".*?</div>', re.S)


#: The five the env-config component carried, in its order. Pinned as a literal:
#: the bundles already built hold this array, and no rebuild is needed to take it
#: out — every app is patched to the empty list, the dashboard included.
PLATFORM_SECTIONS = (
    ("Courses", "https://ai.lms.innotel.us/courses.html"),
    ("Programs", "https://ai.lms.innotel.us/programs.html"),
    ("Classrooms", "https://ai.lms.innotel.us/index.html"),
    ("Studio", "https://studio.innotel.us/"),
    ("Platform", "https://ai.lms.innotel.us/platform.html"),
)


def sections_literal(pairs) -> str:
    """The array literal the bundle holds for a list of (label, href)."""
    return "[" + ",".join(f'["{label}","{href}"]' for label, href in pairs) + "]"


PLATFORM_NAV_ANCHOR = sections_literal(PLATFORM_SECTIONS)

#: The learner arrays the dashboard shipped, in each spelling it has been built
#: with. Pinned as literals so the bundles already deployed lose the links
#: without a rebuild: the catalog link first pointed at the LMS catalog MFE
#: (`Discover New`), then at the portal, and its label was written both
#: "Catalogue" and "Catalog".
LEGACY_LEARNER_ANCHORS = (
    sections_literal((
        ("Courses", "https://apps.learn.innotel.us/"),
        ("Discover New", "https://apps.learn.innotel.us/catalog/courses"),
    )),
    sections_literal((
        ("Courses", "https://apps.learn.innotel.us/"),
        ("Catalogue", "https://lms.innotel.us/"),
    )),
    sections_literal((
        ("Courses", "https://apps.learn.innotel.us/"),
        ("Catalog", "https://lms.innotel.us/"),
    )),
)

#: Every nav array the bundles carry, and the empty list each becomes.
NAV_ANCHORS = (PLATFORM_NAV_ANCHOR,) + LEGACY_LEARNER_ANCHORS

#: The dashboard's learner links, as they appear inside the array. A bundle that
#: still holds one of these still shows a menu, whatever array it was built in.
LEARNER_LINK_MARKERS = tuple(
    f'["{label}","{href}"]'
    for label, href in (
        ("Courses", "https://apps.learn.innotel.us/"),
        ("Catalogue", "https://lms.innotel.us/"),
        ("Catalog", "https://lms.innotel.us/"),
        ("Discover New", "https://apps.learn.innotel.us/catalog/courses"),
    )
)

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


#: The site shell's header, as the indigo theme builds it. Two things come out:
#: the product name the theme puts beside the logo (`title`/`alt` on the anchor and
#: on the image — visible text whenever the estate's own wordmark stands in for
#: the image the theme shipped), and the light/dark switch, which is rendered only
#: when `INDIGO_ENABLE_DARK_TOGGLE` is on.
#:
#: The switch is turned off at the source rather than hidden: the control also
#: writes a cookie and reloads the page, so a `display:none` on it would leave a
#: page-reloading checkbox in the tab order. `=!1` on the feature flag is one
#: token and the widget renders an empty div.
SITE_APP = "site"
SITE_HEADER_RULES = (
    ('s=(0,k.z)().INDIGO_ENABLE_DARK_TOGGLE', "s=!1"),
    ('title:"Open edX"', 'title:"AthenIQ"'),
    ('alt:"Open edX"', 'alt:"AthenIQ"'),
    ('defaultMessage:"My Open edX"', 'defaultMessage:"AthenIQ"'),
)

#: The learner dashboard's header is built by the app itself, not by the theme,
#: so the site's rules find a different shape. Two things still have to come out:
#:
#:   - The dark-mode switch. Its flag is read as `(0,runtime.config)().<name>`
#:     wherever the app asks, so the property read is swapped for a literal
#:     `(!1)` — valid in every position it appears in (`const x=` and `x=`). The
#:     control writes a cookie and reloads the page, so turning the flag off at
#:     the source is what leaves nothing in the tab order; a `display:none` on
#:     the widget would keep a page-reloading control behind it.
#:   - The stock wordmark beside the logo. It is the theme's own anchor
#:     (`a.logo` with `title="Open edX"`), which the plugin's logo slot does not
#:     always replace in this app; the shell CSS below hides exactly that anchor
#:     and nothing else — the AthenIQ logo is `a.logo[title="AthenIQ"]`.
DASHBOARD_TOGGLE_RE = re.compile(
    r"\(0,[A-Za-z_$][A-Za-z0-9_$]*\.[A-Za-z_$][A-Za-z0-9_$]*\)\(\)\.INDIGO_ENABLE_DARK_TOGGLE")

#: The dashboard's own header menu. `mainMenu` is built from three entries —
#: Courses, Programs and Discover New — and `secondaryMenu` from Help; the user
#: menu (profile, account, sign out) is a separate list and stays, because
#: sign-out lives nowhere else.
#:
#: The two that go are spreads gated on a feature flag, so the flag is what is
#: matched rather than the minified names around it: the shape is
#: `(0,a.b)().<FLAG>?[{type:"item",…}]:[]`, and the whole expression becomes
#: `[]` — the spread of an empty list, which leaves the array literal intact.
HEADER_MENU_ITEM_RE = re.compile(
    r'\(0,[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*\)\(\)\.(?:ENABLE_PROGRAMS|SUPPORT_URL)'
    r'\?\[\{type:"item",href:[^\]]*?\}\]:\[\]')

#: The account menu — profile, account, order history, sign out. It goes too:
#: the top is the logo, Courses and Discover New. Sign-out is not lost, it is on
#: the LMS account page every app links to (`ACCOUNT_SETTINGS_URL`).
ACCOUNT_MENU_MARKER = "userMenu:["
#: What a bundle that still carries the menu looks like, for the final check.
ACCOUNT_MENU_SHAPE = "userMenu:[{"

#: In the shell, not in a bundle: the anchor is rendered by a component the
#: plugin does not own in this app, and an attribute selector reaches it without
#: rewriting React. `title` is what distinguishes it from the AthenIQ logo.
DASHBOARD_HEADER_CSS = (
    '<style id="atheniq-header">'
    # The stock wordmark the theme renders beside the logo.
    '#root header a.logo[title="Open edX"]{display:none!important}'
    # A second copy of the logo that links away to the institute site: two
    # `a.logo` anchors, one to `/dashboard` and one to atheniq.institute. The
    # header keeps the one that goes home; the institute is reachable from the
    # link at the foot of the page.
    '#root header a.logo[href*="atheniq.institute"]{display:none!important}'
    '</style>'
)

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

    if app == SITE_APP:
        for old, new in SITE_HEADER_RULES:
            if old in text:
                counts["site-header"] += text.count(old)
                text = text.replace(old, new)

    # The dashboard is served at `/dashboard`; the public path is what the router
    # uses as its basename, so this one replacement moves both the app's files
    # and the routes it matches. `learner-dashboard` without the slashes is the
    # app id and is deliberately left alone.
    if app == DASHBOARD_APP and DASHBOARD_PATH_FROM in text:
        counts["dashboard-path"] += text.count(DASHBOARD_PATH_FROM)
        text = text.replace(DASHBOARD_PATH_FROM, DASHBOARD_PATH_TO)

    if app == DASHBOARD_APP:
        text, toggles = DASHBOARD_TOGGLE_RE.subn("(!1)", text)
        if toggles:
            counts["dashboard-dark-toggle"] += toggles
        # Programs and Help: the top carries Courses and Discover New only.
        text, menus = HEADER_MENU_ITEM_RE.subn("[]", text)
        if menus:
            counts["header-menu"] += menus
        text, accounts = empty_array(text, ACCOUNT_MENU_MARKER)
        if accounts:
            counts["header-account-menu"] += accounts

    # The header carries no AthenIQ nav: every list the bundles know about is
    # emptied. Empty rather than removed because the list is what the component
    # renders — `p.map(...)` over `[]` draws nothing — and the surrounding
    # expression has to keep the shape the rest of the bundle expects.
    for anchor in NAV_ANCHORS:
        if anchor in text:
            counts["header-nav"] += text.count(anchor)
            text = text.replace(anchor, "[]")

    if app == "authoring" and HOME_ACTIONS_ANCHOR in text:
        counts["home-actions"] += text.count(HOME_ACTIONS_ANCHOR)
        text = text.replace(HOME_ACTIONS_ANCHOR, _home_actions_js())
        # The stock library button is one of the four now; its push goes, its
        # enclosing block (and the callback it defines) stays.
        if HOME_LIBRARY_ANCHOR in text:
            counts["home-library-button"] += text.count(HOME_LIBRARY_ANCHOR)
            text = text.replace(HOME_LIBRARY_ANCHOR, "")

    # Last, so the rules above still see the strings the bundle was built with.
    for old, new in CONSOLE_URL_RULES:
        if old in text:
            counts["console-url"] += text.count(old)
            text = text.replace(old, new)

    return text


#: The MFE shell's <head>. The Unity skin goes in as two stylesheets beside it,
#: one per color scheme: Paragon reads its palette from CSS custom properties,
#: so a stylesheet recolors every page without rebuilding a bundle.
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


def empty_array(text: str, marker: str) -> tuple[str, int]:
    """Replace the array literal that starts right after `marker` with `[]`.

    Counted rather than matched with a regular expression: the account menu
    holds one nested `items` array per heading and a spread whose absent branch
    is itself `[]`, so the end of the array is only findable by matching
    brackets. Idempotent — an array that is already empty is left alone.
    """
    start = text.find(marker)
    if start < 0:
        return text, 0
    open_at = start + len(marker) - 1
    if text.startswith("[]", open_at):
        return text, 0
    depth = 0
    for index in range(open_at, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[:open_at] + "[]" + text[index + 1:], 1
    return text, 0


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


def app_root(app: str) -> str:
    """The URL prefix an app is served at — one app does not sit at its own name."""
    return DASHBOARD_ROOT if app == DASHBOARD_APP else app


def strip_institute(dist: Path, counts: Counter, write: bool) -> None:
    """Take the institute pill out of the dashboard shell.

    It sat between the app's root and the end of the body, so it rendered under
    every dashboard route as a bordered link to atheniq.institute. The footer
    already names the institute; this one is off the page.
    """
    shell = dist / "index.html"
    if not shell.is_file():
        raise SystemExit(f"patch-mfe-brand: {dist} has no index.html to clean")
    html = shell.read_text(encoding="utf-8")
    match = INSTITUTE_PILL_RE.search(html)
    if match is None:
        return
    counts["institute-pill"] += 1
    if write:
        shell.write_text(html.replace(match.group(0), "", 1), encoding="utf-8")


def brand_shell(dist: Path, counts: Counter, write: bool) -> None:
    """Put the header rule into the dashboard shell, once."""
    shell = dist / "index.html"
    if not shell.is_file():
        raise SystemExit("patch-mfe-brand: no dashboard shell to brand")
    html = shell.read_text(encoding="utf-8")
    existing = re.search(r'<style id="atheniq-header">.*?</style>', html, re.S)
    if existing and existing.group(0) == DASHBOARD_HEADER_CSS:
        return
    if existing:
        # The block is ours: replace it whole, so a rule added here reaches a
        # shell an earlier version already branded.
        counts["dashboard-header-css"] += 1
        if write:
            shell.write_text(html.replace(existing.group(0), DASHBOARD_HEADER_CSS, 1),
                             encoding="utf-8")
        return
    counts["dashboard-header-css"] += 1
    if write:
        shell.write_text(html.replace("</head>", DASHBOARD_HEADER_CSS + "</head>", 1),
                         encoding="utf-8")


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
    links = UNITY_LINK.format(root=f"/{app_root(app)}/")
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

    if app == DASHBOARD_APP:
        # Stylesheets too: the app's own sheet names its fonts and images by the
        # public path, and those requests would otherwise take a redirect per
        # file. Kept out of `iter_assets`, which is the text `patch_text` walks.
        for sheet in sorted(args.dist.glob("*.css")):
            text = sheet.read_text(encoding="utf-8", errors="ignore")
            if DASHBOARD_PATH_FROM in text:
                counts["dashboard-css-path"] += text.count(DASHBOARD_PATH_FROM)
                if not args.report:
                    sheet.write_text(text.replace(DASHBOARD_PATH_FROM, DASHBOARD_PATH_TO),
                                     encoding="utf-8")
        brand_shell(args.dist, counts, write=not args.report)
        strip_institute(args.dist, counts, write=not args.report)

    for label, number in sorted(counts.items()):
        print(f"  {label:28} {number}")
    print(f"patch-mfe-brand: {app}: {edited} file(s) {'would change' if args.report else 'changed'}")

    # The dashboard's header nav is the reason this script runs on the learner
    # apps: a bundle that still holds a learner link still shows a menu that was
    # meant to go. `--report` writes nothing, so it is held to a different bar:
    # every bundle either has nothing left to strip or a rule that matched it.
    if app == "learner-dashboard":
        leftovers = [a for a in iter_assets(args.dist)
                     if any(marker in a.read_text(encoding="utf-8", errors="ignore")
                            for marker in LEARNER_LINK_MARKERS)]
        if leftovers and (args.report and not counts.get("header-nav")):
            print(f"patch-mfe-brand: {leftovers[0]} still carries a learner header "
                  "link and no rule matched it — the bundle changed and the nav "
                  "was NOT removed", file=sys.stderr)
            return 1
        if leftovers and not args.report:
            print(f"patch-mfe-brand: {leftovers[0]} still carries a learner header "
                  "link after patching — the nav was NOT removed", file=sys.stderr)
            return 1

        # The same bar for the address. `/learner-dashboard/` left in the shell
        # or in the bundle's public path is a dashboard that loads at /dashboard
        # and asks for its own chunks at the old prefix: a page that renders
        # nothing, on the address this patch exists to make work.
        # The header menu goes the same way: a bundle that still spreads a
        # flagged item beside `mainMenu` still draws Programs or Help.
        unmenued = [a for a in iter_assets(args.dist)
                    if HEADER_MENU_ITEM_RE.search(a.read_text(encoding="utf-8", errors="ignore"))]
        if unmenued and args.report and not counts.get("header-menu"):
            print(f"patch-mfe-brand: {unmenued[0].name} spreads a flagged header item and "
                  "no rule matched it — the bundle changed and the menu was NOT reduced",
                  file=sys.stderr)
            return 1
        if unmenued and not args.report:
            print(f"patch-mfe-brand: {unmenued[0].name} still spreads a flagged header "
                  "item — the menu rule did not match and the top was NOT reduced",
                  file=sys.stderr)
            return 1

        accounts = [a for a in iter_assets(args.dist)
                    if ACCOUNT_MENU_SHAPE in a.read_text(encoding="utf-8", errors="ignore")]
        if accounts:
            print(f"patch-mfe-brand: {accounts[0].name} still builds an account menu — "
                  "the top was NOT reduced to Courses and Discover New", file=sys.stderr)
            return 1

        stale = [a for a in iter_assets(args.dist)
                 if DASHBOARD_PATH_FROM in a.read_text(encoding="utf-8", errors="ignore")]
        if stale and (args.report and not counts.get("dashboard-path")):
            print(f"patch-mfe-brand: {stale[0]} still names {DASHBOARD_PATH_FROM} and no "
                  "rule matched it — the public path was NOT moved to "
                  f"{DASHBOARD_PATH_TO}", file=sys.stderr)
            return 1
        if stale and not args.report:
            print(f"patch-mfe-brand: {stale[0]} still names {DASHBOARD_PATH_FROM} after "
                  "patching — the app would load at /dashboard and fetch its chunks "
                  "from the old path", file=sys.stderr)
            return 1

    if app == "authoring" and not counts.get("home-actions") \
            and not any(HOME_MARKER in a.read_text(encoding="utf-8", errors="ignore")
                        for a in iter_assets(args.dist)):
        print("patch-mfe-brand: the authoring home action list was not found — "
              "the bundle changed and the four create actions were NOT added", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
