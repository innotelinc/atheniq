"""AthenIQ — white-label footer and AI link for the learner MFEs.

The Tutor Indigo theme hides the stock Open edX footer and inserts its own
(`IndigoFooter`) into the frontend-plugin-framework's footer slot. That footer
still renders the "Powered by" line with the Tutor and Open edX logos and links
to `open.edx.org` — copy that no LMS theme template can reach, because it lives
in the MFEs' compiled bundles.

This plugin replaces that footer at the same slot, the same way Indigo installs
its own: an env-config runtime definition for the component plus a
`PLUGIN_SLOTS` entry that hides Indigo's widgets and inserts the AthenIQ one. It
targets the footer slot Indigo uses (`org.openedx.frontend.layout.footer.v1`)
and hides both the stock contents and Indigo's/legacy widget ids, so it is
robust across the Indigo versions that used `indigo_footer` and the older
`custom_footer`.

Requires Tutor Indigo (for the theme and the slot machinery) and a rebuilt MFE
image:

    tutor plugins enable atheniqmfe
    tutor config save
    tutor images build mfe
    tutor local launch

The header is the same mechanism: an env-config runtime definition plus a
`PLUGIN_SLOTS` entry that adds one nav to the desktop main menu and one to the
mobile menu. That nav is the platform's own — Courses · Programs · Classrooms ·
Studio · Platform — so every app in the estate opens the same workspace, on the
same Authentik session the LMS already uses. The authoring app additionally gets
a create row (+ New Program · + New Course · + New Classroom · + New Library) in
its page banner, because creating any of the three is one action in the console,
not three different apps.

The LMS footer itself is replaced by `contrib/atheniq-theme` (no rebuild); this
plugin is only for the learner MFEs.
"""
from tutor import hooks as _tutor_hooks

try:
    from tutormfe.hooks import PLUGIN_SLOTS
except ImportError:  # tutor-mfe not installed — the plugin stays inert.
    PLUGIN_SLOTS = None

# The MFEs Indigo styles and slots into (mirrors tutor-indigo's list).
INDIGO_STYLED_MFES = [
    "learning",
    "learner-dashboard",
    "profile",
    "account",
    "discussions",
    "authoring",
]

FOOTER_SLOT = "org.openedx.frontend.layout.footer.v1"

#: The AI interface the header link opens. Kept as one value so the label, the
#: URL and any future move of the console cannot drift apart.
AI_CONSOLE_URL = "https://ai.lms.innotel.us/"

#: The one workspace behind every authoring entry point. Courses, programs and
#: classrooms are created and maintained there; Studio edits the course those
#: specs describe. Each label points at the page that does the thing, so the
#: header is the same everywhere instead of five apps with five menus.
PLATFORM_SECTIONS = (
    ("Courses", AI_CONSOLE_URL + "courses.html"),
    ("Programs", AI_CONSOLE_URL + "programs.html"),
    ("Classrooms", AI_CONSOLE_URL + "index.html"),
    ("Studio", "https://studio.innotel.us/"),
    ("Platform", AI_CONSOLE_URL + "platform.html"),
)

#: What the authoring app's create buttons become. The stock page offers one
#: "+ New Course"; a program, a classroom and a media library are created the
#: same way, in the workspace, and land in the same catalogue.
STUDIO_ACTIONS = (
    ("+ New Program", AI_CONSOLE_URL + "programs.html"),
    ("+ New Course", AI_CONSOLE_URL + "course-create.html"),
    ("+ New Classroom", AI_CONSOLE_URL + "classroom-create.html"),
    ("+ New Library", AI_CONSOLE_URL + "library.html"),
)

#: Where the platform nav goes. These are the *legacy* layout slot ids: the
#: frontend-base compatibility shim maps them onto the new sub-slots
#: (`...slot.header.primaryLinks.v1` for desktop, the mobile menu for phones),
#: and a slot id that is not in that map is skipped with a warning.
HEADER_DESKTOP_SLOT = "org.openedx.frontend.layout.header_desktop_main_menu.v1"
HEADER_MOBILE_SLOT = "org.openedx.frontend.layout.header_mobile_main_menu.v1"

#: The authoring home's banner slot, above the course list. The stock page puts
#: one "+ New Course" button beside its heading; this slot is where the four
#: create entries sit instead, so the action is in the same place on every
#: authoring screen. `additional_course_plugin.v1` was the alternative and is
#: per-card, which is the wrong place for a create action.
AUTHORING_SLOT = "org.openedx.frontend.authoring.page_banner.v1"

#: `all`, because that is the only value this deployment's MFE build honours:
#: tutor-mfe compiles one `env.config.jsx` and every app target copies it, so a
#: named app would simply lose the widget rather than place it. The app that may
#: show it is chosen in the component instead (see HEADER_COMPONENT): Studio
#: only, which is served under `/authoring`.
HEADER_MFES = ["all"]

# The component, injected into the MFE runtime env config exactly as Indigo
# injects its own. Indigo's env-config imports already bring React and
# `getConfig` into scope, so this needs no imports of its own.
FOOTER_COMPONENT = """
const AthenIQFooter = () => {
  const config = getConfig();
  const base = config.LMS_BASE_URL || '';
  const year = new Date().getFullYear();
  return (
    <div className="wrapper wrapper-footer atheniq-footer">
      <footer id="footer" className="tutor-container">
        <div className="footer-top">
          <div className="powered-area">
            <ul className="logo-list">
              <li>
                <a href={base} rel="noreferrer">
                  <img
                    src={`${base}/theming/asset/images/logo.png`}
                    alt="AthenIQ"
                    width="48"
                  />
                </a>
              </li>
            </ul>
          </div>
        </div>
        <span className="copyright-site">
          {`©${year} AthenIQ · Innotel Labs. All Rights Reserved.`}
        </span>
      </footer>
    </div>
  );
};
"""

# Hide the stock contents, Indigo's widget, and the legacy id; then insert ours.
FOOTER_SLOT_CONFIG = """
{
op: PLUGIN_OPERATIONS.Hide,
widgetId: 'default_contents',
},
{
op: PLUGIN_OPERATIONS.Hide,
widgetId: 'indigo_footer',
},
{
op: PLUGIN_OPERATIONS.Hide,
widgetId: 'custom_footer',
},
{
op: PLUGIN_OPERATIONS.Insert,
widget: {
id: 'atheniq_footer',
type: DIRECT_PLUGIN,
priority: 20,
RenderWidget: AthenIQFooter,
},
},
"""

# The platform nav. Plain anchors, not Paragon Nav.Links: the desktop slot
# renders beside the nav rather than inside its <Nav>, and `nav-link` carries
# the same styling in both places.
HEADER_COMPONENT = f"""
const ATHENIQ_SECTIONS = {[list(pair) for pair in PLATFORM_SECTIONS]!r};
const AthenIQPlatformNav = () => {{
  // Studio only. One env.config.jsx is compiled into every MFE here, so the
  // widget has to decide for itself which app it is in: authoring is served
  // under /authoring, and the learner apps (course page, dashboard, profile)
  // are not. A learner has no use for the workspace, an instructor writing a
  // course does.
  if (!window.location.pathname.startsWith('/authoring')) return null;
  return (
  <nav className="atheniq-nav" aria-label="AthenIQ Platform Services">
    {{ATHENIQ_SECTIONS.map(([label, href]) => (
      <a key={{label}} className="nav-link atheniq-nav-link" href={{href}}>{{label}}</a>
    ))}}
  </nav>
  );
}};
"""

# The authoring app's own create row. The stock heading and "+ New course"
# button are hidden rather than edited, because they live in the compiled
# bundle; the four entries below are the whole create surface.
STUDIO_COMPONENT = f"""
const ATHENIQ_STUDIO_ACTIONS = {[list(pair) for pair in STUDIO_ACTIONS]!r};
const AthenIQStudioActions = () => (
  <div className="atheniq-studio-actions">
    <style>{{`
      .atheniq-studio-actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
      .atheniq-studio-actions a {{ text-decoration: none; }}
      .atheniq-nav {{ display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-inline-start: auto; }}
      .atheniq-nav-link {{ white-space: nowrap; }}
    `}}</style>
    {{ATHENIQ_STUDIO_ACTIONS.map(([label, href]) => (
      <a key={{label}} className="btn btn-outline-primary btn-sm" href={{href}}>{{label}}</a>
    ))}}
  </div>
);
"""

HEADER_SLOT_CONFIG = """
{
op: PLUGIN_OPERATIONS.Insert,
widget: {
id: 'atheniq_platform_nav',
type: DIRECT_PLUGIN,
priority: 30,
RenderWidget: AthenIQPlatformNav,
},
},
"""

STUDIO_SLOT_CONFIG = """
{
op: PLUGIN_OPERATIONS.Insert,
widget: {
id: 'atheniq_studio_actions',
type: DIRECT_PLUGIN,
priority: 10,
RenderWidget: AthenIQStudioActions,
},
},
"""

# Browserslist resolves its compat data from the `caniuse-lite` snapshot pinned
# in the app's lockfile, and that snapshot is months old by the time an image is
# built — webpack says so on every build, then compiles against stale targets.
#
# The data package is a leaf, so fetch just its tarball and unpack it over
# node_modules instead of running an install: `npm install caniuse-lite@latest`
# re-resolves the whole peer graph (and fails with ERESOLVE on these apps), and
# an install would also rewrite the package.json/lockfile upstream pinned.
# `npm pack` only downloads.
#
# The target is `$(pwd)`, not a fixed path: this hook injects into the per-app
# stages (WORKDIR /openedx/app) *and* the site stage (WORKDIR /openedx/site).
# Pinning /openedx/app made the site stage create a stray node_modules that
# nothing builds from, so its webpack still warned about stale data.
BROWSERSLIST_REFRESH = """
RUN set -eux; \
    app="$(pwd)"; \
    cd /tmp; \
    npm pack --silent caniuse-lite@latest >/dev/null; \
    rm -rf "$app/node_modules/caniuse-lite"; \
    mkdir -p "$app/node_modules/caniuse-lite"; \
    tar -xzf /tmp/caniuse-lite-*.tgz --strip-components=1 -C "$app/node_modules/caniuse-lite"; \
    rm -f /tmp/caniuse-lite-*.tgz; \
    for d in $(find "$app/node_modules" -type d -name caniuse-lite | grep -vx "$app/node_modules/caniuse-lite"); do \
      rm -rf "$d"; \
      cp -a "$app/node_modules/caniuse-lite/." "$d/"; \
    done; \
    node -e "console.log('caniuse-lite', require('$app/node_modules/caniuse-lite/package.json').version)"
"""

# Bring the components into the MFE runtime env config (Indigo hooks the same
# patch name for its own components).
_tutor_hooks.Filters.ENV_PATCHES.add_item(
    ("mfe-env-config-runtime-definitions", FOOTER_COMPONENT)
)
_tutor_hooks.Filters.ENV_PATCHES.add_item(
    ("mfe-env-config-runtime-definitions", HEADER_COMPONENT)
)
_tutor_hooks.Filters.ENV_PATCHES.add_item(
    ("mfe-env-config-runtime-definitions", STUDIO_COMPONENT)
)

# The legacy per-app stages and the site stage each build webpack, and each
# carries its own "before the build" hook; refresh browserslist data in both.
for _hook in ("mfe-dockerfile-pre-npm-build", "mfe-dockerfile-pre-npm-build-site"):
    _tutor_hooks.Filters.ENV_PATCHES.add_item((_hook, BROWSERSLIST_REFRESH))

if PLUGIN_SLOTS is not None:
    PLUGIN_SLOTS.add_items([(mfe, FOOTER_SLOT, FOOTER_SLOT_CONFIG)
                            for mfe in INDIGO_STYLED_MFES])
    PLUGIN_SLOTS.add_items([(mfe, slot, HEADER_SLOT_CONFIG)
                            for mfe in HEADER_MFES
                            for slot in (HEADER_DESKTOP_SLOT, HEADER_MOBILE_SLOT)])
    # The authoring app's create row, in the page slot rather than the header:
    # the four buttons belong over the studio list, not inside the nav.
    PLUGIN_SLOTS.add_items([("authoring", AUTHORING_SLOT, STUDIO_SLOT_CONFIG)])

# Declarative hooks surface expected by the Tutor plugin loader (v0).
hooks: dict = {}
