# AthenIQ theme overlay — LMS and Studio wear Unity

Files that white-label the Tutor platform (themed with **Indigo**) as
**AthenIQ**, in the Innotel Platform Stack's one theme, **Unity**
(`theme/unity-theme.css` in the platform stack; the canvas, ink, brand, status
and shape tokens this overlay names).

Both halves of the platform are covered by the same script. The Studio half used
to be copied in by hand after a deploy; it is now part of `make theme` and of the
baked image, exactly like the LMS footer.

## The LMS

| File | Replaces | Why |
| --- | --- | --- |
| `lms/templates/head-extra.html` | — (a new `<head>` hook) | Loads Unity and the LMS skin **before the first paint**, sets `data-scheme="desk"`, and adopts Indigo's dark-mode cookie into Unity's mode so the two switches cannot disagree. |
| `lms/templates/footer.html` | Indigo's footer | Drops the "Powered by: Tutor + Open edX" logo list and the edX trademark paragraph; lays out the mark, the platform statement and the three groups of places people actually go. |
| `lms/templates/index_overlay.html` | Indigo's overlay | Names the platform and states what the name means. |
| `lms/static/atheniq/unity-theme.css` | — | **The canonical Unity palette**, vendored byte-for-byte: three schemes × two modes and the shared primitives. |
| `lms/static/atheniq/unity-theme.js` | — | **The canonical Unity switch**, vendored byte-for-byte. Owns `data-mode` / `data-scheme` on `<html>`. |
| `lms/static/atheniq/atheniq-lms.css` | Indigo's compiled chrome | The LMS skin: header, footer, buttons, forms, tables, cards, course page and notices, every rule naming a Unity token. |
| `lms/static/atheniq/unity-light.css` / `unity-dark.css` | — | Paragon's `brandOverride` for the learner MFEs: the same palette expressed as `--pgn-*` variables, so every MFE is recolored without a bundle rebuild. |
| `lms/static/images/logo.png` / `logo-white.png` / `favicon.ico` | Indigo's marks | The AthenIQ mark. |
| `lms/static/images/courses/*.jpg` | — | The course-card photographs (see below). |

## Studio

| File | Replaces | Why |
| --- | --- | --- |
| `cms/templates/widgets/header.html` | Studio's header | Loads Unity in the **`operations`** register, keeps the Platform Services entry, and sets the scheme before content paints. |
| `cms/static/atheniq/unity-theme.css` | — | The same canonical Unity palette, for Studio's origin. |
| `cms/static/atheniq/unity-theme.js` | — | The same canonical switch. |
| `cms/static/atheniq/unity-cms.css` | Studio's chrome | Header, course navigation, buttons, forms, tables, the outline tree, status and dialogs — all Unity tokens; the editing surface stays light and legible. |

## Course photographs

`config/course-photos.json` is the pool: one set of photographs per **subject**
(ai, data, security, networks, software, business, finance, health, science,
justice, writing, support, leadership, learning). A course resolves to a subject
by its title, then to a photograph in that pool by a hash of its code — stable
across runs, varied within a program.

```bash
make course-photos         # fetch the pool (Unsplash, free for commercial use)
make check-course-photos   # every file present and 1200×675
python3 scripts/course-photos.py --list   # how each course resolves
```

`publish-courses.py` writes `/static/atheniq/images/courses/<file>` into every
course's `CourseOverview.course_image_url` when it publishes, so the card in
Explore and the same course's record in the LMS show the same picture.

## Applying

The templates and rasters live inside the LMS and CMS images under
`/openedx/themes/indigo/`, so copy them in and restart:

```bash
make images                # regenerate the brand rasters, if stale
make course-photos         # fetch the course photographs, if missing
make theme                 # == ./scripts/apply-atheniq-theme.sh
```

The script does not stop at the copy. `docker cp` into the running containers is
lost when they are recreated (`tutor local launch` stops and starts the
platform), so it also **bakes the files into the image the compose project
starts from** — one `COPY` layer over the upstream `overhangio/openedx` image,
built in seconds, with the untouched image kept as
`atheniq/openedx-theme-base:<tag>` for a rollback. It restarts **both** the LMS
and the CMS; `--no-restart` skips that, `--no-bake` is the old behaviour (a look
that the next recreate throws away).

For a deployment that rebuilds `openedx` from source instead, enable
[`../tutor-atheniq-theme`](../tutor-atheniq-theme): its Dockerfile patch copies
this overlay into the image, places the served static copies, and re-collects the
static assets, so `tutor images build openedx` produces the same result.

## The learner MFEs

The learner **MFEs** (catalog, learning, profile, …) do **not** render the LMS
footer template — they render their own footer from compiled JS bundles. Indigo
installs its `IndigoFooter` into the frontend-plugin-framework's footer slot, and
that footer still prints "Powered by" with the Tutor + Open edX logos and links to
`open.edx.org`. Because it is baked into the bundles, no template or config value
on the LMS can change it.

[`contrib/tutor-atheniq-mfe`](../tutor-atheniq-mfe) is a Tutor plugin that hides
Indigo's footer widgets at that slot and inserts the AthenIQ lockup instead. It
needs an MFE rebuild:

```bash
tutor plugins enable atheniqmfe
tutor config save
tutor images build mfe
tutor local launch
```

Without that rebuild, the LMS itself (footer, header, favicon, page titles,
emails) reads **AthenIQ**; only the MFE footer keeps the upstream badge.
