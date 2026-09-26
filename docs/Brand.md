# AthenIQ — Brand

AthenIQ is a product of **Innotel Labs**, the LearningOps platform of the Innotel
Platform Stack. This page is the single reference for the mark, the palette, and how
the brand is named. When the landing page and the docs disagree with this page, this
page wins — update them together.

## The name

- **AthenIQ** — one word, capital A, capital IQ, no space, no hyphen. The wordmark
  sets a terminal period in the accent colour: `AthenIQ.`
- **Innotel Labs** — the company. Use it in attribution: *"AthenIQ — an Innotel Labs
  product"* or *"© Innotel Labs"*.
- **Innotel Platform Stack** — the wider platform AthenIQ belongs to. Keep the
  product names (Authentik, Cerulean, ONYX, Magnate, Signara) capitalised as written.

## Logo

The mark is **ascending chevrons with an orbit** — progress and certification, in
motion. Two nested chevrons rise through a slanted orbit ring with a trailing node.

| Asset | Use |
| --- | --- |
| [`web/landing/assets/atheniq-mark.svg`](../web/landing/assets/atheniq-mark.svg) | Icon/mark only, transparent background |
| [`web/landing/assets/atheniq-logo.svg`](../web/landing/assets/atheniq-logo.svg) | Horizontal lockup: mark + wordmark + "by Innotel Labs" |
| [`web/landing/assets/favicon.svg`](../web/landing/assets/favicon.svg) | Square tile, for favicons and app icons |

The SVG files above are the **vector masters**. Several consumers do not render SVG
— the Open edX course card, Open Graph / social unfurls, and iOS/Android home-screen
icons — so rendered **PNG** versions ship alongside them, produced by
[`scripts/build-course-images.py`](../scripts/build-course-images.py) (`make images`,
verified by `make check-images`). Pillow is the only dependency.

| Raster | Size | Use |
| --- | --- | --- |
| [`web/landing/assets/favicon-32.png`](../web/landing/assets/favicon-32.png) | 32×32 | Browser tab |
| [`web/landing/assets/apple-touch-icon.png`](../web/landing/assets/apple-touch-icon.png) | 180×180 | Home-screen / app icon |
| [`web/landing/assets/atheniq-og.png`](../web/landing/assets/atheniq-og.png) | 1200×630 | Social / Open Graph card |
| `courses/<slug>/olx/static/<slug>-course-card.png` | 1200×675 | LMS course card (`course_image`) |

When the mark, the palette, or the typography changes, regenerate the rasters with
`make images` in the same change — the generator mirrors the tokens and the mark
geometry documented here, so the two never drift apart.

**Clear space.** Leave at least the width of one chevron (≈ 1/4 of the mark) around
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
change so the palette and the assets never drift apart.
