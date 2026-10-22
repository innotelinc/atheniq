# Unity — the AthenIQ Open edX theme

The theme the LMS and Studio wear. It is a complete Open edX theme directory:
`lms/` and `cms/` each hold their templates and static files, exactly the layout
`COMPREHENSIVE_THEME_DIRS` expects, and it is installed as
`/openedx/themes/unity` with `DEFAULT_SITE_THEME = "unity"`.

**Indigo is not part of this theme.** The deployment used to run
`tutor-indigo` and paint Unity over it. This theme was forked from Indigo's
theme at 22.0.0 as a starting point for the platform's own markup, then:

* every visible surface (LMS header, footer, course pages, Studio chrome,
  buttons, forms, tables, cards, notices and the dark mode) is painted by
  `lms/static/atheniq/atheniq-lms.css` and `cms/static/atheniq/unity-cms.css`,
  both naming Unity tokens;
* the Unity palette and switch live in `atheniq/unity-theme.css` and
  `atheniq/unity-theme.js`, the canonical copies from the Innotel Platform
  Stack;
* the footer, the `<head>` hook and the landing overlay are AthenIQ's;
* the brand rasters are AthenIQ's; and
* Studio's header is `cms/templates/widgets/header.html`, in the Unity
  `operations` register.

The forked compiled stylesheets under `lms/static/css/`, `cms/static/css/`,
`lms/static/fonts/` and the remaining images are the structural base — the
layout, course chrome and Open edX component defaults that Unity's skin sits on.
They are vendored here so the theme is self-contained and no Indigo package or
plugin is installed at runtime. The original Sass sources are kept under
`lms/static/sass/` and `cms/static/sass/` for provenance and recompilation;
they are not served.

## Layout

| Path | What it is |
| --- | --- |
| `lms/templates/head-extra.html` | Loads Unity and the LMS skin before the first paint; adopts the old theme cookie once. |
| `lms/templates/footer.html` | The AthenIQ footer (no upstream attribution lockups). |
| `lms/templates/index_overlay.html` | The landing overlay. |
| `lms/static/atheniq/` | Unity palette, switch, LMS skin and the MFEs' Paragon override. |
| `lms/static/images/` | Brand rasters and the theme's structural images. |
| `cms/templates/widgets/header.html` | Studio's header, in the `operations` register. |
| `cms/static/atheniq/` | Unity palette, switch and Studio skin. |
| `tasks/init.sh` | Assigns the theme to the deployment's sites on a fresh database. |

Course-card photographs are **not** stored here. They are one pool in
`../atheniq-theme/lms/static/images/courses/`, served at
`/static/atheniq/images/courses/…`, so the publisher, the catalog and the theme
cannot disagree about which picture a course has.

## Applying

The theme is installed by `contrib/tutor-atheniq-theme` (image rebuild) or by
`scripts/apply-atheniq-theme.sh` (bake into the running image). After either:

```bash
tutor local do settheme unity
```

The theme name and the setting are one string in the plugin, so they cannot
drift.
