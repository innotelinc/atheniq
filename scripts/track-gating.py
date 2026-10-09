#!/usr/bin/env python3
"""AthenIQ — in-LMS track gating.

A workforce track is an ordered ladder: ITSP102 only makes sense once ITSP101 is
passed, and so on through the certification. This turns the catalog into that
gating (a prerequisite chain) so the LMS enforces it rather than a learner
stumbling into course four first.

The catalog (`config/workforce-tracks.json`) is the single source of truth — the
chain is derived from the order courses are listed in, never hand-written.

Open edX spreads a course's prerequisites over three layers, and a real gate needs
all three (verified against the running release):

  1. the **course block** field `pre_requisite_courses` (`Scope.settings`) — the
     course-about page and `get_prerequisite_courses_display()` read it directly;
  2. `CourseOverview._pre_requisite_courses_json`, the **derived cache** the learner
     dashboard and learner home read — regenerated from (1);
  3. a **milestone** per prerequisite (`set_prerequisite_courses`), which is what
     actually blocks access (`MilestoneAccessError` in `courseware/access.py`).

Writing only the overview is a silent no-op: `CourseOverview.pre_requisite_courses`
has a documented do-nothing setter, so assigning it and saving still reports
success while persisting nothing. All three are also gated behind
`ENABLE_PREREQUISITE_COURSES` and the `MILESTONES_APP` setting; `--apply` reports
when either is off.

    python3 scripts/track-gating.py                  # human-readable plan
    python3 scripts/track-gating.py --json           # machine plan
    python3 scripts/track-gating.py --track it-support
    python3 scripts/track-gating.py --cumulative     # require every earlier course
    python3 scripts/track-gating.py --check          # fail if the catalog yields no plan
    python3 scripts/track-gating.py --apply          # write it (operator action)
    python3 scripts/track-gating.py --apply --dry-run

`--apply` runs through the running CMS container's own models
(`./manage.py cms shell`), writing the block exactly as Studio's course-details
tab writes it and the milestones through `milestones_helpers`, so the LMS signals
fire and the derived overviews are regenerated — it never edits a database row
behind Open edX's back. It is an operator action: nothing here runs except when
asked.
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
# apply (operator action, in the CMS's own Django process)
# --------------------------------------------------------------------------

MISSING_PREFIX = "missing course: "

APPLY_SNIPPET = """
import json

from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey

from common.djangoapps.util.milestones_helpers import (
    is_prerequisite_courses_enabled, set_prerequisite_courses,
)
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from xmodule.modulestore.django import modulestore

plan = json.loads({plan_json!r})

if not is_prerequisite_courses_enabled():
    raise SystemExit(
        "prerequisites are switched off on this LMS: set FEATURES"
        "[ENABLE_PREREQUISITE_COURSES] and MILESTONES_APP, then restart.")

# Settings writes are attributed to an editor in the modulestore history; use the
# same kind of account Studio would have used.
User = get_user_model()
editor = (User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
          or User.objects.filter(is_staff=True, is_active=True).order_by("id").first())
if editor is None:
    raise SystemExit("no active staff account to attribute the settings change to")

store = modulestore()
gated, changed, missing = [], [], []
for item in plan:
    key = CourseKey.from_string(item["course"])
    block = store.get_course(key)
    if block is None:
        missing.append(item["course"])
        continue
    prerequisites = [str(prerequisite) for prerequisite in item["prerequisites"]]
    # Layer 1: the course block field. Written exactly as Studio's course-details
    # tab writes it, so the publish/update signals fire.
    if list(block.pre_requisite_courses) != prerequisites:
        block.pre_requisite_courses = prerequisites
        store.update_item(block, editor.id)
        changed.append(item["course"])
    # Layer 3: the milestone the access check actually enforces. Idempotent — it
    # clears this course's existing "requires" milestones before re-adding.
    set_prerequisite_courses(key, prerequisites)
    gated.append(key)

# Layer 2: regenerate the derived overview rows the dashboard reads.
CourseOverview.update_select_courses(sorted(gated, key=str), force_update=True)

print("prerequisites set for", len(gated), "course(s):",
      len(changed), "changed, editor", editor.username)
for course in missing:
    print("{missing_prefix}" + course)
"""


def apply_plan(plan, container, dry_run):
    """Run the gating snippet in the CMS. Returns the catalog courses it could not
    find in the LMS (empty on a complete apply)."""
    plan_json = json.dumps([{k: v for k, v in item.items() if k != "track"} for item in plan])
    snippet = APPLY_SNIPPET.format(plan_json=plan_json, missing_prefix=MISSING_PREFIX)
    cmd = ["docker", "exec", "-i", container, "./manage.py", "cms", "shell", "-c", snippet]
    if dry_run:
        print("would run in", container, ":")
        print(snippet)
        return []
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.stdout:
        print(out.stdout, end="")
    if out.returncode != 0:
        if out.stdout.strip():
            # The snippet's own message is already on stdout; only add the tail of
            # the traceback when it said nothing useful.
            sys.stderr.write(out.stderr[-400:])
        else:
            sys.stderr.write(out.stderr[-2000:])
        raise SystemExit(f"apply failed in {container} (exit {out.returncode})")
    return [line[len(MISSING_PREFIX):].strip() for line in out.stdout.splitlines()
            if line.startswith(MISSING_PREFIX)]


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
        missing = apply_plan(plan, args.container, args.dry_run)
        if missing:
            for course in missing:
                print(f"  not in the LMS: {course}", file=sys.stderr)
            raise SystemExit(
                f"{len(missing)} catalog course(s) are not in the LMS — "
                "import them (make course-import) before gating.")


if __name__ == "__main__":
    main()
