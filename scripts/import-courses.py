#!/usr/bin/env python3
"""AthenIQ — bundle and import the OLX courses into the LMS.

Every course under `courses/<slug>/olx/` is a self-contained Open edX course
package. This tool finds them, validates their structure with
`check-course-olx.py`, bundles each into a `.tar.gz`, and plans (or, with
`--execute`, runs) the import into the Tutor CMS container.

It is deliberately two-phase:

  * the default (plan) prints what it found and the exact commands it would run;
    it touches nothing.
  * `--bundle` writes the archives under `dist/`.
  * `--execute` runs `docker cp` + `manage.py cms import` for each course.

Nothing in CI runs `--execute`; re-import is an operator action against a real
deployment (see docs/Deployment.md).

Usage:
    python3 scripts/import-courses.py                 # plan (default)
    python3 scripts/import-courses.py --bundle        # also build dist/*.tar.gz
    python3 scripts/import-courses.py --course ITSP102
    python3 scripts/import-courses.py --execute       # import into the running CMS
    python3 scripts/import-courses.py --json

Exit codes: 0 ok, 1 invalid course or a failed import.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULTS = {
    "COURSE_ROOT": os.path.join(REPO, "courses"),
    "DIST_DIR": os.path.join(REPO, "dist"),
    "CMS_CONTAINER": "tutor_local-cms-1",
    "EDX_PLATFORM": "/openedx/edx-platform",
    "EDX_DATA_DIR": "/openedx/data",
    "PYTHON": "python",
}


def _load_validator():
    """Load the hyphenated OLX validator as a module (reuse, don't duplicate)."""
    path = os.path.join(REPO, "scripts", "check-course-olx.py")
    spec = importlib.util.spec_from_file_location("check_course_olx", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def find_olx(root):
    """Every `courses/<slug>/olx` directory that holds a course.xml."""
    if os.path.isfile(os.path.join(root, "course.xml")):
        return [root]
    found = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            candidate = os.path.join(root, name, "olx")
            if os.path.isfile(os.path.join(candidate, "course.xml")):
                found.append(candidate)
    return found


def read_index(olx_dir):
    """Return (org, course, run, title) from a course's OLX root."""
    index = ET.parse(os.path.join(olx_dir, "course.xml")).getroot()
    run = index.get("url_name")
    block = ET.parse(os.path.join(olx_dir, "course", f"{run}.xml")).getroot()
    return index.get("org"), index.get("course"), run, block.get("display_name")


def plan(root):
    """Describe every course package: key, directory, title, archive name."""
    entries = []
    for olx_dir in find_olx(root):
        slug = os.path.basename(os.path.dirname(olx_dir))
        org, course, run, title = read_index(olx_dir)
        entries.append({
            "slug": slug,
            "org": org,
            "course": course,
            "run": run,
            "title": title,
            "key": f"course-v1:{org}+{course}+{run}",
            "olx_dir": olx_dir,
            "archive": f"{slug}-{run}.tar.gz",
        })
    return entries


def build_archive(entry, dest_dir):
    """Bundle one course's olx/ directory into `<slug>-<run>.tar.gz`.

    The archive contains a single top-level `olx/` directory, which is what the
    Studio importer expects (a course data directory holding course.xml).
    """
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, entry["archive"])
    with tarfile.open(path, "w:gz") as tar:
        tar.add(entry["olx_dir"], arcname="olx")
    return path


def import_commands(entry, archive_path, container=None, platform=None, data_dir=None,
                    python=None):
    """The two shell commands that import one bundled course into the CMS."""
    container = container or DEFAULTS["CMS_CONTAINER"]
    platform = platform or DEFAULTS["EDX_PLATFORM"]
    data_dir = data_dir or DEFAULTS["EDX_DATA_DIR"]
    python = python or DEFAULTS["PYTHON"]
    basename = os.path.basename(archive_path)
    remote = f"/tmp/{basename}"
    return [
        f"docker cp {archive_path} {container}:{remote}",
        (f"docker exec {container} sh -c 'cd {platform} && "
         f"{python} ./manage.py cms import {data_dir} {entry['key']} {remote}'"),
    ]


def validate(entry):
    errors, warnings, _ = VALIDATOR.validate_course(entry["olx_dir"])
    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULTS["COURSE_ROOT"], help="courses/ directory")
    ap.add_argument("--dist-dir", default=DEFAULTS["DIST_DIR"], help="where archives are written")
    ap.add_argument("--course", action="append", default=None,
                    help="only this course slug or key (repeatable)")
    ap.add_argument("--container", default=DEFAULTS["CMS_CONTAINER"])
    ap.add_argument("--platform", default=DEFAULTS["EDX_PLATFORM"])
    ap.add_argument("--data-dir", default=DEFAULTS["EDX_DATA_DIR"])
    ap.add_argument("--bundle", action="store_true", help="build the .tar.gz archives")
    ap.add_argument("--execute", action="store_true", help="run the imports (operator action)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        raise SystemExit(f"course root not found: {args.root}")

    entries = plan(args.root)
    if args.course:
        wanted = set(args.course)
        entries = [e for e in entries if e["slug"] in wanted or e["key"] in wanted]
    if not entries:
        raise SystemExit("no matching course packages found")

    all_errors = []
    for entry in entries:
        errors, warnings = validate(entry)
        entry["errors"] = errors
        entry["warnings"] = warnings
        all_errors.extend(f"{entry['slug']}: {e}" for e in errors)

    if all_errors and not args.execute:
        for e in all_errors:
            print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1)

    commands = []
    if args.bundle or args.execute:
        for entry in entries:
            entry["archive_path"] = build_archive(entry, args.dist_dir)
            commands.extend(import_commands(entry, entry["archive_path"],
                                            args.container, args.platform,
                                            args.data_dir))

    if args.json:
        print(json.dumps({
            "root": args.root,
            "courses": [{k: v for k, v in e.items() if k != "olx_dir"} for e in entries],
            "commands": commands,
            "valid": not all_errors,
        }, indent=2, sort_keys=True))
    else:
        print(f"Course import plan — {len(entries)} package(s) under "
              f"{os.path.relpath(args.root, REPO)}")
        for e in entries:
            state = "ok" if not e["errors"] else "INVALID"
            print(f"  {e['key']:<46} {e['title'] or '?':<42} {state}")
            for w in e["warnings"]:
                print(f"      warning: {w}")
        if commands:
            print("\nCommands:")
            for c in commands:
                print(f"  {c}")
        elif not args.bundle:
            print("\n(plan only — pass --bundle to build archives or --execute to import)")

    if args.execute:
        for entry in entries:
            if entry["errors"]:
                print(f"error: refusing to import invalid course {entry['slug']}", file=sys.stderr)
                raise SystemExit(1)
        for command in commands:
            print(f"$ {command}")
            result = subprocess.run(command, shell=True)
            if result.returncode != 0:
                print(f"error: command failed ({result.returncode}): {command}", file=sys.stderr)
                raise SystemExit(1)

    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()
