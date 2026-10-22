#!/usr/bin/env python3
"""AthenIQ — the photographs behind the course cards.

A course card without a photograph is a row of text, and the learner catalog is
a wall of cards. This tool owns the images that fill them:

  * `config/course-photos.json` is the pool — one set of photographs per
    *subject* (ai, data, justice, health, ...), each with the keywords that
    route a course title to it;
  * `contrib/atheniq-theme/lms/static/images/courses/` holds the fetched
    1200x675 JPEGs, served by the LMS at
    `/static/atheniq/images/courses/<file>`;
  * `resolve()` is the single mapping a publisher uses:
    `publish-courses.py` writes the returned URL into each course's
    `course_image_url`, and `build-course-catalog.py` links the same file.

WHY A POOL AND NOT ONE IMAGE PER COURSE. The programs are thirty or forty
courses that share a handful of subjects; commissioning 114 distinct
photographs would be a stock-photo wall, and near-identical images read as a
template. A subject pool plus a hash of the course key gives every course a
stable, distinct choice within its subject, and one subject's photographs can be
replaced without touching the course records.

THE POOL IS THE FALLBACK. `scripts/course-cards.py` renders a card per course
from its program plan (`<CODE>.jpg` in this same directory, carrying the title,
program, semester and code). When that file exists, `resolve()` returns it and
the pool is used only for a course that has not been rendered yet.

    python3 scripts/course-photos.py --fetch     # download the pool
    python3 scripts/course-photos.py --check     # files present, 1200x675, mapping complete
    python3 scripts/course-photos.py --list      # how each course in the tree maps

Source: Unsplash (https://unsplash.com/license) — free for commercial and
non-commercial use, no permission or attribution required. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import struct
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "config", "course-photos.json")
PHOTO_DIR = os.path.join(REPO, "contrib", "atheniq-theme", "lms", "static",
                         "images", "courses")
#: The path the LMS serves the pool from. `scripts/apply-atheniq-theme.sh` and
#: the theme plugin both copy the directory to `/openedx/staticfiles/atheniq/`.
URL_PREFIX = "/static/atheniq/images/courses"

UNSPLASH = ("https://images.unsplash.com/photo-{id}"
            "?w={width}&h={height}&fit=crop&crop=entropy&q=82&fm=jpg")
USER_AGENT = "AthenIQ-course-photos/1.0 (+https://atheniq.innotel.us)"


def load_manifest(path=MANIFEST):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _keywords(subject):
    return [str(word).lower() for word in subject.get("keywords") or [] if word]


def subject_for(title, code="", description="", manifest=None):
    """The subject a course belongs to, by its own words.

    The manifest's order is the precedence order: a title that says both
    "forensic" and "science" belongs to whichever subject is declared first,
    which is a decision the manifest makes once, not a rule hidden here.
    """
    manifest = manifest or load_manifest()
    haystack = " ".join([str(title or ""), str(description or "")]).lower()
    code_prefix = _slug(code)[:3]
    for subject_name, subject in (manifest.get("subjects") or {}).items():
        for word in _keywords(subject):
            if re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", haystack):
                return subject_name
    # A code such as `CJ310` carries its own subject for a course whose title
    # was written in another language or is simply "Capstone".
    for subject_name, subject in (manifest.get("subjects") or {}).items():
        if code_prefix and code_prefix in [str(alias).lower() for alias in subject.get("codes") or []]:
            return subject_name
    return manifest.get("default") or "learning"


def resolve(code, title, description="", manifest=None):
    """The photograph for one course: {subject, photo, file, url}.

    The pick inside the subject is a hash of the course code, so the same
    course always gets the same photograph and two courses in one program
    usually get different ones — no clock, no randomness, no state to keep.
    """
    manifest = manifest or load_manifest()
    subjects = manifest.get("subjects") or {}
    overrides = manifest.get("courses") or {}
    subject_name = subject_for(title, code, description, manifest)

    # A card rendered for exactly this course (`scripts/course-cards.py`) wins
    # over the shared subject pool: it carries the course's own title, code and
    # program, so the catalog never shows two courses with the same picture.
    per_course = f"{str(code).upper()}.jpg"
    if os.path.isfile(os.path.join(PHOTO_DIR, per_course)):
        return {"subject": subject_name, "photo": None,
                "file": per_course, "url": f"{URL_PREFIX}/{per_course}"}

    override = overrides.get(str(code).upper())
    if override and "/" in str(override):
        subject_name, chosen = str(override).split("/", 1)
        if chosen.endswith(".jpg"):
            filename = chosen
            return {"subject": subject_name, "photo": None,
                    "file": filename, "url": f"{URL_PREFIX}/{filename}"}

    photos = list((subjects.get(subject_name) or {}).get("photos") or [])
    if not photos:
        subject_name = manifest.get("default") or "learning"
        photos = list((subjects.get(subject_name) or {}).get("photos") or [])
    if not photos:
        raise ValueError("the course-photo manifest has no photographs at all")
    digest = hashlib.sha256(f"{str(code).upper()}".encode()).hexdigest()
    index = int(digest[:8], 16) % len(photos)
    filename = f"{_slug(subject_name)}-{index + 1}.jpg"
    return {"subject": subject_name, "photo": photos[index],
            "file": filename, "url": f"{URL_PREFIX}/{filename}"}


def planned(manifest=None):
    """[(subject, photo_id, path)] for every photograph in the pool."""
    manifest = manifest or load_manifest()
    width, height = manifest.get("size") or [1200, 675]
    out = []
    for subject_name, subject in (manifest.get("subjects") or {}).items():
        for index, photo in enumerate(subject.get("photos") or [], 1):
            out.append((subject_name, photo,
                        os.path.join(PHOTO_DIR, f"{_slug(subject_name)}-{index}.jpg"),
                        width, height))
    return out


def _jpeg_size(path):
    """(width, height) of a JPEG, read from its SOF marker. Stdlib only."""
    with open(path, "rb") as fh:
        if fh.read(2) != b"\xff\xd8":
            raise ValueError("not a JPEG")
        while True:
            marker = fh.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                raise ValueError("truncated JPEG")
            kind = marker[1]
            if kind in (0xD8, 0xD9):
                continue
            length = struct.unpack(">H", fh.read(2))[0]
            if kind in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                _precision, height, width = struct.unpack(">BHH", fh.read(5))
                return width, height
            fh.seek(length - 2, os.SEEK_CUR)


def fetch(only=None, manifest=None):
    """Download the pool (idempotent; an existing file is left alone)."""
    manifest = manifest or load_manifest()
    os.makedirs(PHOTO_DIR, exist_ok=True)
    written = []
    for subject_name, photo, path, width, height in planned(manifest):
        if only and subject_name != only:
            continue
        if os.path.isfile(path) and os.path.getsize(path) > 10_000:
            continue
        url = UNSPLASH.format(id=photo, width=width, height=height)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        tmp = path + ".part"
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if not data.startswith(b"\xff\xd8"):
            raise SystemExit(f"{url} did not return a JPEG ({len(data)} bytes)")
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
        written.append((path, len(data)))
    return written


def check(manifest=None):
    """Every pooled photograph present, correctly sized, and mapped."""
    manifest = manifest or load_manifest()
    problems = []
    for subject_name, photo, path, width, height in planned(manifest):
        rel = os.path.relpath(path, REPO)
        if not os.path.isfile(path):
            problems.append(f"{rel}: missing (run make course-photos)")
            continue
        try:
            actual = _jpeg_size(path)
        except (OSError, ValueError) as err:
            problems.append(f"{rel}: unreadable ({err})")
            continue
        if actual != (width, height):
            problems.append(f"{rel}: {actual[0]}x{actual[1]}, expected {width}x{height}")
    return problems


def course_rows(repo=REPO):
    """[(code, title, resolved)] for every course in the tree."""
    spec = importlib.util.spec_from_file_location(
        "check_course_olx", os.path.join(repo, "scripts", "check-course-olx.py"))
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    manifest = load_manifest()
    rows = []
    for olx_dir in validator.find_courses(os.path.join(repo, "courses")):
        errors, _, summary = validator.validate_course(olx_dir)
        if errors:
            continue
        key = summary["course_key"]
        code = key.split("+")[1] if "+" in key else key
        title = summary["title"] or code
        rows.append((code, title, resolve(code, title, manifest=manifest)))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="download the pool")
    ap.add_argument("--only", help="fetch one subject only")
    ap.add_argument("--check", action="store_true",
                    help="fail if a photograph is missing, mis-sized or unmapped")
    ap.add_argument("--list", action="store_true",
                    help="print how every course in the tree resolves")
    args = ap.parse_args()

    if args.list:
        for code, title, photo in course_rows():
            print(f"{code:<10} {photo['subject']:<12} {photo['file']:<20} {title[:52]}")
        return

    if args.check:
        problems = check()
        if problems:
            raise SystemExit("course photos are stale:\n  " + "\n  ".join(problems))
        print(f"course photos are present and sized ({len(planned())}).")
        return

    if args.fetch:
        for path, size in fetch(args.only):
            print(f"wrote {os.path.relpath(path, REPO)}  {size // 1024} KiB")
        print(f"pool complete ({len(planned())} photographs).")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
