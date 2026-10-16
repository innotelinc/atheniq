"""AthenIQ — the platform's own face, baked into the Tutor images.

WHAT THIS PLUGIN IS. `contrib/atheniq-theme` holds the files; this makes them
part of the deployment instead of a copy in a container's writable layer. The
difference matters: `make theme` (`scripts/apply-atheniq-theme.sh`) applies the
same files to a *running* LMS and is lost the next time the container is
recreated — which is exactly what `tutor local launch` does. A brand that
disappears on the next deploy is not a brand, it is a suggestion.

HOW IT LANDS. Two patches and one configuration default:

1. **The theme files**, rendered into the Open edX build context and `COPY`-ed
   over Indigo's theme *after* the image's own asset collection, followed by a
   `collectstatic` so the collected, content-hashed copies — the ones a browser
   actually fetches — are the AthenIQ ones. The LMS header logo, the footer, the
   index overlay, the favicon and the Unity stylesheets all arrive this way.

   Why after `collectstatic` rather than before: the theme directory is copied
   into the image at one point and its static assets are collected at another,
   and only a patch at the last of those points is guaranteed to see both. The
   extra `collectstatic` is a few seconds and removes the whole class of "the
   template changed but the served image did not" bugs.

2. **The learner MFEs' palette.** Indigo renders `MFE_CONFIG["PARAGON_THEME_URLS"]`
   from the `PARAGON_THEME_URLS` configuration value, and the MFEs paint from
   those stylesheets at runtime. This patch keeps Indigo's compiled theme as the
   `default` URL — it is the structure and the utility classes — and points
   `brandOverride` at AthenIQ's Unity skin, served from the LMS's own theming
   assets. No MFE bundle is rebuilt, and no MFE is left wearing another
   platform's colours.

   *Why the patch mutates in place rather than replacing the value.* The
   `default` URL carries Indigo's release branch, so hard-coding it here would
   pin the deployment to whatever was current the day this file was written.
   Reading it back and overriding only `brandOverride` keeps this plugin
   agnostic to the Indigo version underneath.

3. **`PLATFORM_NAME`**, as a default only: a deployment that has already chosen
   its own name keeps it (`tutor config save` wins over a plugin default).

INSTALL

    pip install -e contrib/tutor-atheniq-theme       # or copy into ~/.local/share/tutor/plugins
    tutor plugins enable atheniqtheme
    tutor config save
    tutor images build openedx                       # the theme files are in the image
    tutor local launch

REQUIRES A REBUILT openedx IMAGE for part 1; part 2 takes effect on the next
`tutor local launch` and an LMS restart, because it is a settings patch. Nothing
here needs the `mfe` image rebuilt: the Unity skin is a stylesheet the MFEs load,
not a component compiled into them. `contrib/tutor-atheniq-mfe` is the plugin
for the parts that *do* need that rebuild — the footer lockup and the header
logo's hover label inside the compiled bundles.
"""

from __future__ import annotations

from pathlib import Path

from tutor import hooks

#: The theme overlay: templates, brand rasters and the Unity stylesheets.
#: Resolved from this file rather than configured, because the two directories
#: are one artifact — the plugin exists to install `atheniq-theme`.
THEME_DIR = Path(__file__).resolve().parent.parent.parent / "atheniq-theme"
if not THEME_DIR.is_dir():  # pragma: no cover - a broken install, said plainly
    raise ImportError(
        f"the AthenIQ theme overlay is missing at {THEME_DIR}. Install this "
        "plugin from the onTrak/atheniq checkout (pip install -e "
        "contrib/tutor-atheniq-theme), or copy contrib/atheniq-theme beside it."
    )

#: Where Indigo keeps its theme inside the image, and therefore where ours goes.
THEME_ROOT = "/openedx/themes/indigo/lms"

#: The Tutor settings patches that carry the Unity skin into the MFEs.
MFE_SETTINGS_PATCH = "mfe-lms-common-settings"


def _unity_patch() -> str:
    """The settings patch that re-points Paragon's brand override at Unity.

    Only `brandOverride` moves: the compiled theme stays the `default` URL, so
    the deployment keeps every structural rule and utility class Indigo ships.
    `LMS_ROOT_URL` is the LMS's own public base URL — the same host that serves
    the theming assets, so no new host is introduced.
    """
    return '''# AthenIQ — wear Unity. The compiled theme stays underneath; only the brand
# override moves, so structure and utilities are untouched.
_atheniq_variants = MFE_CONFIG.get("PARAGON_THEME_URLS", {}).get("variants", {})
for _atheniq_variant in ("light", "dark"):
    _atheniq_urls = _atheniq_variants.setdefault(_atheniq_variant, {}).setdefault("urls", {})
    _atheniq_urls["brandOverride"] = (
        f"{LMS_ROOT_URL}/theming/asset/atheniq/unity-{_atheniq_variant}.css"
    )
FRONTEND_SITE_CONFIG.setdefault("commonAppConfig", {})["PARAGON_THEME_URLS"] = (
    MFE_CONFIG["PARAGON_THEME_URLS"]
)
'''


# --- 1. the theme files, into the openedx image ------------------------------

# The overlay is rendered into the build context (`env/build/openedx/`) under its
# own directory name, so the Dockerfile can `COPY` exactly what it owns.
hooks.Filters.ENV_TEMPLATE_ROOTS.add_item(str(THEME_DIR.parent))
hooks.Filters.ENV_TEMPLATE_TARGETS.add_items(
    [
        # `<contrib>/atheniq-theme/**` -> `build/openedx/atheniq-theme/**`
        ("atheniq-theme", "build/openedx"),
    ]
)

hooks.Filters.ENV_PATCHES.add_item(
    (
        # After the image's own `collectstatic`, so both the theme directory and
        # the collected, hashed copies come out AthenIQ's.
        "openedx-dockerfile",
        f"""# AthenIQ — the platform's own branding, on top of Indigo's theme. The theme
# files are copied in and then re-collected, because a browser fetches the
# collected, content-hashed copy under /openedx/staticfiles/, not the theme
# directory: without the second step the templates change and the served logo
# does not.
COPY --chown=app:app ./atheniq-theme/lms/ {THEME_ROOT}/
RUN ./manage.py lms collectstatic --noinput --settings=tutor.assets && \\
    ./manage.py cms collectstatic --noinput --settings=tutor.assets
""",
    ),
    # Last of the Dockerfile patches: nothing else may follow with a theme copy
    # of its own, or it would overwrite the branding this plugin just installed.
    priority=hooks.priorities.LOW,
)


# --- 2. the learner MFEs' palette -------------------------------------------

# `priority=LOW` IS NOT DECORATION. Tutor renders patches for one patch point in
# priority order, highest last — and Indigo assigns `MFE_CONFIG["PARAGON_THEME_URLS"]`
# from its own `mfe-lms-common-settings` patch at the default priority. At the
# default priority ours renders *first* and Indigo then overwrites it, which is a
# silent no-op: the stylesheet exists, the config looks right in `config.yml`, and
# nothing changes on screen. LOW puts this after it. `LC_ALL=C tutor config save`
# is how that was found, and `tests/test_unity_skin.py` pins it.
hooks.Filters.ENV_PATCHES.add_item(
    (MFE_SETTINGS_PATCH, _unity_patch()), priority=hooks.priorities.LOW
)


# --- 3. the platform's name --------------------------------------------------

# A default, not an override: a deployment that already chose its own name (or
# wants a different one) is unaffected, which is what "default" has to mean for
# this plugin to be safe to enable anywhere.
hooks.Filters.CONFIG_DEFAULTS.add_item(("PLATFORM_NAME", "AthenIQ"))

# Declarative hooks surface expected by the Tutor plugin loader (v0).
hooks: dict = {}
