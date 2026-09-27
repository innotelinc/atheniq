#!/usr/bin/env python3
"""AthenIQ — fail if the owl mark drifts between the generator and the SVG masters.

The mark is defined once, as geometry, in `scripts/build-course-images.py`
(`EYE_*`, `TUFTS`, `BEAK`, `SPARK`). Every SVG — the three brand masters and each
course card — is a hand-maintained copy of that geometry, and the **favicon tile
transform** is derived from the same bounds. When one side changes without the
other, the raster and vector logos silently disagree.

This check rebuilds the expected SVG fragments from the geometry and asserts each
SVG contains them (colours and `url(#…)` paint are normalised away, so a card may
use `url(#g)` where a master uses `url(#atheniq-owl)`).

    python3 scripts/check-brand-mark.py          # human output
    python3 scripts/check-brand-mark.py --json   # machine output

Exit codes: 0 in sync, 1 drifted.
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_images(repo=REPO):
    path = os.path.join(repo, "scripts", "build-course-images.py")
    spec = importlib.util.spec_from_file_location("atheniq_build_course_images", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IMAGES = _load_images()


def _num(value):
    """Format a coordinate the way the SVGs do: trim trailing zeros."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text if text else "0"


def expected_fragments():
    """The exact SVG substrings the shared geometry must produce."""
    frags = []
    for (bx, by), (tx, ty) in IMAGES.TUFTS:
        frags.append(f"M{_num(bx)} {_num(by)} L{_num(tx)} {_num(ty)}")
    for cx, cy in IMAGES.EYE_RINGS:
        frags.append(f'cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(IMAGES.EYE_R)}"')
    for cx, cy in IMAGES.EYE_RINGS:
        frags.append(f'cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(IMAGES.PUPIL_R)}"')
    frags.append("M" + " L".join(f"{_num(x)} {_num(y)}" for x, y in IMAGES.BEAK) + " Z")
    frags.append("M" + " L".join(f"{_num(x)} {_num(y)}" for x, y in IMAGES.SPARK) + " Z")
    frags.append(f'stroke-width="{_num(IMAGES.EYE_STROKE)}"')
    return frags


def normalize(text):
    """Drop the paint choice and collapse whitespace, so cards and masters align."""
    text = re.sub(r"url\(#[^)]*\)", "url(#G)", text)
    return re.sub(r"\s+", " ", text)


def svg_targets(repo=REPO):
    """The brand masters plus every course-card SVG."""
    targets = [
        os.path.join(repo, "web", "landing", "assets", "atheniq-mark.svg"),
        os.path.join(repo, "web", "landing", "assets", "atheniq-logo.svg"),
        os.path.join(repo, "web", "landing", "assets", "favicon.svg"),
    ]
    targets += sorted(glob.glob(os.path.join(repo, "courses", "*", "olx", "static",
                                             "*-course-card.svg")))
    return targets


def check(repo=REPO):
    """Return a list of human-readable drift problems (empty == in sync)."""
    frags = expected_fragments()
    transform = f'transform="{IMAGES.favicon_transform_attr()}"'
    problems = []
    for path in svg_targets(repo):
        rel = os.path.relpath(path, repo)
        if not os.path.isfile(path):
            problems.append(f"{rel}: missing")
            continue
        body = normalize(open(path, encoding="utf-8").read())
        for frag in frags:
            if frag not in body:
                problems.append(f"{rel}: missing mark geometry `{frag}`")
        if rel.endswith("favicon.svg") and transform not in body:
            problems.append(
                f"{rel}: favicon transform is not {transform} "
                "(derive it with build-course-images.favicon_transform_attr())")
    return problems


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    targets = svg_targets()
    problems = check()

    if args.json:
        print(json.dumps({"svgs": [os.path.relpath(p, REPO) for p in targets],
                          "problems": problems, "in_sync": not problems},
                         indent=2, sort_keys=True))
        sys.exit(1 if problems else 0)

    if problems:
        for p in problems:
            print(f"  drift: {p}", file=sys.stderr)
        raise SystemExit(f"brand mark drift in {len(problems)} place(s).")
    print(f"brand mark is in sync across {len(targets)} SVG(s).")


if __name__ == "__main__":
    main()
