#!/usr/bin/env python3
"""AthenIQ — in-LMS track gating.

A workforce track is an ordered ladder: ITSP102 only makes sense once ITSP101 is
passed, and so on through the certification. This turns the catalog into that
gating (a prerequisite chain) so the LMS enforces it rather than a learner
stumbling into course four first.

The catalog (`config/workforce-tracks.json`) is the single source of truth — the
chain is derived from the order courses are listed in, never hand-written. Open
edX keeps a course's prerequisites on its course overview (`CourseOverview.
prerequisites`, a list of course keys), which is what the LMS reads to show the
"You must complete … first" gate.

    python3 scripts/track-gating.py                  # human-readable plan
    python3 scripts/track-gating.py --json           # machine plan
    python3 scripts/track-gating.py --track it-support
    python3 scripts/track-gating.py --cumulative     # require every earlier course
    python3 scripts/track-gating.py --check          # fail if the catalog yields no plan
    python3 scripts/track-gating.py --apply          # write it (operator action)
    python3 scripts/track-gating.py --apply --dry-run

`--apply` runs through the running CMS container's own model
(`./manage.py cms shell`), so the LMS signals fire — it never edits the database
row behind Open edX's back. It is an operator action: nothing here runs except
when asked.
"""
import argparse
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(REPO, "config", "workforce-tracks.json")

# CMS container that owns the course overviews.
DEFAULT_CMS_CONTAINER = "tutor_local-cms-1"


# --------------------------------------------------------------------------
# plan (pure — the part the tests pin)
# --------------------------------------------------------------------------

def prerequisite_plan(doc, track_id=None, cumulative=False):
    """Derive each course's prerequisites from the track's course order.

    Sequential (default): a course requires the one immediately before it.
    Cumulative: it requires every earlier course in the track. Tracks are only
    as ordered as the catalog lists them, so this is deterministic.
    """
    plan = []
    for track in doc.get("tracks", []):
        if not isinstance(track, dict):
            continue
        if track_id and track.get("id") != track_id:
            continue
        courses = [c for c in (track.get("courses") or []) if isinstance(c, str)]
        for i, key in enumerate(courses):
            prereqs = courses[:i] if cumulative else courses[i - 1:i]
            plan.append({
                "track": track.get("id"),
                "course": key,
                "prerequisites": prereqs,
            })
    return plan


def validate_plan(doc, plan, errors=None):
    """Catch a catalog that cannot gate cleanly: duplicate courses in one track,
    or a course key that is not a `course-v1:` key (already checked by
    check-workforce-tracks.py, but gating must not trust that)."""
    errors = [] if errors is None else errors
    seen = {}
    for item in plan:
        key = item["course"]
        if key in seen:
            errors.append(f"course {key} appears twice in track {item['track']}")
        seen[key] = True
        if not key.startswith("course-v1:") or key.count("+") != 2:
            errors.append(f"course {key} is not a course-v1:<org>+<course>+<run> key")
        for pre in item["prerequisites"]:
            if pre == key:
                errors.append(f"course {key} lists itself as a prerequisite")
    return errors


def load_catalog(path):
    with open(path) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# apply (operator action, via the CMS model)
# --------------------------------------------------------------------------

APPLY_SNIPPET = """
import json
from opaque_keys.edx.keys import CourseKey
try:
    from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
except ImportError:  # older layouts
    from course_overviews.models import CourseOverview

plan = json.loads({plan_json!r})
keys = {{item["course"]: CourseKey.from_string(item["course"]) for item in plan}}
by_id = {{str(o.id): o for o in CourseOverview.objects.filter(id__in=list(keys.values()))}}
written = 0
for item in plan:
    overview = by_id.get(item["course"])
    if overview is None:
        print("missing course overview:", item["course"])
        continue
    overview.prerequisites = item["prerequisites"]
    overview.save()
    written += 1
print("prerequisites written for", written, "course(s)")
"""


def apply_plan(plan, container, dry_run):
    plan_json = json.dumps([{k: v for k, v in item.items() if k != "track"} for item in plan])
    snippet = APPLY_SNIPPET.format(plan_json=plan_json)
    cmd = ["docker", "exec", "-i", container, "./manage.py", "cms", "shell", "-c", snippet]
    if dry_run:
        print("would run in", container, ":")
        print(snippet)
        return 0
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.stdout:
        print(out.stdout, end="")
    if out.returncode != 0:
        sys.stderr.write(out.stderr[-2000:])
        raise SystemExit(f"apply failed in {container}")
    return out.returncode


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=DEFAULT_FILE, help="catalog to read")
    ap.add_argument("--track", help="only this track id")
    ap.add_argument("--cumulative", action="store_true",
                    help="require every earlier course, not just the previous one")
    ap.add_argument("--json", action="store_true", help="machine-readable plan")
    ap.add_argument("--check", action="store_true",
                    help="validate the catalog yields a clean plan and exit")
    ap.add_argument("--apply", action="store_true",
                    help="write the prerequisites through the CMS (operator action)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --apply, print the snippet instead of running it")
    ap.add_argument("--container", default=os.environ.get("CMS_CONTAINER", DEFAULT_CMS_CONTAINER),
                    help="running CMS container")
    args = ap.parse_args()

    try:
        doc = load_catalog(args.file)
    except FileNotFoundError:
        raise SystemExit(f"catalog not found: {args.file}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"catalog is not valid JSON: {e}")

    plan = prerequisite_plan(doc, args.track, args.cumulative)
    errors = validate_plan(doc, plan)

    if args.check:
        if errors:
            for e in errors:
                print(f"error: {e}", file=sys.stderr)
            raise SystemExit(f"{len(errors)} gating error(s) — catalog invalid.")
        if not plan:
            raise SystemExit("no courses to gate (empty catalog or unknown --track)")
        print(f"gating plan is clean — {len(plan)} course(s), "
              f"{sum(1 for i in plan if i['prerequisites'])} gated.")
        return

    if args.json:
        print(json.dumps({"tracks": sorted({i["track"] for i in plan}),
                          "plan": plan}, indent=2, sort_keys=True))
        sys.exit(1 if errors else 0)

    for item in plan:
        pre = ", ".join(item["prerequisites"]) or "—"
        print(f"  {item['course']:<42} after: {pre}")
    for e in errors:
        print(f"  error: {e}", file=sys.stderr)
    if errors:
        raise SystemExit(f"\n{len(errors)} gating error(s).")

    if args.apply:
        print()
        apply_plan(plan, args.container, args.dry_run)


if __name__ == "__main__":
    main()
