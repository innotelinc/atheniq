# AthenIQ — Brand

AthenIQ is a product of **Innotel Labs**, the LearningOps platform of the Innotel
Platform Stack. This page is the single reference for the mark, the palette, and how
the brand is named. When the landing page and the docs disagree with this page, this
page wins — update them together.

## The name

- **AthenIQ** — one word, capital A, capital IQ, no space, no hyphen. The wordmark
  sets a terminal period in the accent colour: `AthenIQ.`
- **The meaning** — a play on **Athene** (Athena), the Greek goddess of wisdom, and
  **IQ**, a measure of intelligence. *Athene + IQ*: wisdom, amplified. Say it
  "ATH-uh-nik". When the name is explained, keep the pairing — Athene **and** IQ —
  and never badge it with another platform's name; AthenIQ **is** the platform.
- **Innotel Labs** — the company. Use it in attribution: *"AthenIQ — an Innotel Labs
  product"* or *"© Innotel Labs"*.
- **Innotel Platform Stack** — the wider platform AthenIQ belongs to. Keep the
  product names (Authentik, Cerulean, ONYX, Magnate, Signara) capitalised as written.

## Logo

The mark is **Athene's owl, crowned by a spark**. Two large gradient eye-rings meet
at the brow and ring bright accent pupils; two ear tufts rise from the brow, a solid
beak sits between the eyes, and a four-point spark crowns the head — the owl for
wisdom, the spark for the IQ in the name. Drawn as one bold monoline in the brand
gradient, it stays legible from a favicon up to a hero. The 2026 refresh (much
heavier stroke, big touching eyes, a solid four-point spark) is defined once in the
`EYE_*` / `TUFTS` / `BEAK` / `SPARK` geometry in
[`scripts/build-course-images.py`](../scripts/build-course-images.py) and mirrored
exactly into every SVG — change them together.

| Asset | Use |
| --- | --- |
| [`web/landing/assets/atheniq-mark.svg`](../web/landing/assets/atheniq-mark.svg) | Icon/mark only, transparent background |
| [`web/landing/assets/atheniq-logo.svg`](../web/landing/assets/atheniq-logo.svg) | Horizontal lockup: mark + wordmark + "by Innotel Labs" |
| [`web/landing/assets/favicon.svg`](../web/landing/assets/favicon.svg) | Square tile, for favicons and app icons |

The SVG files above are the **vector masters**. Several consumers do not render SVG
— the LMS course card, Open Graph / social unfurls, and iOS/Android home-screen
icons — so rendered **PNG** versions ship alongside them, produced by
[`scripts/build-course-images.py`](../scripts/build-course-images.py) (`make images`,
verified by `make check-images`). Pillow is the only dependency.

| Raster | Size | Use |
| --- | --- | --- |
| [`web/landing/assets/favicon-32.png`](../web/landing/assets/favicon-32.png) | 32×32 | Browser tab |
| [`web/landing/assets/apple-touch-icon.png`](../web/landing/assets/apple-touch-icon.png) | 180×180 | Home-screen / app icon |
| [`web/landing/assets/atheniq-og.png`](../web/landing/assets/atheniq-og.png) | 1200×630 | Social / Open Graph card |
| `courses/<slug>/olx/static/<slug>-course-card.png` | 1200×675 | LMS course card (`course_image`) |

The same owl is inlined directly in the course-card SVGs under
`courses/<slug>/olx/static/`, each scaling the 64-unit geometry with its own gradient
(`url(#g)`).

When the mark, the palette, or the typography changes, regenerate the rasters with
`make images` in the same change — the generator mirrors the tokens and the mark
geometry documented here, so the two never drift apart.

Every landing/syllabus page also embeds the favicon **inline**, as a
`data:image/svg+xml` URI (`scripts/build-course-images.py:inline_favicon`). The
Innotel Platform Stack's conformity audit requires the icon to be self-contained,
and an inlined icon is cache-busted with the page itself, so it can never be served
stale from a separate URL. Update the SVG master and the embedded copy together;
the tests fail if they diverge.

**Clear space.** Leave at least the width of one eye-ring (≈ 1/3 of the mark) around
the mark on every side. Do not stretch, rotate, recolour, or add effects.

**Minimum size.** The mark is legible down to 20 px; below that use the favicon tile.

## Palette — emerald on slate

A dark, professional canvas with a single emerald accent. Success states use a
cooler teal so they never read as the same thing as the accent; "in progress" uses
amber.

| Token | Hex | Role |
| --- | --- | --- |
| `--p-bg` | `#0a1118` | Page background |
| `--p-bg-elevated` | `#101a22` | Cards, panels |
| `--p-surface` | `#16222c` | Raised surfaces |
| `--p-surface-hover` | `#1d2b36` | Hover fill |
| `--p-border` | `#22323d` | Hairlines and borders |
| `--p-text` | `#eef4f8` | Primary text |
| `--p-text-secondary` | `#c2cfd9` | Body/secondary text |
| `--p-text-muted` | `#93a4b1` | Captions, de-emphasised text |
| `--p-accent` | `#10b981` | Brand accent, links, primary actions |
| `--p-accent-hover` | `#34d399` | Accent hover |
| `--p-accent-tint` | `rgba(16, 185, 129, 0.12)` | Accent wash (kickers, chips) |
| `--p-success` | `#2dd4bf` | "Live"/"done" states |
| `--p-gold` | `#fbbf24` | "Next"/warning states |

The logo gradient runs `#059669 → #10b981 → #34d399`. The tokens are defined once, at
the top of [`web/landing/index.html`](../web/landing/index.html); keep any new surface
on the same names.

## Typography

System sans-serif: `ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue",
sans-serif`. Code and commands use a monospace stack. The wordmark is set heavy
(700) with slight positive letter-spacing.

## Colour and accessibility

- Body text is `--p-text-secondary` or brighter on the dark canvas; never place
  `--p-text-muted` body copy.
- Primary buttons are emerald with `--p-bg`-coloured text — keep the pair; white on
  emerald fails contrast.
- Never convey state by colour alone; pair `--p-success` / `--p-gold` with a label.

## Changing the brand

Update the three SVGs, the token block in the landing page, and this page in one
change so the palette and the assets never drift apart. Then regenerate the rasters
and the pages that embed the favicon:

```bash
make images catalog syllabus   # rasters + generated pages
make check-images check-brand check-catalog check-syllabus
```

`check-brand` is the guard that keeps the two copies honest: it rebuilds the
expected SVG fragments from the geometry in
[`scripts/build-course-images.py`](../scripts/build-course-images.py) and fails if
any SVG — or the favicon's derived tile transform — has drifted.

The live LMS takes its name from `PLATFORM_NAME` and its footer from
[`contrib/atheniq-theme`](../contrib/atheniq-theme); keep them in step with this
page (see [docs/Deployment.md](Deployment.md#branding--the-platform-is-atheniq)).
