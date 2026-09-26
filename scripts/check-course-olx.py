#!/usr/bin/env python3
"""AthenIQ — validate the OLX course packages under `courses/`.

Each course is authored as Open Learning XML in the exact layout Open edX Studio
exports and imports: a root `course.xml`, a `course/<run>.xml` block, then
`chapter/`, `sequential/`, `vertical/`, `html/` and `problem/` directories plus
`policies/`, `about/` and `info/`. Keeping the courseware as data in the repo lets
it be reviewed and versioned; the LMS stays the runtime.

This is a lint, not a publisher: it parses the XML and checks the structure the
Studio importer relies on. It never touches the LMS.

Checks per course:
  * `course.xml` is a `<course>` with `url_name`/`org`/`course`
  * the course key is `course-v1:<org>+<course>+<run>`
  * `course/<run>.xml` exists and is a `<course>` referencing chapters
  * every container reference resolves to a file of the right type:
    chapter -> sequential -> vertical -> component
  * a chapter's children are sequentials (never a vertical directly — that
    crashes the Studio authoring outline)
  * an `<html>` component names a `filename` whose `.html` content exists
  * a `<problem>` contains at least one response element
  * (warning) at least one graded sequential and one problem exist
  * (warning) a policies/<run>/grading_policy.json parses when present

Usage:
    python3 scripts/check-course-olx.py                 # all courses, human summary
    python3 scripts/check-course-olx.py --json          # machine output
    python3 scripts/check-course-olx.py --markdown      # course outline tables
    python3 scripts/check-course-olx.py --file PATH     # one OLX directory

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

COURSE_KEY_RE = re.compile(r"^course-v1:[^+\s]+\+[^+\s]+\+[^+\s]+$")
CONTAINER_CHILD = {
    "course": "chapter",
    "chapter": "sequential",
    "sequential": "vertical",
}
# Component types an author may place in a unit. The tag name is the directory.
COMPONENT_TAGS = {"html", "problem", "video", "lti", "poll", "survey", "drag-and-drop-v2", "openassessment"}
RESPONSE_TAGS = {"multiplechoiceresponse", "choiceresponse", "numericalresponse",
                 "stringresponse", "customresponse", "optionresponse",
                 "formularesponse", "coderesponse"}


def parse(path):
    """Parse an XML file, returning (root, error)."""
    try:
        return ET.parse(path).getroot(), None
    except ET.ParseError as e:
        return None, f"invalid XML: {e}"
    except OSError as e:
        return None, f"cannot read: {e}"


def course_key(org, course, run):
    return f"course-v1:{org}+{course}+{run}"


def _ref(root, tag="url_name"):
    return root.get(tag) if root is not None else None


def validate_course(olx_dir):
    """Validate one OLX directory (the one containing course.xml).

    Returns (errors, warnings, summary).
    """
    errors = []
    warnings = []
    summary = {"dir": olx_dir, "course_key": None, "title": None,
               "chapters": 0, "sequentials": 0, "graded": 0, "units": 0,
               "html": 0, "problems": 0}

    def fail(msg):
        errors.append(msg)

    root_path = os.path.join(olx_dir, "course.xml")
    if not os.path.isfile(root_path):
        fail("course.xml not found")
        return errors, warnings, summary

    index, err = parse(root_path)
    if err:
        fail(f"course.xml: {err}")
        return errors, warnings, summary
    if index.tag != "course":
        fail(f"course.xml: root element is <{index.tag}>, expected <course>")

    run = _ref(index)
    org = index.get("org")
    course = index.get("course")
    if not run:
        fail("course.xml: missing url_name (the course run)")
    if not org:
        fail("course.xml: missing org")
    if not course:
        fail("course.xml: missing course")
    if not (run and org and course):
        return errors, warnings, summary

    key = course_key(org, course, run)
    summary["course_key"] = key
    if not COURSE_KEY_RE.match(key):
        fail(f"course key '{key}' is not course-v1:<org>+<course>+<run>")

    block_path = os.path.join(olx_dir, "course", f"{run}.xml")
    block, err = parse(block_path)
    if err:
        fail(f"course/{run}.xml: {err}")
        return errors, warnings, summary
    if block.tag != "course":
        fail(f"course/{run}.xml: root element is <{block.tag}>, expected <course>")
    summary["title"] = block.get("display_name")

    def resolve(kind, ref, where):
        path = os.path.join(olx_dir, kind, f"{ref}.xml")
        if not os.path.isfile(path):
            fail(f"{where}: {kind}/{ref}.xml not found")
            return None
        node, e = parse(path)
        if e:
            fail(f"{kind}/{ref}.xml: {e}")
            return None
        if node.tag != kind:
            fail(f"{kind}/{ref}.xml: root element is <{node.tag}>, expected <{kind}>")
        return node

    chapters = [c for c in block if c.tag == "chapter"]
    if not chapters:
        fail("course block references no chapters")
    for chapter_ref in chapters:
        ref = _ref(chapter_ref)
        if not ref:
            fail("course block has a <chapter> without url_name")
            continue
        summary["chapters"] += 1
        chapter = resolve("chapter", ref, f"chapter/{ref}")
        if chapter is None:
            continue
        for child in chapter:
            if child.tag != "sequential":
                fail(f"chapter/{ref} contains <{child.tag}>; "
                     "chapters may only contain sequentials (a vertical placed "
                     "directly under a chapter breaks the Studio outline)")
                continue
            sref = _ref(child)
            if not sref:
                fail(f"chapter/{ref}: <sequential> without url_name")
                continue
            summary["sequentials"] += 1
            sequential = resolve("sequential", sref, f"sequential/{sref}")
            if sequential is None:
                continue
            if sequential.get("graded") == "true":
                summary["graded"] += 1
            for unit_ref in sequential:
                if unit_ref.tag != "vertical":
                    fail(f"sequential/{sref} contains <{unit_ref.tag}>; "
                         "sequentials may only contain verticals")
                    continue
                uref = _ref(unit_ref)
                if not uref:
                    fail(f"sequential/{sref}: <vertical> without url_name")
                    continue
                summary["units"] += 1
                unit = resolve("vertical", uref, f"vertical/{uref}")
                if unit is None:
                    continue
                for comp in unit:
                    cref = _ref(comp)
                    if not cref:
                        fail(f"vertical/{uref}: <{comp.tag}> without url_name")
                        continue
                    if comp.tag not in COMPONENT_TAGS:
                        fail(f"vertical/{uref}: unknown component <{comp.tag}>")
                        continue
                    node = resolve(comp.tag, cref, f"{comp.tag}/{cref}")
                    if node is None:
                        continue
                    if comp.tag == "html":
                        summary["html"] += 1
                        filename = node.get("filename")
                        if not filename:
                            fail(f"html/{cref}.xml: <html> missing filename")
                        elif not os.path.isfile(os.path.join(olx_dir, "html", f"{filename}.html")):
                            fail(f"html/{cref}.xml: content html/{filename}.html not found")
                    elif comp.tag == "problem":
                        summary["problems"] += 1
                        if not any(ch.tag in RESPONSE_TAGS for ch in node):
                            fail(f"problem/{cref}.xml: no recognized response element")

    if summary["graded"] == 0:
        warnings.append("course has no graded sequential")
    if summary["problems"] == 0:
        warnings.append("course has no graded problems")

    grading = os.path.join(olx_dir, "policies", run, "grading_policy.json")
    if os.path.isfile(grading):
        try:
            with open(grading) as fh:
                json.load(fh)
        except json.JSONDecodeError as e:
            fail(f"policies/{run}/grading_policy.json: {e}")
    else:
        warnings.append(f"policies/{run}/grading_policy.json not found")

    policy_path = os.path.join(olx_dir, "policies", run, "policy.json")
    if os.path.isfile(policy_path):
        try:
            with open(policy_path) as fh:
                policy = json.load(fh)
        except json.JSONDecodeError as e:
            fail(f"policies/{run}/policy.json: {e}")
            policy = None
        if isinstance(policy, dict):
            course_policy = policy.get(f"course/{run}") or {}
            image = course_policy.get("course_image")
            if image and not os.path.isfile(os.path.join(olx_dir, "static", image)):
                fail(f"policies/{run}/policy.json: course_image '{image}' not found in static/")
            certs = (course_policy.get("certificates") or {}).get("certificates")
            certs = [c for c in certs if isinstance(c, dict)] if isinstance(certs, list) else []
            if not certs:
                warnings.append("policy.json declares no certificate definition")
            else:
                if not any(c.get("is_active") for c in certs):
                    warnings.append("certificate definition has no active certificate")
                if not any(c.get("signatories") for c in certs):
                    warnings.append("certificate definition has no signatory")
    else:
        warnings.append(f"policies/{run}/policy.json not found")

    return errors, warnings, summary


def find_courses(root):
    if os.path.isfile(os.path.join(root, "course.xml")):
        return [root]
    found = []
    if os.path.isdir(root):
        for name in sorted(os.listdir(root)):
            candidate = os.path.join(root, name, "olx")
            if os.path.isfile(os.path.join(candidate, "course.xml")):
                found.append(candidate)
    return found


def markdown_table(summary):
    return (f"| Course | Key | Chapters | Units | Lessons | Problems |\n"
            f"| --- | --- | --- | --- | --- | --- |\n"
            f"| {summary['title'] or '?'} | `{summary['course_key']}` "
            f"| {summary['chapters']} | {summary['units']} "
            f"| {summary['html']} | {summary['problems']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULT_ROOT, help="directory holding course packages")
    ap.add_argument("--file", help="validate a single OLX directory")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--markdown", action="store_true", help="emit a Markdown outline and exit")
    args = ap.parse_args()

    target = args.file or args.root
    if not os.path.exists(target):
        raise SystemExit(f"not found: {target}")
    courses = find_courses(target)
    if not courses:
        raise SystemExit(f"no OLX courses found under {target}")

    results = [validate_course(c) for c in courses]
    all_errors = [e for errs, _, _ in results for e in errs]
    all_warnings = [w for _, ws, _ in results for w in ws]

    if args.json:
        print(json.dumps({
            "root": target,
            "courses": [
                {"dir": os.path.relpath(s["dir"], REPO), "course_key": s["course_key"],
                 "title": s["title"], "chapters": s["chapters"], "sequentials": s["sequentials"],
                 "graded": s["graded"], "units": s["units"], "html": s["html"],
                 "problems": s["problems"], "errors": errs, "warnings": ws}
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

    print(f"Course OLX — {len(courses)} course(s) under {os.path.relpath(target, REPO)}")
    for errs, ws, s in results:
        print(f"  {s['course_key']} — {s['title'] or '?'}")
        print(f"    {s['chapters']} chapters · {s['sequentials']} subsections "
              f"({s['graded']} graded) · {s['units']} units · "
              f"{s['html']} lessons · {s['problems']} problems")
        for w in ws:
            print(f"    warning: {w}")
        for e in errs:
            print(f"    error: {e}", file=sys.stderr)

    if all_errors:
        print(f"\n{len(all_errors)} error(s) — course OLX invalid.", file=sys.stderr)
        sys.exit(1)
    print("\nOK — course OLX valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
