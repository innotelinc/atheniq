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

The header carries nothing. A nav slotted into it renders on every page of every
learner app, and the links it carried repeated what the page already offers —
the dashboard lists the learner's own courses, and the AthenIQ portal
(`lms.innotel.us`) is where the catalog and the program store are. The
workspace menu (Courses · Programs · Classrooms · Studio · Platform) stays in
the console, where those pages live, not in a learner's header.

The authoring app gets a create row (+ New Program · + New Course · + New
Classroom · + New Library) in its page banner, because creating any of the
three is one action in the console, not three different apps.

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

#: The console's own base URL. Kept as one value so the create actions cannot
#: drift from the pages they open.
AI_CONSOLE_URL = "https://ai.lms.innotel.us/"

#: There is no header nav at all. Courses · Programs · Classrooms · Studio ·
#: Platform is the console's menu, and a learner's header has no use for it; the
#: two learner links that were once slotted in (Courses and the catalog) only
#: repeated the dashboard's own course list and the portal. Both are gone.

#: What the authoring app's create buttons become. The stock page offers one
#: "+ New Course"; a program, a classroom and a media library are created the
#: same way, in the workspace, and land in the same catalog.
STUDIO_ACTIONS = (
    ("+ New Program", AI_CONSOLE_URL + "programs.html"),
    ("+ New Course", AI_CONSOLE_URL + "course-create.html"),
    ("+ New Classroom", AI_CONSOLE_URL + "classroom-create.html"),
    ("+ New Library", AI_CONSOLE_URL + "library.html"),
)

#: The authoring home's banner slot, above the course list. The stock page puts
#: one "+ New Course" button beside its heading; this slot is where the four
#: create entries sit instead, so the action is in the same place on every
#: authoring screen. `additional_course_plugin.v1` was the alternative and is
#: per-card, which is the wrong place for a create action.
AUTHORING_SLOT = "org.openedx.frontend.authoring.page_banner.v1"

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
      `}}</style>
    {{ATHENIQ_STUDIO_ACTIONS.map(([label, href]) => (
      <a key={{label}} className="btn btn-outline-primary btn-sm" href={{href}}>{{label}}</a>
    ))}}
  </div>
);
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
    ("mfe-env-config-runtime-definitions", STUDIO_COMPONENT)
)

# The legacy per-app stages and the site stage each build webpack, and each
# carries its own "before the build" hook; refresh browserslist data in both.
for _hook in ("mfe-dockerfile-pre-npm-build", "mfe-dockerfile-pre-npm-build-site"):
    _tutor_hooks.Filters.ENV_PATCHES.add_item((_hook, BROWSERSLIST_REFRESH))

if PLUGIN_SLOTS is not None:
    PLUGIN_SLOTS.add_items([(mfe, FOOTER_SLOT, FOOTER_SLOT_CONFIG)
                            for mfe in INDIGO_STYLED_MFES])
    # The authoring app's create row, in the page slot rather than the header:
    # the four buttons belong over the studio list, not inside the nav.
    PLUGIN_SLOTS.add_items([("authoring", AUTHORING_SLOT, STUDIO_SLOT_CONFIG)])

# Declarative hooks surface expected by the Tutor plugin loader (v0).
hooks: dict = {}
