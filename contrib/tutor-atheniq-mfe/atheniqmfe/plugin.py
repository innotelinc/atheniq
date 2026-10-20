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

The header link is the same mechanism: an env-config runtime definition plus a
`PLUGIN_SLOTS` entry that appends one widget to the desktop main menu and one
to the mobile menu. It is the way into the AI interface (`ai.lms.innotel.us`)
from any learner page, on the same Authentik session the LMS already uses, so
the click does not ask for a second sign-in.

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
AI_CONSOLE_LABEL = "AI Classroom"

#: Where the header link goes. These are the *legacy* layout slot ids: the
#: frontend-base compatibility shim maps them onto the new sub-slots
#: (`...slot.header.primaryLinks.v1` for desktop, the mobile menu for phones),
#: and a slot id that is not in that map is skipped with a warning.
HEADER_DESKTOP_SLOT = "org.openedx.frontend.layout.header_desktop_main_menu.v1"
HEADER_MOBILE_SLOT = "org.openedx.frontend.layout.header_mobile_main_menu.v1"

#: The wildcard is the whole list on purpose. tutor-mfe renders `all`
#: *unguarded* in env.config.jsx — the file every legacy MFE builds with — and
#: again in the site app's env.config.all.jsx. Naming the MFEs as well (as the
#: footer does) would add the same widget a second time to every app that also
#: matched the wildcard, which is exactly the duplicate link this list exists to
#: avoid.
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

# The header link. A plain anchor, not a Paragon Nav.Link: the desktop slot
# renders beside the nav rather than inside its <Nav>, and `nav-link` carries
# the same styling in both places.
HEADER_COMPONENT = f"""
const AthenIQHeaderLink = () => (
  <a className="nav-link" href={{{AI_CONSOLE_URL!r}}}>{AI_CONSOLE_LABEL}</a>
);
"""

HEADER_SLOT_CONFIG = """
{
op: PLUGIN_OPERATIONS.Insert,
widget: {
id: 'atheniq_ai_link',
type: DIRECT_PLUGIN,
priority: 30,
RenderWidget: AthenIQHeaderLink,
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

# Declarative hooks surface expected by the Tutor plugin loader (v0).
hooks: dict = {}
