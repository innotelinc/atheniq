#!/usr/bin/env python3
"""AthenIQ — render one course card per course, from its program and title.

The catalog's cards were photographs only: a subject pool shared by every course
in that subject, so two courses of one program could show the same picture and
nothing on the card said *which* course it was. This renderer composes a card
that belongs to exactly one course:

    <program>            eyebrow, e.g. BUSINESS ADMINISTRATION
    <semester line>      e.g. Semester 3 — Market Dynamics
    <course title>       the card's own headline, wrapped and auto-fitted
    <CODE> <credits>     the course code chip and term
    <credential>         e.g. Bachelor of Business Administration

The photograph still comes from `scripts/course-photos.py` (the subject pool,
picked by a hash of the code), but it is graded into the brand background and
carries the course's own words, so no two cards read the same.

    python3 scripts/course-cards.py --programs DIR --out DIR
    python3 scripts/course-cards.py --programs DIR --out DIR --check
    python3 scripts/course-cards.py --programs DIR --out DIR --list

The output is a 1600x900 JPEG per course (`<CODE>.jpg`) plus `cards.json`, the
manifest `publish-courses.py --cards` reads to upload each card to its course.
Pillow is the only third-party dependency; the palette and mark come from
`docs/Brand.md`, the same tokens `build-course-images.py` renders.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(REPO, "contrib", "atheniq-theme", "lms", "static",
                         "images", "courses")

CARD_SIZE = (1600, 900)

# -- Brand tokens (mirrors docs/Brand.md) -----------------------------------
BG_TOP = (8, 16, 24)
BG_BOTTOM = (13, 27, 35)
TEXT = (238, 244, 248)
MUTED = (174, 190, 202)
FAINT = (120, 140, 154)
ACCENT = (52, 211, 153)
ACCENT_DEEP = (16, 185, 129)
CHIP_TEXT = (110, 231, 183)
CHIP_BG = (16, 185, 129)

FONTS = {
    "black": ["/usr/share/fonts/truetype/lato/Lato-Black.ttf",
              "/usr/share/fonts/truetype/lato/Lato-Heavy.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "bold": ["/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semibold": ["/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
                 "/usr/share/fonts/truetype/lato/Lato-Bold.ttf"],
    "regular": ["/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # tests import this module; keep it importable without Pillow
    Image = ImageDraw = ImageFilter = ImageFont = None


def _photos():
    path = os.path.join(REPO, "scripts", "course-photos.py")
    spec = importlib.util.spec_from_file_location("atheniq_course_photos", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _font(weight, size):
    for path in FONTS[weight]:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


# -- layout helpers ----------------------------------------------------------

def _spaced(draw, xy, text, font, fill, tracking=0.0):
    """Draw text with letter-spacing; returns the width drawn."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + tracking
    return x - xy[0]


def _spaced_width(draw, text, font, tracking=0.0):
    return sum(draw.textlength(char, font=font) + tracking for char in text) - tracking


def _wrap(draw, text, font, max_width):
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _fit_title(draw, text, max_width, max_lines=3, largest=92, smallest=54):
    """The biggest bold size whose wrapped title fits the box."""
    size = largest
    while size >= smallest:
        font = _font("bold", size)
        lines = _wrap(draw, text, font, max_width)
        widest = max((draw.textlength(line, font=font) for line in lines), default=0)
        if len(lines) <= max_lines and widest <= max_width:
            return font, lines, size
        size -= 2
    # A single unbreakable word can still be too wide at the floor: split it
    # rather than let it run under the photograph.
    font = _font("bold", smallest)
    lines = _wrap(draw, text, font, max_width)[:max_lines]
    fixed = []
    for line in lines:
        while draw.textlength(line, font=font) > max_width and len(line) > 1:
            cut = len(line)
            while cut > 1 and draw.textlength(line[:cut], font=font) > max_width:
                cut -= 1
            fixed.append(line[:cut])
            line = line[cut:]
        fixed.append(line)
    return font, fixed[:max_lines], smallest


def _gradient(size, top, bottom):
    width, height = size
    strip = Image.new("RGB", (1, height))
    px = strip.load()
    for y in range(height):
        k = y / max(1, height - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * k) for i in range(3))
    return strip.resize(size, Image.BILINEAR)


def _glow(size, center, radius, color, strength=64):
    """A soft radial accent glow, drawn as one blurred disc."""
    layer = Image.new("L", size, 0)
    ImageDraw.Draw(layer).ellipse(
        [center[0] - radius, center[1] - radius,
         center[0] + radius, center[1] + radius], fill=strength)
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 3))
    tint = Image.new("RGB", size, color)
    return tint, layer


def _cover(image, box):
    """Crop-to-fill `image` into `box`, centred on the more interesting half."""
    width, height = box
    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h)
    resized = image.resize((max(1, round(src_w * scale)), max(1, round(src_h * scale))),
                           Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def render_card(entry, photo_path):
    """Compose one card; returns a PIL image."""
    if Image is None:
        raise SystemExit("Pillow is required to render course cards: pip install Pillow")
    width, height = CARD_SIZE
    canvas = _gradient(CARD_SIZE, BG_TOP, BG_BOTTOM)

    # The photograph occupies the right 60%, faded into the background on the
    # left so the title never sits on a busy edge.
    photo_w = int(width * 0.60)
    photo = Image.open(photo_path).convert("RGB")
    photo = _cover(photo, (photo_w, height))
    photo = Image.blend(photo, Image.new("RGB", photo.size, (10, 32, 30)), 0.10)
    dark = Image.new("RGB", photo.size, (4, 9, 13))
    photo = Image.blend(photo, dark, 0.22)
    x0 = width - photo_w
    mask = Image.new("L", (photo_w, height), 0)
    mdraw = ImageDraw.Draw(mask)
    for x in range(photo_w):
        k = min(1.0, max(0.0, (x - photo_w * 0.22) / (photo_w * 0.40)))
        mdraw.line([(x, 0), (x, height)], fill=round(255 * k))
    canvas.paste(photo, (x0, 0), mask)

    # A quiet emerald glow where the photograph meets the copy.
    tint, layer = _glow(CARD_SIZE, (int(width * 0.52), int(height * 0.26)),
                        int(height * 0.55), ACCENT_DEEP, strength=52)
    canvas = Image.composite(tint, canvas, layer)

    draw = ImageDraw.Draw(canvas)
    left = 96
    # The copy column stops where the photograph starts fading in, so no line
    # ever sits on a busy part of the image.
    content_w = min(700, width - photo_w - left)

    # Wordmark.
    mark_font = _font("black", 30)
    draw.text((left, 66), "AthenIQ", font=mark_font, fill=TEXT)
    dot_w = draw.textlength("AthenIQ", font=mark_font)
    draw.ellipse([left + dot_w + 3, 88, left + dot_w + 12, 97], fill=ACCENT)
    draw.text((left, 106), "INNOTEL LABS", font=_font("semibold", 14), fill=FAINT)

    # Eyebrow: the program, then the semester it belongs to.
    eyebrow_y = 300
    eyebrow_font = _font("bold", 24)
    eyebrow = str(entry.get("program") or "AthenIQ").upper()
    _spaced(draw, (left, eyebrow_y), eyebrow[:46], eyebrow_font, ACCENT, tracking=2.2)

    semester = str(entry.get("semester") or "").strip()
    if semester:
        draw.text((left, eyebrow_y + 42), semester[:58],
                  font=_font("regular", 20), fill=MUTED)

    # Title.
    title = str(entry.get("title") or entry.get("code") or "Course")
    font, lines, size = _fit_title(draw, title, content_w, largest=84, smallest=50)
    y = 400
    for line in lines:
        draw.text((left, y), line, font=font, fill=TEXT)
        y += round(size * 1.12)

    # Code chip + credits/term.
    chip_y = min(y + 18, 700)
    chip_font = _font("bold", 22)
    code = str(entry.get("code") or "").upper()
    chip_w = draw.textlength(code, font=chip_font) + 32
    draw.rounded_rectangle([left, chip_y, left + chip_w, chip_y + 44], radius=10,
                           fill=(16, 44, 38), outline=(52, 211, 153), width=2)
    draw.text((left + 16, chip_y + 8), code, font=chip_font, fill=CHIP_TEXT)
    meta = []
    if entry.get("credits") is not None:
        meta.append(f"{entry['credits']} credits")
    if entry.get("term"):
        meta.append(str(entry["term"]).replace("_", " "))
    if meta:
        draw.text((left + chip_w + 20, chip_y + 11), "  ·  ".join(meta),
                  font=_font("regular", 20), fill=MUTED)

    # Credential, pinned to the bottom.
    credential = str(entry.get("credential") or "").strip()
    draw.line([(left, 800), (left + content_w, 800)], fill=(38, 58, 70), width=1)
    if credential:
        draw.text((left, 822), credential[:72], font=_font("regular", 20), fill=FAINT)
    return canvas


def course_entries(programs_dir, term=None):
    """[(entry, photo_path)] for every course in every program file."""
    photos = _photos()
    manifest = photos.load_manifest()
    out = []
    seen = set()
    names = sorted(name for name in os.listdir(programs_dir) if name.endswith(".json"))
    for name in names:
        with open(os.path.join(programs_dir, name), encoding="utf-8") as fh:
            program = json.load(fh)
        program_name = program.get("name") or program.get("id") or name[:-5]
        credential = program.get("credential") or ""
        program_term = term or _term_label(program.get("startTerm"))
        for semester in program.get("semesters") or []:
            semester_name = semester.get("name") or ""
            for course in semester.get("courses") or []:
                code = str(course.get("code") or "").strip().upper()
                if not code or code in seen:
                    continue
                seen.add(code)
                title = str(course.get("title") or code)
                resolved = photos.resolve(code, title, course.get("description") or "",
                                          manifest=manifest)
                entry = {
                    "code": code,
                    "title": title,
                    "program": program_name,
                    "credential": credential,
                    "semester": semester_name,
                    "credits": course.get("credits"),
                    "term": program_term,
                    "description": course.get("description") or "",
                }
                out.append((entry, os.path.join(PHOTO_DIR, resolved["file"])))
    return out


def _term_label(start):
    """The cohort label on a card: the program's own words when it has them.

    `startTerm` is human-facing ("Spring 2027", "Fall 2026", "2027_T1"); the
    card prints it rather than inventing a quarter from the year, which is what
    made every spring cohort read as `2027_T4`.
    """
    return str(start or "").strip()


def build(programs_dir, out_dir, term=None):
    """Render every card; returns the manifest written to `cards.json`."""
    os.makedirs(out_dir, exist_ok=True)
    cards = []
    for entry, photo in course_entries(programs_dir, term):
        if not os.path.isfile(photo):
            raise SystemExit(f"{entry['code']}: no photograph at {photo}")
        image = render_card(entry, photo)
        path = os.path.join(out_dir, f"{entry['code']}.jpg")
        image.save(path, "JPEG", quality=92, optimize=True, progressive=True)
        cards.append({**entry, "file": os.path.basename(path),
                      "bytes": os.path.getsize(path)})
    manifest = {"size": list(CARD_SIZE), "cards": cards}
    with open(os.path.join(out_dir, "cards.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--programs", required=True, help="directory of program JSON files")
    ap.add_argument("--out", default=PHOTO_DIR, help="output directory for the cards")
    ap.add_argument("--term", help="override the term label, e.g. 2026_T4")
    ap.add_argument("--check", action="store_true", help="verify cards exist and are sized")
    ap.add_argument("--list", action="store_true", help="print the planned cards")
    args = ap.parse_args()

    if args.check:
        missing = []
        for entry, _photo in course_entries(args.programs, args.term):
            path = os.path.join(args.out, f"{entry['code']}.jpg")
            if not os.path.isfile(path):
                missing.append(entry["code"])
        if missing:
            raise SystemExit("course cards missing: " + ", ".join(missing))
        print(f"course cards are present ({len(course_entries(args.programs, args.term))}).")
        return

    if args.list:
        for entry, photo in course_entries(args.programs, args.term):
            print(f"{entry['code']:<9} {entry['program'][:22]:<24} "
                  f"{os.path.basename(photo):<16} {entry['title'][:44]}")
        return

    manifest = build(args.programs, args.out, args.term)
    print(f"wrote {len(manifest['cards'])} cards to {os.path.relpath(args.out, REPO)}")


if __name__ == "__main__":
    main()
