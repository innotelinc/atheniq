"""AthenIQ — the Unity theme for Open edX, baked into the Tutor images.

WHAT THIS INSTALLS. `contrib/openedx-theme-unity` is a complete Open edX theme:

* `lms/` and `cms/` hold the templates, the compiled stylesheets, fonts and
  images; and
* `lms/static/atheniq/` and `cms/static/atheniq/` hold the Unity design
  system, its switch and the LMS/Studio skins.

The theme directory is installed at `/openedx/themes/unity` as the site theme.
It replaces `tutor-indigo`: Indigo is no longer installed, enabled or loaded.
The theme's structural base was forked from Indigo's MIT/Apache-2.0 theme at the
point AthenIQ adopted it, and every visible surface is painted by Unity (see
`contrib/openedx-theme-unity/README.md` for the provenance and file map).

HOW IT LANDS. Three patches and one configuration default:

1. **The theme files**, rendered into the Open edX build context and `COPY`-ed
   into `/openedx/themes/unity/`, followed by a `collectstatic` so the collected,
   content-hashed copies — the ones a browser actually fetches — are the Unity
   ones. The two served static halves are copied explicitly as well:
   `/openedx/staticfiles/atheniq/` for the LMS (linked by `head-extra.html` as
   `/static/atheniq/…`) and `/openedx/staticfiles/studio/unity/atheniq/` for
   Studio (linked as `/static/studio/unity/atheniq/…`).

   Why after `collectstatic` rather than before: the theme directory is copied
   into the image at one point and its static assets are collected at another,
   and only a patch at the last of those points is guaranteed to see both. The
   extra `collectstatic` is a few seconds and removes the whole class of "the
   template changed but the served image did not" bugs.

2. **`DEFAULT_SITE_THEME = "unity"`** for the LMS and the CMS, as a settings
   patch. This is what makes a freshly created site — and a site whose theme
   record was reset — land on Unity instead of the platform default. The
   existing site's theme is set with `tutor local do settheme unity`; both agree
   on the same directory.

3. **`PLATFORM_NAME`**, as a default only: a deployment that has already chosen
   its own name keeps it (`tutor config save` wins over a plugin default).

INSTALL

    pip install -e contrib/tutor-atheniq-theme       # or copy into ~/.local/share/tutor/plugins
    tutor plugins enable atheniqtheme
    tutor config save
    tutor images build openedx                       # the theme files are in the image
    tutor local launch
    tutor local do settheme unity

REQUIRES A REBUILT openedx IMAGE for part 1. For a deployment that cannot
rebuild from source, `scripts/apply-atheniq-theme.sh` bakes the same theme into a
one-layer derivative of the running image and is what this repository's host
uses. Nothing here needs the `mfe` image rebuilt: the Unity skin is a stylesheet
the MFEs load, not a component compiled into them. `contrib/tutor-atheniq-mfe`
is the plugin for the parts that *do* need that rebuild — the footer lockup and
the header logo's hover label inside the compiled bundles.
"""

from __future__ import annotations

from pathlib import Path

from tutor import hooks

#: The theme: templates, compiled CSS, brand rasters and the Unity stylesheets.
#: Resolved from this file rather than configured, because the two directories
#: are one artifact — the plugin exists to install `openedx-theme-unity`.
THEME_DIR = Path(__file__).resolve().parent.parent.parent / "openedx-theme-unity"
if not THEME_DIR.is_dir():  # pragma: no cover - a broken install, said plainly
    raise ImportError(
        f"the Unity theme is missing at {THEME_DIR}. Install this plugin from "
        "the onTrak/atheniq checkout (pip install -e contrib/tutor-atheniq-theme), "
        "or copy contrib/openedx-theme-unity beside it."
    )

#: The theme's name, and therefore its directory under `/openedx/themes` and the
#: value of `DEFAULT_SITE_THEME`. One string, so the three cannot drift.
THEME_NAME = "unity"

#: Where an Open edX theme lives inside the image. The LMS and the CMS are two
#: overlays with the same root.
THEME_ROOT = f"/openedx/themes/{THEME_NAME}"

#: Where a browser actually fetches the two skins from. The LMS theming app
#: resolves `/theming/asset/atheniq/…` out of the *top-level* collected static
#: directory, and Studio asks for `/static/studio/unity/atheniq/…` — the CMS's
#: static namespace is `studio`, and the theme's own files are collected under
#: its `unity/` inside that. Both are copied explicitly rather than left to
#: `collectstatic` alone, which would leave the LMS's `/static/atheniq/…` URLs —
#: the ones `head-extra.html` links — unserved.
LMS_STATIC_ROOT = "/openedx/staticfiles/atheniq"
CMS_STATIC_ROOT = f"/openedx/staticfiles/studio/{THEME_NAME}/atheniq"

#: The settings patch points that declare the default theme.
LMS_SETTINGS_PATCH = "openedx-lms-common-settings"
CMS_SETTINGS_PATCH = "openedx-cms-common-settings"


# --- 1. the theme files, into the openedx image ------------------------------

# The theme is rendered into the build context (`env/build/openedx/`) under its
# own directory name, so the Dockerfile can `COPY` exactly what it owns.
# The theme is an artifact, not a template. Tutor renders every file under a
# template root through Jinja, and the compiled CSS contains the sequence `{#`
# (a minified `--#fff` custom property) which Jinja reads as the start of a
# comment. The whole directory is therefore copied verbatim; the only files that
# need Tutor's configuration are the Mako templates, and they are not rendered
# here either — Mako does that in the LMS at request time.
@hooks.Filters.IS_FILE_RENDERED.add()
def _copy_theme_verbatim(rendered: bool, template_name: str) -> bool:
    if template_name.startswith(("openedx-theme-unity/", "atheniq-theme/")):
        return False
    return rendered
hooks.Filters.ENV_TEMPLATE_ROOTS.add_item(str(THEME_DIR.parent))
hooks.Filters.ENV_TEMPLATE_TARGETS.add_items(
    [
        # `<contrib>/openedx-theme-unity/**` -> `build/openedx/openedx-theme-unity/**`
        ("openedx-theme-unity", "build/openedx"),
        # The course-card photographs are one pool shared by the publisher and
        # the theme; they are copied from their single source into the served
        # static directory below rather than duplicated in the theme.
        ("atheniq-theme", "build/openedx"),
    ]
)

hooks.Filters.ENV_PATCHES.add_item(
    (
        # After the image's own `collectstatic`, so both the theme directory and
        # the collected, hashed copies come out Unity's.
        "openedx-dockerfile",
        f"""# AthenIQ — the Unity Open edX theme. The theme files are copied in and then
# re-collected, because a browser fetches the collected, content-hashed copy
# under /openedx/staticfiles/, not the theme directory: without the second step
# the templates change and the served logo does not.
COPY --chown=app:app ./openedx-theme-unity/lms/ {THEME_ROOT}/lms/
COPY --chown=app:app ./openedx-theme-unity/cms/ {THEME_ROOT}/cms/
# The two skins' served copies. `head-extra.html` links `/static/atheniq/…` and
# Studio's header links `/static/studio/unity/atheniq/…`; these are the
# directories those URLs resolve to, so the stylesheets, the switch and the
# course photos are in place even if a collect is ever run with `--skip-themes`.
COPY --chown=app:app ./openedx-theme-unity/lms/static/atheniq/ {LMS_STATIC_ROOT}/
COPY --chown=app:app ./openedx-theme-unity/lms/static/images/ {LMS_STATIC_ROOT}/images/
COPY --chown=app:app ./atheniq-theme/lms/static/images/courses/ {LMS_STATIC_ROOT}/images/courses/
COPY --chown=app:app ./openedx-theme-unity/cms/static/atheniq/ {CMS_STATIC_ROOT}/
RUN ./manage.py lms collectstatic --noinput --settings=tutor.assets && \
    ./manage.py cms collectstatic --noinput --settings=tutor.assets
""",
    ),
    # Last of the Dockerfile patches: nothing else may follow with a theme copy
    # of its own, or it would overwrite the branding this plugin just installed.
    priority=hooks.priorities.LOW,
)


# --- 2. the site theme -------------------------------------------------------

# `settheme` writes a `SiteTheme` row for the deployment's site; this makes the
# same choice the default for any site that has no row (a fresh database, a new
# site, or a hostname added later). Both point at the one directory above.
for patch_name in (LMS_SETTINGS_PATCH, CMS_SETTINGS_PATCH):
    hooks.Filters.ENV_PATCHES.add_item(
        (
            patch_name,
            f'# AthenIQ — the platform wears Unity.\nDEFAULT_SITE_THEME = "{THEME_NAME}"\n',
        ),
        priority=hooks.priorities.LOW,
    )


# --- 3. the platform's name --------------------------------------------------

# A default, not an override: a deployment that already chose its own name (or
# wants a different one) is unaffected, which is what "default" has to mean for
# this plugin to be safe to enable anywhere.
hooks.Filters.CONFIG_DEFAULTS.add_item(("PLATFORM_NAME", "AthenIQ"))

# Declarative hooks surface expected by the Tutor plugin loader (v0).
hooks: dict = {}
