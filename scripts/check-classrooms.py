#!/usr/bin/env python3
"""AthenIQ — validate the OpenMAIC classroom specs against the OLX courseware.

Each course may ship a generative-classroom specification beside its courseware —
`courses/<slug>/openmaic/classrooms.json` — describing, per chapter, the scenario
OpenMAIC should generate: a prompt, objectives, agent roles, and the activities the
classroom should contain.

The spec points at the courseware by URL name (`chapter`, `linked_units`). That is
exactly the kind of pointer that rots silently: rename a unit in the OLX and the
classroom spec still looks fine while linking at nothing. So this lint reads both
sides — the spec and the OLX outline — and fails when they disagree:

  * the document parses and is versioned
  * `source_course` is a `course-v1:` key with an OLX package in this repo
  * every classroom has a unique slug `id`, a `title`, a `prompt`, objectives,
    and at least one activity
  * the classroom's `chapter` exists in that course's outline
  * every `linked_units` entry is a unit **of that chapter** (so a unit moved
    between chapters is caught, not just a deleted one)
  * (warning) a chapter of the course has no classroom
  * (warning) an activity declares a type this repo does not use
  * (warning) the spec does not route through the platform's OmniRoute gateway

It is a lint, not a generator: it never talks to OpenMAIC and never touches the LMS.

Usage:
    python3 scripts/check-classrooms.py                 # human summary
    python3 scripts/check-classrooms.py --json          # machine output
    python3 scripts/check-classrooms.py --file PATH     # one classrooms.json

Exit codes: 0 valid (warnings allowed), 1 invalid.
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOT = os.path.join(REPO, "courses")

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COURSE_KEY_RE = re.compile(r"^course-v1:[^+\s]+\+[^+\s]+\+[^+\s]+$")
# Activity types this repo's specs use. An unknown type is a warning, not an
# error: OpenMAIC may grow activity kinds, and a spec should not be blocked by
# a lint that has not caught up.
KNOWN_ACTIVITY_TYPES = {
    "slides", "roleplay", "quiz", "simulation", "lab", "video", "reading",
    "poll", "discussion", "exercise",
}
EXPECTED_GATEWAY = "OmniRoute"


def load_validator():
    """Reuse the OLX linter's course discovery (one source of truth for packages)."""
    import importlib.util
    path = os.path.join(REPO, "scripts", "check-course-olx.py")
    spec = importlib.util.spec_from_file_location("check_course_olx", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


def olx_index(root):
    """Map every authored course key to its outline.

    Returns ``{course_key: {"slug": ..., "chapters": {chapter_url: [unit_url, ...]}}}``
    so a classroom can be checked against the real OLX structure.
    """
    index = {}
    for olx_dir in VALIDATOR.find_courses(root):
        try:
            header = ET.parse(os.path.join(olx_dir, "course.xml")).getroot()
            run = header.get("url_name")
            key = f"course-v1:{header.get('org')}+{header.get('course')}+{run}"
            block = ET.parse(os.path.join(olx_dir, "course", f"{run}.xml")).getroot()
        except (ET.ParseError, OSError):
            continue

        chapters = {}
        for chapter_ref in [c for c in block if c.tag == "chapter"]:
            cref = chapter_ref.get("url_name")
            try:
                chapter = ET.parse(os.path.join(olx_dir, "chapter", f"{cref}.xml")).getroot()
            except (ET.ParseError, OSError):
                continue
            units = []
            for seq_ref in [s for s in chapter if s.tag == "sequential"]:
                sref = seq_ref.get("url_name")
                try:
                    sequential = ET.parse(
                        os.path.join(olx_dir, "sequential", f"{sref}.xml")).getroot()
                except (ET.ParseError, OSError):
                    continue
                units += [u.get("url_name") for u in sequential if u.tag == "vertical"]
            chapters[cref] = units

        index[key] = {"slug": os.path.basename(os.path.dirname(olx_dir)),
                      "chapters": chapters}
    return index


def find_specs(root):
    """Every `courses/<slug>/openmaic/classrooms.json` under root."""
    found = []
    if os.path.isfile(root) and root.endswith(".json"):
        return [root]
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            candidate = os.path.join(root, name, "openmaic", "classrooms.json")
            if os.path.isfile(candidate):
                found.append(candidate)
    return found


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def validate_spec(path, index):
    """Validate one classroom spec against the OLX index.

    Returns (errors, warnings, summary).
    """
    errors = []
    warnings = []
    summary = {"file": path, "source_course": None, "classrooms": 0}

    try:
        with open(path) as fh:
            doc = json.load(fh)
    except json.JSONDecodeError as e:
        return [f"not valid JSON: {e}"], warnings, summary
    except OSError as e:
        return [f"cannot read: {e}"], warnings, summary

    if not isinstance(doc, dict):
        return ["spec must be a JSON object"], warnings, summary
    if not isinstance(doc.get("version"), int):
        errors.append("version must be an integer")

    source = doc.get("source_course")
    summary["source_course"] = source
    if not _nonempty(source):
        errors.append("source_course must be a course-v1: key")
    elif not COURSE_KEY_RE.match(source):
        errors.append(f"source_course '{source}' is not course-v1:<org>+<course>+<run>")
    elif source not in index:
        errors.append(f"source_course '{source}' has no OLX package under courses/")

    gateway = doc.get("gateway")
    if gateway is None:
        warnings.append("spec declares no gateway (the platform routes through "
                        f"{EXPECTED_GATEWAY})")
    elif gateway != EXPECTED_GATEWAY:
        warnings.append(f"gateway '{gateway}' is not the platform gateway "
                        f"'{EXPECTED_GATEWAY}'")

    classrooms = doc.get("classrooms")
    if not isinstance(classrooms, list) or not classrooms:
        errors.append("classrooms must be a non-empty array")
        return errors, warnings, summary

    outline = index.get(source) if _nonempty(source) else None
    covered = set()
    seen_ids = set()

    for i, room in enumerate(classrooms):
        where = f"classrooms[{i}]"
        if not isinstance(room, dict):
            errors.append(f"{where} must be an object")
            continue

        rid = room.get("id")
        if not _nonempty(rid) or not SLUG_RE.match(rid or ""):
            errors.append(f"{where}.id must be a lowercase slug")
            rid = where
        elif rid in seen_ids:
            errors.append(f"{where}.id '{rid}' is not unique")
        else:
            seen_ids.add(rid)
        summary["classrooms"] += 1

        for field in ("title", "prompt"):
            if not _nonempty(room.get(field)):
                errors.append(f"{where}.{field} must be a non-empty string")

        objectives = room.get("objectives")
        if not isinstance(objectives, list) or not objectives \
                or not all(_nonempty(o) for o in objectives):
            errors.append(f"{where}.objectives must be a non-empty array of strings")

        activities = room.get("activities")
        if not isinstance(activities, list) or not activities:
            errors.append(f"{where}.activities must be a non-empty array")
        else:
            for j, activity in enumerate(activities):
                if not isinstance(activity, dict):
                    errors.append(f"{where}.activities[{j}] must be an object")
                    continue
                atype = activity.get("type")
                if not _nonempty(atype):
                    errors.append(f"{where}.activities[{j}].type must be a non-empty string")
                elif atype not in KNOWN_ACTIVITY_TYPES:
                    warnings.append(f"{where}.activities[{j}] type '{atype}' is not one "
                                    "this repo uses")
                if not _nonempty(activity.get("title")):
                    warnings.append(f"{where}.activities[{j}] has no title")

        # The pointers into the courseware — the whole reason this lint exists.
        chapter = room.get("chapter")
        if not _nonempty(chapter):
            errors.append(f"{where}.chapter must be a non-empty string (an OLX chapter url_name)")
            continue
        if outline is None:
            continue
        if chapter not in outline["chapters"]:
            errors.append(f"{where}.chapter '{chapter}' is not a chapter of {source}")
            continue
        covered.add(chapter)

        linked = room.get("linked_units")
        if not isinstance(linked, list) or not linked or not all(_nonempty(u) for u in linked):
            errors.append(f"{where}.linked_units must be a non-empty array of url_names")
            continue
        units = outline["chapters"][chapter]
        for unit in linked:
            if unit not in units:
                errors.append(f"{where}.linked_units '{unit}' is not a unit of chapter "
                              f"'{chapter}'")

    if outline is not None:
        for chapter in outline["chapters"]:
            if chapter not in covered:
                warnings.append(f"chapter '{chapter}' of {source} has no classroom")

    return errors, warnings, summary


def markdown_table(summary):
    return (f"| Course | Classrooms |\n| --- | --- |\n"
            f"| `{summary['source_course']}` | {summary['classrooms']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULT_ROOT, help="directory holding course packages")
    ap.add_argument("--file", help="validate a single classrooms.json")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--markdown", action="store_true", help="emit a Markdown table and exit")
    args = ap.parse_args()

    if not os.path.exists(args.root):
        raise SystemExit(f"not found: {args.root}")

    specs = [args.file] if args.file else find_specs(args.root)
    if not specs:
        raise SystemExit(f"no classroom specs found under {args.root}")

    index = olx_index(args.root if not args.file else DEFAULT_ROOT)
    results = [validate_spec(p, index) for p in specs]
    all_errors = [f"{os.path.basename(os.path.dirname(os.path.dirname(p)))}: {e}"
                  for (errs, _, s), p in zip(results, specs) for e in errs]
    all_warnings = [f"{os.path.basename(os.path.dirname(os.path.dirname(p)))}: {w}"
                    for (_, ws, s), p in zip(results, specs) for w in ws]

    if args.json:
        print(json.dumps({
            "root": args.root,
            "specs": [
                {"file": os.path.relpath(s["file"], REPO), "source_course": s["source_course"],
                 "classrooms": s["classrooms"], "errors": errs, "warnings": ws}
                for (errs, ws, s) in results
            ],
            "errors": all_errors,
            "warnings": all_warnings,
            "valid": not all_errors,
        }, indent=2, sort_keys=True))
        sys.exit(1 if all_errors else 0)

    if args.markdown and not all_errors:
        for _, _, s in results:
            print(markdown_table(s))
        return

    print(f"Classrooms — {len(specs)} spec(s)")
    for errs, ws, s in results:
        print(f"  {s['source_course'] or '?'} — {s['classrooms']} classroom(s)")
        for w in ws:
            print(f"    warning: {w}")
        for e in errs:
            print(f"    error: {e}", file=sys.stderr)

    if all_errors:
        print(f"\n{len(all_errors)} error(s) — classroom specs invalid.", file=sys.stderr)
        sys.exit(1)
    print("\nOK — classroom specs valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
