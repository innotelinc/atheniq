"""AthenIQ — white-label footer for the learner MFEs.

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

# Bring the component into the MFE runtime env config (Indigo hooks the same
# patch name for its own components).
_tutor_hooks.Filters.ENV_PATCHES.add_item(
    ("mfe-env-config-runtime-definitions", FOOTER_COMPONENT)
)

if PLUGIN_SLOTS is not None:
    PLUGIN_SLOTS.add_items([(mfe, FOOTER_SLOT, FOOTER_SLOT_CONFIG)
                            for mfe in INDIGO_STYLED_MFES])

# Declarative hooks surface expected by the Tutor plugin loader (v0).
hooks: dict = {}
