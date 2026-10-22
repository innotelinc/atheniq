# AthenIQ brand assets — the sources the Unity theme installs

This directory is **not** the Open edX theme any more. The theme is
[`../openedx-theme-unity`](../openedx-theme-unity): a complete Open edX theme
installed at `/openedx/themes/unity` with `DEFAULT_SITE_THEME = "unity"`. Indigo
is not installed, enabled or loaded.

What remains here are the assets that have one source outside the theme:

| Path | Why it lives here |
| --- | --- |
| `mfe/unity-light.css`, `mfe/unity-dark.css` | Paragon `brandOverride` for the learner MFEs; compiled into the MFE bundles by `scripts/patch-mfe-brand.py`. |
| `lms/static/images/courses/` | The course-photograph pool. Served from `/static/atheniq/images/courses/…`; `publish-courses.py` and the catalog resolve a course to one file here. |
| `lms/static/images/logo.png`, `logo-white.png`, `favicon.ico` | The generated brand rasters (`make images`); the theme's installer copies them into `/openedx/themes/unity/lms/static/images/`. |
| `lms/templates/*`, `lms/static/atheniq/*`, `cms/*` | Historical copies kept in step with the theme for reference and for the tests that pin the Unity palette; the theme is the copy that is installed. |

The theme's own README has the file map and provenance. Apply the theme with:

```bash
make images                # regenerate the brand rasters, if stale
make course-photos         # fetch the course photographs, if missing
make theme                 # == ./scripts/apply-atheniq-theme.sh
tutor local do settheme unity
```

## The learner MFEs

The learner **MFEs** (catalog, learning, profile, …) do not render the LMS
footer template — they render their own footer from compiled JS bundles. The
MFE image was built with Indigo's frontend plugin before this migration, and its
footer widget still prints “Powered by” with the Tutor + Open edX logos. Because
it is baked into the bundles, no template or config value on the LMS can change
it.

[`contrib/tutor-atheniq-mfe`](../tutor-atheniq-mfe) hides those footer widgets at
that slot and inserts the AthenIQ lockup instead. It needs an MFE rebuild:

```bash
tutor plugins enable atheniqmfe
tutor config save
tutor images build mfe
tutor local launch
```

The Unity palette reaches the MFEs today through `atheniq-unity.css`, which the
MFE bundles load; the MFE rebuild is only about the compiled footer component.
