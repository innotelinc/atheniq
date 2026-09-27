# AthenIQ LMS theme overlay

Files that white-label the Tutor LMS (themed with **Indigo**) as **AthenIQ**:

| File | Replaces | Why |
| --- | --- | --- |
| `lms/templates/footer.html` | Indigo's footer | Drops the "Powered by: Tutor + Open edX" logo list and the edX trademark paragraph; shows an AthenIQ copyright. |
| `lms/templates/index_overlay.html` | Indigo's overlay | Names the platform and states what the name means. |
| `lms/static/images/logo.png` | Indigo's header logo | The AthenIQ mark (light header). |
| `lms/static/images/logo-white.png` | Indigo's dark-header logo | The AthenIQ mark (dark header). |
| `lms/static/images/favicon.ico` | Indigo's favicon | The AthenIQ favicon tile. |

The `lms/static/images/*.png` / `*.ico` files are **generated** — render them with
`make images` (they come from the same mark geometry as the landing-page assets;
see [docs/Brand.md](../../docs/Brand.md)).

The `PLATFORM_NAME` itself is a Tutor config value, not a template — set it with:

```bash
tutor config save --set PLATFORM_NAME=AthenIQ
```

## Applying

The templates and rasters live inside the LMS image under
`/openedx/themes/indigo/`, so copy them in and restart:

```bash
make images            # regenerate the rasters first, if stale
make theme             # == ./scripts/apply-atheniq-theme.sh
```

That is an operational convenience: the copies live in the container's writable
layer and are lost when the container is recreated (`tutor local launch`). To make
them permanent, fold them into a Tutor theme plugin and `tutor images build
openedx`.

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
