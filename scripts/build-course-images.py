#!/usr/bin/env python3
"""AthenIQ — render the brand and course-card raster (PNG) assets.

The repository keeps the *vector masters* as SVG: `web/landing/assets/*.svg` and
each course's `static/<slug>-course-card.svg`. Some consumers, though, do not
render SVG at all:

  * the Open edX **course card** (Studio's "Course Card Image") wants a raster;
  * social unfurlers (Open Graph / Twitter cards) reject SVG;
  * iOS/Android home-screen icons (`apple-touch-icon`) must be PNG.

So this script renders PNG rasters from the same brand spec with Pillow. It is
the tool that closes the "no SVG rasteriser installed" gap: no `rsvg-convert`,
ImageMagick, or headless browser is required — only Pillow.

It emits:

  * `web/landing/assets/favicon-32.png`        32×32   (browser tab)
  * `web/landing/assets/apple-touch-icon.png`  180×180 (home screen)
  * `web/landing/assets/atheniq-og.png`        1200×630 (social card)
  * `courses/<slug>/olx/static/<slug>-course-card.png`  1200×675 (LMS card)

Both the SVG masters and these rasters derive from `docs/Brand.md`; keep the
palette, the mark geometry, and this file in step.

Usage:
    python3 scripts/build-course-images.py           # write every raster
    python3 scripts/build-course-images.py --check   # verify they exist + sized
    python3 scripts/build-course-images.py --list    # print the planned outputs

Pillow is the only third-party dependency (`pip install Pillow`). The `--check`
mode deliberately verifies *presence and dimensions*, not byte equality, so it
is stable across Pillow versions; regenerate with `make images`.
"""
import argparse
import base64
import importlib.util
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(REPO, "web", "landing", "assets")
COURSES_DIR = os.path.join(REPO, "courses")
TRACKS_FILE = os.path.join(REPO, "config", "workforce-tracks.json")

# A course card is authored at 800×450 in the SVG; we render the LMS/OG raster
# at 16:9 1200×675 (1.5×) so Studio's course card is crisp on hi-DPI displays.
CARD_SIZE = (1200, 675)
CARD_SCALE = 1.5

# --- Brand tokens (mirrors docs/Brand.md) ---------------------------------
BG = (10, 17, 24)          # --p-bg        #0a1118
TILE_BG = (11, 18, 32)     # favicon tile  #0b1220
TEXT = (238, 244, 248)     # --p-text      #eef4f8
MUTED = (147, 164, 177)    # --p-text-muted #93a4b1
ACCENT_HOVER = (52, 211, 153)   # --p-accent-hover #34d399
ACCENT = (16, 185, 129)    # --p-accent    #10b981
NODE = (110, 231, 183)     # trailing orbit node #6ee7b7
RING = (52, 211, 153, 115)  # orbit stroke, ~0.45 alpha
GRADIENT_STOPS = [(0.0, (5, 150, 105)), (0.55, (16, 185, 129)), (1.0, (52, 211, 153))]

try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except ImportError:  # tests import this module; keep it importable without Pillow
    HAVE_PIL = False

FONT_CANDIDATES = {
    "bold": ["/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semibold": ["/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
                 "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}


def _require_pil():
    if not HAVE_PIL:
        raise SystemExit("Pillow is required for image rendering: pip install Pillow")


def _font(weight, size):
    for path in FONT_CANDIDATES[weight]:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    # Pillow >= 10 bundles a scalable default face.
    return ImageFont.load_default(size=size)


def inline_favicon(repo=REPO):
    """The favicon as a self-contained `data:` URI.

    The Innotel Platform Stack's conformity audit requires every landing page to
    carry a *self-contained* SVG favicon, so it is embedded in the page rather
    than linked. An inlined icon is also cache-busted with the page itself — it
    can never be served stale from a separate URL.
    """
    path = os.path.join(repo, "web", "landing", "assets", "favicon.svg")
    with open(path) as fh:
        svg = fh.read().strip()
    svg = re.sub(r">\s+<", "><", svg)
    svg = re.sub(r"\s{2,}", " ", svg)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_module("check_course_olx", os.path.join(REPO, "scripts", "check-course-olx.py"))


# --- Palette / gradient helpers -------------------------------------------

def _sample_stops(stops, t):
    t = max(0.0, min(1.0, t))
    for i in range(1, len(stops)):
        p0, c0 = stops[i - 1]
        p1, c1 = stops[i]
        if t <= p1:
            span = (p1 - p0) or 1.0
            k = (t - p0) / span
            return tuple(round(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
    return stops[-1][1]


def _gradient(size, stops=GRADIENT_STOPS):
    """A cached diagonal (bottom-left → top-right) gradient, resized to size."""
    n = 256
    small = Image.new("RGB", (n, n))
    px = small.load()
    for y in range(n):
        for x in range(n):
            px[x, y] = _sample_stops(stops, (x + (n - 1 - y)) / (2 * (n - 1)))
    return small.resize(size, Image.BILINEAR)


# --- The mark (ascending chevrons through a slanted orbit) ----------------

def _draw_mark(base, ox, oy, scale):
    """Draw the brand mark at (ox, oy) in 64-unit space, scaled by `scale`."""
    size = int(round(64 * scale))
    pad = int(round(10 * scale))
    side = size + 2 * pad

    def pt(x, y):
        return (pad + x * scale, pad + y * scale)

    # Orbit ring: an ellipse, rotated -18° about its centre.
    ring = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring)
    cx, cy = pt(32, 30)
    rx, ry = 27 * scale, 10 * scale
    ring_draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                      outline=RING, width=max(1, round(1.6 * scale)))
    ring = ring.rotate(-18, resample=Image.BICUBIC, center=(cx, cy))

    # Chevrons: two nested "V" strokes, filled with the brand gradient.
    stroke = max(1, round(7 * scale))
    mask = Image.new("L", (side, side), 0)
    mask_draw = ImageDraw.Draw(mask)
    # Each chevron is a two-segment "V"; round its joints and caps by stamping
    # circles at every vertex (Pillow lines support joint="curve" but not caps).
    for apex, (left, right) in (((32, 27), ((15, 44), (49, 44))),
                                ((32, 22), ((23, 31), (41, 31)))):
        vertices = [left, apex, right]
        mask_draw.line([pt(*v) for v in vertices], fill=255, width=stroke, joint="curve")
        for x, y in (pt(*v) for v in vertices):
            r = stroke / 2
            mask_draw.ellipse([x - r, y - r, x + r, y + r], fill=255)

    chevrons = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    chevrons.paste(_gradient((side, side)).convert("RGBA"), (0, 0), mask)

    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    tile.alpha_composite(ring)
    tile.alpha_composite(chevrons)
    node = ImageDraw.Draw(tile)
    nx, ny = pt(57, 22)
    nr = 2.6 * scale
    node.ellipse([nx - nr, ny - nr, nx + nr, ny + nr], fill=NODE)

    base.paste(tile, (int(round(ox - pad)), int(round(oy - pad))), tile)


# --- Text helpers ----------------------------------------------------------

def _tracked(draw, xy, text, font, fill, tracking):
    """Draw text with letter-spacing (Pillow has no native tracking)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


def _fit_font(text, weight, size, max_width, min_size=28):
    font = _font(weight, size)
    while size > min_size and _draw_textlength(text, font) > max_width:
        size -= 2
        font = _font(weight, size)
    return font


def _draw_textlength(text, font):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    return probe.textlength(text, font=font)


# --- Assets ----------------------------------------------------------------

def render_course_card(code, title, subtitle):
    """One 1200×675 Open edX course card, 16:9."""
    _require_pil()
    width, height = CARD_SIZE
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    _draw_mark(img, ox=84, oy=144, scale=2.6 * CARD_SCALE)

    draw = ImageDraw.Draw(img)
    _tracked(draw, (84, 495), code, _font("bold", round(39)), ACCENT_HOVER, 4.5)

    title_font = _fit_font(title, "bold", round(60), width - 84 - 56)
    draw.text((84, 564), title, font=title_font, fill=TEXT)
    draw.text((84, 618), subtitle, font=_font("regular", round(27)), fill=MUTED)
    return img


def render_mark_tile(size):
    """A square app-icon tile: brand mark on a rounded slate square."""
    _require_pil()
    img = Image.new("RGBA", (size, size), TILE_BG + (255,))
    radius = max(2, round(size * 14 / 64))
    # Rounded corners are the only transparency; keep the tile opaque elsewhere.
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.putalpha(mask)

    scale = size * 0.78 / 64
    ox = (size - 64 * scale) / 2
    oy = (size - 64 * scale) / 2
    _draw_mark(img, ox, oy, scale)
    return img


def render_og_card():
    """1200×630 social card: mark, wordmark, and the tagline."""
    _require_pil()
    width, height = 1200, 630
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    _draw_mark(img, ox=110, oy=190, scale=4.4)

    draw = ImageDraw.Draw(img)
    # Emphasise the wordmark's terminal period in the accent colour.
    end = _tracked(draw, (440, 236), "AthenIQ", _font("bold", 88), TEXT, 1.5)
    draw.text((end + 6, 236), ".", font=_font("bold", 88), fill=ACCENT_HOVER)
    draw.text((444, 352), "Learn what's real.", font=_font("semibold", 34), fill=ACCENT_HOVER)
    draw.text((444, 400), "Open learning platform · Innotel Labs", font=_font("regular", 26), fill=MUTED)

    draw.rectangle([110, 470, 1090, 472], fill=(34, 50, 61))
    return img


# --- Model -----------------------------------------------------------------

def course_models(repo=REPO):
    """Every shipped course as {slug, code, title, subtitle}."""
    track_by_key = {}
    try:
        doc = json.load(open(os.path.join(repo, "config", "workforce-tracks.json")))
    except FileNotFoundError:
        doc = {"tracks": []}
    for track in doc.get("tracks", []):
        for key in track.get("courses", []):
            track_by_key[key] = track.get("title") or track.get("id")

    models = []
    for olx_dir in VALIDATOR.find_courses(os.path.join(repo, "courses")):
        _, _, summary = VALIDATOR.validate_course(olx_dir)
        key = summary["course_key"]
        parts = key.split("+")
        code = parts[1] if len(parts) > 1 else key
        title = summary["title"] or code
        track = track_by_key.get(key)
        subtitle = (f"Innotel Labs · {track} track" if track
                    else "Innotel Labs · platform reference course")
        slug = os.path.basename(os.path.dirname(olx_dir))
        models.append({"slug": slug, "code": code, "title": title, "subtitle": subtitle,
                       "olx": olx_dir})
    return models


def planned_outputs(repo=REPO):
    """Return [(path, (width, height))] for every raster this tool owns."""
    out = [
        (os.path.join(repo, "web", "landing", "assets", "favicon-32.png"), (32, 32)),
        (os.path.join(repo, "web", "landing", "assets", "apple-touch-icon.png"), (180, 180)),
        (os.path.join(repo, "web", "landing", "assets", "atheniq-og.png"), (1200, 630)),
    ]
    for course in course_models(repo):
        out.append((os.path.join(course["olx"], "static",
                                 f"{course['slug']}-course-card.png"), CARD_SIZE))
    return out


def build_all(repo=REPO):
    """Render every asset; return [(path, PIL.Image)]."""
    _require_pil()
    rendered = [
        (os.path.join(repo, "web", "landing", "assets", "favicon-32.png"), render_mark_tile(32)),
        (os.path.join(repo, "web", "landing", "assets", "apple-touch-icon.png"), render_mark_tile(180)),
        (os.path.join(repo, "web", "landing", "assets", "atheniq-og.png"), render_og_card()),
    ]
    for course in course_models(repo):
        image = render_course_card(course["code"], course["title"], course["subtitle"])
        rendered.append((os.path.join(course["olx"], "static",
                                      f"{course['slug']}-course-card.png"), image))
    return rendered


def check(repo=REPO):
    """Presence + dimension check (stable across Pillow versions)."""
    _require_pil()
    problems = []
    for path, size in planned_outputs(repo):
        rel = os.path.relpath(path, repo)
        if not os.path.isfile(path):
            problems.append(f"{rel}: missing (run make images)")
            continue
        try:
            with Image.open(path) as img:
                if img.size != size:
                    problems.append(f"{rel}: {img.size[0]}×{img.size[1]}, expected "
                                    f"{size[0]}×{size[1]}")
        except Exception as exc:  # pragma: no cover - corrupt file
            problems.append(f"{rel}: not a readable PNG ({exc})")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if a raster is missing or mis-sized")
    ap.add_argument("--list", action="store_true", help="print the planned outputs and exit")
    args = ap.parse_args()

    if args.list:
        for path, size in planned_outputs():
            print(f"{os.path.relpath(path, REPO)}  {size[0]}×{size[1]}")
        return

    if args.check:
        problems = check()
        if problems:
            raise SystemExit("image assets are stale:\n  " + "\n  ".join(problems))
        print(f"image assets are present and sized ({len(planned_outputs())}).")
        return

    for path, image in build_all():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        image.save(path, "PNG", optimize=True)
        print(f"wrote {os.path.relpath(path, REPO)}  {image.size[0]}×{image.size[1]}")


if __name__ == "__main__":
    main()
