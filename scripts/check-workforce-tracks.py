#!/usr/bin/env python3
"""AthenIQ — validate the workforce-tracks catalog.

The catalog (`config/workforce-tracks.json`) is the source of truth for the
platform's workforce-development and instructor tracks: named ladders of Open
edX courses that share a credential and, optionally, a Magnate entitlement.

Keeping it as data — and validating it — is what lets the landing page, the
deployment runbook, and the operator keep the same view of what a "track" is.
This is a lint, not a publisher: it never touches the LMS.

Checks:
  * the document parses and is versioned
  * every track has a unique slug `id`, a `title`, a `summary`, and >= 1 course
  * every course key matches `course-v1:<org>+<course>+<run>`
  * `status` is one of draft | active | retired
  * `credential.type` (when present) is a known type
  * `entitlement.plan` (when set) looks like a Magnate plan slug
  * `skills` (when present) is a list of non-empty strings
  * no two tracks claim the same course in the same run (advisory warning)

Usage:
    python3 scripts/check-workforce-tracks.py               # human summary
    python3 scripts/check-workforce-tracks.py --json        # machine output
    python3 scripts/check-workforce-tracks.py --markdown    # README-ready table
    python3 scripts/check-workforce-tracks.py --file PATH   # validate another catalog

Exit codes: 0 valid (warnings allowed), 1 invalid.
"""
import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(REPO, "config", "workforce-tracks.json")

COURSE_KEY_RE = re.compile(r"^course-v1:[^+\s]+:[^+\s]+$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATUSES = {"draft", "active", "retired"}
CREDENTIAL_TYPES = {"certificate", "badge", "none"}


def course_key_check(key):
    # Open edX course keys are `course-v1:<org>+<course>+<run>`.
    return bool(re.match(r"^course-v1:[^+\s]+\+[^+\s]+\+[^+\s]+$", key))


def validate(doc):
    errors = []
    warnings = []

    if not isinstance(doc, dict):
        return ["catalog must be a JSON object"], warnings
    if not isinstance(doc.get("version"), int):
        errors.append("catalog.version must be an integer")
    tracks = doc.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        errors.append("catalog.tracks must be a non-empty array")
        return errors, warnings

    seen_ids = set()
    course_owners = {}
    for i, track in enumerate(tracks):
        where = f"tracks[{i}]"
        if not isinstance(track, dict):
            errors.append(f"{where} must be an object")
            continue
        tid = track.get("id")
        if not isinstance(tid, str) or not SLUG_RE.match(tid):
            errors.append(f"{where}.id must be a lowercase slug")
            tid = tid if isinstance(tid, str) else where
        elif tid in seen_ids:
            errors.append(f"{where}.id '{tid}' is not unique")
        else:
            seen_ids.add(tid)

        for field in ("title", "summary"):
            if not isinstance(track.get(field), str) or not track[field].strip():
                errors.append(f"{where}.{field} must be a non-empty string")

        status = track.get("status", "draft")
        if status not in STATUSES:
            errors.append(f"{where}.status must be one of {sorted(STATUSES)}")

        courses = track.get("courses")
        if not isinstance(courses, list) or not courses:
            errors.append(f"{where}.courses must be a non-empty array")
        else:
            for j, key in enumerate(courses):
                if not isinstance(key, str) or not course_key_check(key):
                    errors.append(
                        f"{where}.courses[{j}] '{key}' is not a "
                        "course-v1:<org>+<course>+<run> key")
                else:
                    course_owners.setdefault(key, []).append(tid)

        credential = track.get("credential")
        if credential is not None:
            if not isinstance(credential, dict):
                errors.append(f"{where}.credential must be an object")
            else:
                ctype = credential.get("type")
                if ctype not in CREDENTIAL_TYPES:
                    errors.append(
                        f"{where}.credential.type must be one of {sorted(CREDENTIAL_TYPES)}")
                if credential.get("type") == "certificate" and not credential.get("signara_template"):
                    warnings.append(
                        f"{where}.credential declares a certificate but no signara_template")

        entitlement = track.get("entitlement")
        if entitlement is not None:
            if not isinstance(entitlement, dict):
                errors.append(f"{where}.entitlement must be an object")
            else:
                plan = entitlement.get("plan")
                if plan is not None and (not isinstance(plan, str) or not SLUG_RE.match(plan)):
                    errors.append(f"{where}.entitlement.plan must be null or a slug")

        skills = track.get("skills")
        if skills is not None and (not isinstance(skills, list)
                                   or not all(isinstance(s, str) and s.strip() for s in skills)):
            errors.append(f"{where}.skills must be an array of non-empty strings")

    for key, owners in course_owners.items():
        if len(owners) > 1:
            warnings.append(f"course {key} appears in multiple tracks: {', '.join(owners)}")

    return errors, warnings


def markdown_table(tracks):
    lines = ["| Track | Role / audience | Courses | Access | Status |",
             "| --- | --- | --- | --- | --- |"]
    for t in tracks:
        plan = (t.get("entitlement") or {}).get("plan")
        access = f"Magnate `{plan}`" if plan else "free"
        lines.append(
            f"| **{t['title']}** (`{t['id']}`) | {t.get('target_role', '-')} "
            f"· {t.get('audience', '-')} | {len(t.get('courses', []))} | {access} "
            f"| {t.get('status', 'draft')} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=DEFAULT_FILE, help="catalog to validate")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--markdown", action="store_true", help="emit a Markdown table and exit")
    args = ap.parse_args()

    try:
        with open(args.file) as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise SystemExit(f"catalog not found: {args.file}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"catalog is not valid JSON: {e}")

    errors, warnings = validate(doc)
    tracks = doc.get("tracks", []) if isinstance(doc, dict) else []

    if args.markdown and not errors:
        print(markdown_table(tracks))
        return

    if args.json:
        print(json.dumps({
            "file": args.file,
            "tracks": len(tracks),
            "errors": errors,
            "warnings": warnings,
            "valid": not errors,
        }, indent=2, sort_keys=True))
        sys.exit(1 if errors else 0)

    print(f"Workforce tracks — {len(tracks)} track(s) in {os.path.relpath(args.file, REPO)}")
    for t in tracks:
        if not isinstance(t, dict):
            continue
        plan = (t.get("entitlement") or {}).get("plan")
        access = f"magnate:{plan}" if plan else "free"
        print(f"  {t.get('id', '?'):<28} {t.get('title', '?'):<32} "
              f"{len(t.get('courses', [])):>2} course(s)  {t.get('status', 'draft'):<7} {access}")
    for w in warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)

    if errors:
        print(f"\n{len(errors)} error(s) — catalog invalid.", file=sys.stderr)
        sys.exit(1)
    print("\nOK — catalog valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
