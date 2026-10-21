#!/usr/bin/env python3
"""AthenIQ — publish a programme's courses into the LMS as real courses.

A programme in the console is a plan: semesters, course codes, credits,
prerequisites, final examinations. Until this tool existed those codes were only
that — a line in a JSON file. A learner could read the programme, but the course
was not in the LMS: it was not in *Explore courses*, it could not be enrolled in,
and so it could never appear in *My courses*.

This tool closes that gap. For every course in a programme it writes a real OLX
course package and imports it into the running CMS, so the course exists in the
LMS exactly like the hand-authored ones under `courses/`:

    course-v1:InnotelLabs+ACCT201+2026_T1

The package is a *course shell*, not invented courseware. It carries what the
plan actually says — the description, credits, prerequisites, the programme and
semester it belongs to, how many classroom modules it runs, and the final
examination blueprint with its weights and pass mark — plus the orientation and
syllabus pages every learner needs on day one. Lessons are not fabricated: when
the course's classrooms are generated they are added to the same course key (see
`build-classrooms.py --publish`), which is why the key is derived from the code
and never re-derived once the course exists.

Publishing is idempotent. A course already in the LMS is left alone, so running
this on every boot is safe; a course that is missing is added.

    python3 scripts/publish-courses.py                      # plan, touches nothing
    python3 scripts/publish-courses.py --execute            # publish what is missing
    python3 scripts/publish-courses.py --program <id> --execute
    python3 scripts/publish-courses.py --course ACCT201 --execute
    python3 scripts/publish-courses.py --program <id> --enroll learner@x.edu
    python3 scripts/publish-courses.py --json

After the imports the CMS is reindexed so the new courses appear in the catalog
search the learner dashboard and *Explore courses* read from.

Exit codes: 0 ok, 1 a course failed to publish (or the LMS could not be reached).

Stdlib only, like every other script in this tree.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

DEFAULTS = {
    "ORG": "InnotelLabs",
    "CMS_CONTAINER": "tutor_local-cms-1",
    "LMS_CONTAINER": "tutor_local-lms-1",
    "EDX_PLATFORM": "/openedx/edx-platform",
    "EDX_DATA_DIR": "/openedx/data",
    "PYTHON": "python",
    #: How long a course list from the LMS is reused before asking again.
    "KEYS_TTL": 30,
    #: The enrolment mode a learner is given. Everything on this deployment is
    #: open (honor); a paid course adds its own verified mode at checkout.
    "MODE": "honor",
    "SIGNATORY": "Darnel Hunter",
    "SIGNATORY_ORG": "Innotel Labs",
}

#: Seasons the console writes into `startTerm`, and the quarter each one is.
SEASON_QUARTER = {"winter": 1, "spring": 2, "summer": 3, "fall": 4, "autumn": 4}


def _module(name, path):
    """Import a sibling script by path (their filenames carry hyphens)."""
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def programs_module():
    """`program-manager.py`: the shape of a program, and how a course is assessed."""
    return _module("atheniq_program_manager", os.path.join(HERE, "program-manager.py"))


class LmsError(RuntimeError):
    """The LMS could not be reached or refused a command."""


# -- keys and terms -----------------------------------------------------------


def term_for(program: dict, clock=time.time) -> str:
    """The run a new course is created under, e.g. `2026_T4`.

    A programme names its first term ("Fall 2026", "2027_T2"); when it does not,
    the term the programme was created in is the next best answer, and the current
    quarter when even that is missing. The run is part of the course key, so it is
    derived once and then left alone — publishing again must not mint a second run
    of the same course.
    """
    label = str(program.get("startTerm") or "").strip()
    when = None
    from_label = re.search(r"(20\d{2})-(\d{2})-(\d{2})", label)
    if from_label:
        when = dt.date(int(from_label.group(1)), int(from_label.group(2)),
                       int(from_label.group(3)))
    year_match = re.search(r"(20\d{2})", label)
    year = int(year_match.group(1)) if year_match else None
    explicit = re.search(r"_?T([1-4])\b", label, re.IGNORECASE)
    if year and explicit:
        return f"{year}_T{explicit.group(1)}"
    if year:
        quarter = None
        for word, number in SEASON_QUARTER.items():
            if word in label.lower():
                quarter = number
                break
        if quarter is None:
            quarter = _quarter(when or _date_from_stamp(program.get("createdAt")) or
                               dt.datetime.fromtimestamp(clock(), dt.timezone.utc).date())
        return f"{year}_T{quarter}"
    if when is None:
        when = _date_from_stamp(program.get("createdAt")) or \
            dt.datetime.fromtimestamp(clock(), dt.timezone.utc).date()
    return f"{when.year}_T{_quarter(when)}"


def _quarter(day: dt.date) -> int:
    return (day.month - 1) // 3 + 1


def _date_from_stamp(stamp) -> dt.date | None:
    try:
        return dt.datetime.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ").date()
    except (TypeError, ValueError):
        return None


def course_key(code: str, term: str, org: str = DEFAULTS["ORG"]) -> str:
    return f"course-v1:{org}+{str(code).strip().upper()}+{term}"


def key_index(keys) -> dict[str, str]:
    """Map a course code to the run the LMS already holds for it.

    A course may already exist under a hand-picked run (`DATA101`'s `2026_T1`)
    rather than the term a programme would derive. The code, not the run, is what
    identifies a course for a learner, so an existing key always wins.
    """
    index = {}
    for key in keys or ():
        parts = str(key).split("+")
        if len(parts) != 3 or not key.startswith("course-v1:"):
            continue
        code = parts[1].strip().upper()
        index.setdefault(code, key)
    return index


# -- the OLX shell ------------------------------------------------------------


def _dates(term: str) -> dict[str, str]:
    """The run's dates: it opens two months early and stays open for two years."""
    match = re.match(r"^(\d{4})_T([1-4])$", term)
    year = int(match.group(1)) if match else dt.date.today().year
    quarter = int(match.group(2)) if match else _quarter(dt.date.today())
    start = dt.datetime(year, 3 * (quarter - 1) + 1, 1, tzinfo=dt.timezone.utc)
    return {
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enrollment_start": (start - dt.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enrollment_end": (start + dt.timedelta(days=730)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text if text.endswith("\n") else text + "\n")


def _xml(text: str) -> str:
    return html.escape(str(text), quote=True)


def entry_for(course: dict, program: dict, semester: dict, term: str,
              key: str | None = None, published: bool = False) -> dict:
    """Everything the shell (and the CLI's report) needs about one course."""
    code = str(course.get("code") or "").strip().upper()
    return {
        "code": code,
        "title": course.get("title") or code,
        "credits": int(course.get("credits") or 3),
        "description": course.get("description") or "",
        "prerequisites": list(course.get("prerequisites") or []),
        "finalExam": course.get("finalExam") or "comprehensive",
        "kind": course.get("kind") or "core",
        "classrooms": int(course.get("classrooms") or 4),
        "semester": int(semester.get("number") or 0),
        "semesterName": semester.get("name") or "",
        "program": program.get("name") or "",
        "programId": program.get("id") or "",
        "credential": program.get("credential") or "",
        "credentialKind": program.get("credentialKind") or "degree",
        "totalCredits": program.get("totalCredits"),
        "term": term,
        "key": key or course_key(code, term),
        "published": bool(published),
        "slug": f"{code}-{term}",
    }


def _welcome_html(entry: dict) -> str:
    seats = entry["classrooms"]
    return "".join([
        f"<h2>{html.escape(entry['code'])} — {html.escape(entry['title'])}</h2>\n",
        f"<p>{html.escape(entry['description'])}</p>\n" if entry["description"] else "",
        "<p>This course is part of <strong>", html.escape(entry["program"]),
        "</strong>", html.escape(f" ({entry['credential']})"),
        f", semester {entry['semester']}", html.escape(f" — {entry['semesterName']}" if entry["semesterName"] else ""),
        f". It is worth {entry['credits']} credits.</p>\n",
        f"<p>The course runs in {seats} classroom module{'s' if seats != 1 else ''}. "
        "Each module's live classroom and its lessons are published in this course "
        "as they are built; the syllabus below is what the course commits to now.</p>\n",
        "<p>Start with the syllabus, then the course plan.</p>\n",
    ])


def _syllabus_html(entry: dict) -> str:
    blueprint = programs_module().final_exam_blueprint(entry)
    prereq = ", ".join(entry["prerequisites"]) or "None — this is an entry course."
    return "".join([
        "<h2>Syllabus</h2>\n",
        "<h3>Credits and place in the programme</h3>\n",
        f"<p>{entry['credits']} credits, semester {entry['semester']} of "
        f"{html.escape(entry['program'])} — {html.escape(entry['credential'])}.</p>\n",
        "<h3>Prerequisites</h3>\n",
        f"<p>{html.escape(prereq)}</p>\n",
        "<h3>How the course runs</h3>\n",
        f"<p>{entry['classrooms']} classroom module{'s' if entry['classrooms'] != 1 else ''}, "
        "each one a live session with an AI teacher and AI classmates on OpenMAIC, "
        "followed by the module's own work in this course.</p>\n",
        "<h3>Assessment</h3>\n",
        f"<p>{html.escape(blueprint['label'])} — {blueprint['weight']}% of the course "
        f"mark ({html.escape(blueprint['duration'])}). The course is passed at "
        f"{programs_module().course_pass_mark(entry):.0f}%.</p>\n",
        "<p>Grades are recorded by the programme office and shown in your progress "
        "on the learner portal.</p>\n",
    ])


def _plan_html(entry: dict) -> str:
    seats = entry["classrooms"]
    items = "".join(f"<li>Classroom module {number}</li>\n" for number in range(1, seats + 1))
    return "".join([
        "<h2>Course plan</h2>\n",
        f"<p>{html.escape(entry['title'])} is taught in {seats} classroom "
        f"module{'s' if seats != 1 else ''}, in this order:</p>\n",
        f"<ol>\n{items}</ol>\n",
        "<p>Each module's classroom is built on OpenMAIC and added to this course "
        "when it is generated. Until then this page is the course's published "
        "plan: what it teaches, how much it is worth, and how it is assessed.</p>\n",
    ])


def _assessment_html(entry: dict) -> str:
    blueprint = programs_module().final_exam_blueprint(entry)
    rows = "".join(
        f"<tr><td>{html.escape(section['name'])}</td>"
        f"<td>{section['weight']}%</td>"
        f"<td>{html.escape(section['detail'])}</td></tr>\n"
        for section in blueprint["sections"])
    return "".join([
        f"<h2>{html.escape(blueprint['label'])}</h2>\n",
        f"<p>{html.escape(blueprint['guidance'])}</p>\n",
        "<p>",
        html.escape(blueprint["duration"]),
        f" · {blueprint['weight']}% of the course mark · pass at "
        f"{programs_module().course_pass_mark(entry):.0f}%.</p>\n",
        "<table>\n<thead><tr><th>Section</th><th>Weight</th><th>What it asks for</th></tr></thead>\n",
        f"<tbody>\n{rows}</tbody>\n</table>\n",
    ])


def build_shell(entry: dict, dest: str) -> str:
    """Write one course's OLX package under `dest`, returning its `olx/` path.

    The layout is the one the Studio importer and `check-course-olx.py` expect:
    chapter -> sequential -> vertical -> component, with policies, about pages and
    the run's dates. Content is only what the programme plan supports.
    """
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    olx = os.path.join(dest, "olx")
    os.makedirs(olx)
    term = entry["term"]
    dates = _dates(term)
    name = f"{entry['code']} — {entry['title']}"
    chapters = [("c1_start", "Start here", [
        ("s1_welcome", "Welcome", "u1_welcome", "l1_welcome", "Welcome"),
        ("s2_syllabus", "Syllabus", "u2_syllabus", "l2_syllabus", "Syllabus"),
    ]), ("c2_plan", "Course plan", [
        ("s3_plan", "Course plan", "u3_plan", "l3_plan", "Course plan"),
    ]), ("c3_assessment", "Assessment", [
        ("s4_assessment", blueprint_label(entry), "u4_assessment", "l4_assessment",
         "Final examination"),
    ])]

    _write(os.path.join(olx, "course.xml"),
           f'<course url_name="{_xml(term)}" org="{_xml(DEFAULTS["ORG"])}" '
           f'course="{_xml(entry["code"])}"/>')
    course_children = "".join(f'<chapter url_name="{ref}"/>\n' for ref, _, _ in chapters)
    _write(os.path.join(olx, "course", f"{term}.xml"), (
        f'<course display_name="{_xml(name)}" language="en" '
        f'start="{dates["start"]}" enrollment_start="{dates["enrollment_start"]}" '
        f'enrollment_end="{dates["enrollment_end"]}" cert_html_view_enabled="true" '
        f'certificates_display_behavior="CertificatesDisplayBehaviors.END">\n'
        f'{course_children}'
        f'<wiki slug="{_xml(DEFAULTS["ORG"])}.{_xml(entry["code"])}.{_xml(term)}"/>\n'
        '</course>'))

    for chapter_ref, chapter_name, sequentials in chapters:
        kids = "".join(f'<sequential url_name="{seq}"/>\n' for seq, _, _, _, _ in sequentials)
        _write(os.path.join(olx, "chapter", f"{chapter_ref}.xml"),
               f'<chapter display_name="{_xml(chapter_name)}">\n{kids}</chapter>')
        for seq, seq_name, unit, lesson, lesson_name in sequentials:
            _write(os.path.join(olx, "sequential", f"{seq}.xml"), (
                f'<sequential display_name="{_xml(seq_name)}" graded="false" '
                f'show_correctness="always">\n'
                f'<vertical url_name="{unit}"/>\n</sequential>'))
            _write(os.path.join(olx, "vertical", f"{unit}.xml"),
                   f'<vertical display_name="{_xml(seq_name)}">\n'
                   f'<html url_name="{lesson}"/>\n</vertical>')
            _write(os.path.join(olx, "html", f"{lesson}.xml"),
                   f'<html filename="{lesson}" display_name="{_xml(lesson_name)}"/>')

    _write(os.path.join(olx, "html", "l1_welcome.html"), _welcome_html(entry))
    _write(os.path.join(olx, "html", "l2_syllabus.html"), _syllabus_html(entry))
    _write(os.path.join(olx, "html", "l3_plan.html"), _plan_html(entry))
    _write(os.path.join(olx, "html", "l4_assessment.html"), _assessment_html(entry))

    _write(os.path.join(olx, "about", "short_description.html"), "".join([
        f"{entry['code']} — {entry['title']}. ",
        entry["description"] or "",
        f" Part of {entry['program']}.",
    ]))
    _write(os.path.join(olx, "about", "overview.html"), _welcome_html(entry))
    _write(os.path.join(olx, "info", "updates.html"),
           f"<p>{html.escape(name)} is open. The syllabus and the course plan are "
           "published; classroom modules are added as they are built.</p>")

    policy = {
        f"course/{term}": {
            "display_name": name,
            "language": "en",
            "start": dates["start"],
            "enrollment_start": dates["enrollment_start"],
            "enrollment_end": dates["enrollment_end"],
            "cert_html_view_enabled": True,
            "certificates_display_behavior": "CertificatesDisplayBehaviors.END",
            "certificates_show_before_end": True,
            "discussion_topics": {"General": {"id": "course"}},
            "learning_info": [],
            "tabs": [
                {"name": "Course", "type": "courseware", "course_staff_only": False},
                {"name": "Progress", "type": "progress", "course_staff_only": False},
                {"name": "Dates", "type": "dates", "course_staff_only": False},
                {"name": "Discussion", "type": "discussion", "course_staff_only": False},
            ],
            "certificates": {"certificates": [{
                "id": 0,
                "course_title": name,
                "is_active": True,
                "signatories": [{
                    "name": DEFAULTS["SIGNATORY"],
                    "organization": DEFAULTS["SIGNATORY_ORG"],
                    "title": DEFAULTS["SIGNATORY_ORG"],
                }],
            }]},
        },
    }
    _write(os.path.join(olx, "policies", term, "policy.json"),
           json.dumps(policy, indent=2, sort_keys=True))
    # The shell ships no graded assessment yet, so the policy only has to be
    # valid: the mark comes from the programme office until the classroom's
    # problems are imported into this same course key.
    _write(os.path.join(olx, "policies", term, "grading_policy.json"), json.dumps({
        "GRADER": [{"type": "Final Exam", "min_count": 1, "drop_count": 0,
                    "short_label": "Final", "weight": 1.0}],
        "GRADE_CUTOFFS": {"Pass": 0.5},
    }, indent=2, sort_keys=True))
    _write(os.path.join(olx, "policies", "assets.json"), "{}")
    return olx


def blueprint_label(entry: dict) -> str:
    return programs_module().final_exam_blueprint(entry)["label"]


# -- the LMS ------------------------------------------------------------------


class DockerLms:
    """The running Tutor stack, reached through `docker` on this host.

    Every operation is one `docker exec` against the CMS or LMS container, the
    same way `import-courses.py` and `build-classrooms.py` publish a course. No
    Django code is imported here: the tools are called where they live.
    """

    def __init__(self, cms_container=None, lms_container=None, platform=None,
                 data_dir=None, python=None, work_dir=None, run=None,
                 timeout=600):
        self.cms = cms_container or os.environ.get("CMS_CONTAINER", DEFAULTS["CMS_CONTAINER"])
        self.lms = lms_container or os.environ.get("LMS_CONTAINER", DEFAULTS["LMS_CONTAINER"])
        self.platform = platform or DEFAULTS["EDX_PLATFORM"]
        self.data_dir = data_dir or DEFAULTS["EDX_DATA_DIR"]
        self.python = python or DEFAULTS["PYTHON"]
        self.work_dir = work_dir or os.path.join(REPO, "dist", "lms")
        self._run = run or subprocess.run
        self.timeout = timeout

    # -- plumbing ---------------------------------------------------------

    def _docker(self, argv, stdin_text: str | None = None):
        """Run one docker command; a non-zero exit is an `LmsError`, never a no-op."""
        result = self._run(["docker"] + list(argv), capture_output=True, text=True,
                           input=stdin_text, timeout=self.timeout)
        if result.returncode != 0:
            tail = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()[-4:]
            raise LmsError(f"docker {' '.join(argv)[:60]} failed ({result.returncode}): "
                           + " / ".join(tail))
        return result

    def _exec(self, container: str, argv, stdin_text: str | None = None):
        prefix = ["exec", "-i", container] if stdin_text is not None else ["exec", container]
        return self._docker(prefix + list(argv), stdin_text=stdin_text)

    # -- reads ------------------------------------------------------------

    def course_ids(self) -> list[str]:
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms dump_course_ids"])
        keys = []
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("course-v1:"):
                keys.append(line)
        return keys

    # -- writes -----------------------------------------------------------

    def import_olx(self, olx_dir: str, name: str) -> str:
        """Bundle one course's OLX and import it into the CMS."""
        return self.import_batch([(olx_dir, name)])[0]

    def import_batch(self, packages) -> list[str]:
        """Import several courses in one CMS process.

        `manage.py cms import` takes a data directory and any number of course
        directories, and each invocation pays a full Django start-up (tens of
        seconds). A programme is thirty or forty courses, so they are staged with
        one copy and imported by one command instead of one process each.

        The archive holds `{name}/course.xml` for every course, which is exactly
        the layout the importer expects under its data directory.
        """
        packages = [(olx, name) for olx, name in packages if olx]
        if not packages:
            return []
        os.makedirs(self.work_dir, exist_ok=True)
        archive = os.path.join(self.work_dir, "batch.tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            for olx_dir, name in packages:
                tar.add(olx_dir, arcname=name)
        remote = "/tmp/atheniq-courses.tar.gz"
        self._docker(["cp", archive, f"{self.cms}:{remote}"])
        self._exec(self.cms, ["sh", "-c", f"cd {self.data_dir} && tar xzf {remote}"])
        names = " ".join(name for _, name in packages)
        self._exec(self.cms, ["sh", "-c",
                              f"cd {self.platform} && {self.python} ./manage.py cms "
                              f"import {self.data_dir} {names}"])
        return [name for _, name in packages]

    def reindex(self) -> str:
        """Rebuild the catalog search index the MFE catalog reads."""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms "
                                       f"reindex_course --all --setup"])
        return (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""

    def enroll(self, students, keys) -> dict:
        """Enrol learners in courses, creating the honor mode when the course has none.

        This is what puts a course in *My courses*: the dashboard lists a learner's
        enrollments, so a course that nobody is enrolled in is invisible there however
        well it is published.
        """
        students = [str(s).strip() for s in students if str(s).strip()]
        keys = [str(k).strip() for k in keys if str(k).strip()]
        if not students or not keys:
            return {"students": []}
        plan = json.dumps({"students": students, "courses": keys, "mode": DEFAULTS["MODE"]})
        script = f"""
import json
from django.contrib.auth import get_user_model
from common.djangoapps.student.models import CourseEnrollment, CourseMode
from opaque_keys.edx.keys import CourseKey

plan = json.loads({plan!r})
User = get_user_model()
out = []
for ident in plan["students"]:
    user = (User.objects.filter(email__iexact=ident).first()
            or User.objects.filter(username__iexact=ident).first())
    if user is None:
        out.append({{"student": ident, "missing": True, "enrolled": [], "errors": []}})
        continue
    enrolled, errors = [], []
    for key in plan["courses"]:
        try:
            course_key = CourseKey.from_string(key)
            CourseMode.objects.get_or_create(
                course_id=course_key, mode_slug=plan["mode"],
                defaults={{"mode_display_name": "Honor", "currency": "usd", "min_price": 0}})
            CourseEnrollment.enroll(user, course_key, mode=plan["mode"])
            enrolled.append(key)
        except Exception as err:
            errors.append(f"{{key}}: {{err}}")
    out.append({{"student": ident, "user": user.username,
                 "missing": False, "enrolled": enrolled, "errors": errors}})
print("ATHENIQ_ENROLL " + json.dumps(out))
"""
        result = self._exec(self.lms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py lms shell"],
                            stdin_text=script)
        for line in reversed((result.stdout or "").splitlines()):
            if line.startswith("ATHENIQ_ENROLL "):
                return {"students": json.loads(line[len("ATHENIQ_ENROLL "):])}
        raise LmsError("the LMS answered without an enrolment report")


# -- the publisher ------------------------------------------------------------


class Publisher:
    """Programme courses -> real LMS courses, and learners into them.

    The publisher owns no HTTP and no page: the console calls it, and so does the
    CLI. Its only state on disk is the generated OLX under `work_dir` and a record
    of what it published, so a second run is a no-op rather than a duplicate.
    """

    def __init__(self, root: str, work_dir: str | None = None, lms=None,
                 clock=time.time, org: str = DEFAULTS["ORG"]):
        self.root = root
        self.work_dir = work_dir or os.path.join(root, "lms")
        self.lms = lms or DockerLms(work_dir=self.work_dir)
        self.clock = clock
        self.org = org
        self._keys: dict[str, str] | None = None
        self._keys_at = 0.0
        #: Seconds between a failed reindex and its one retry.
        self.retry_delay = 5

    # -- programmes -------------------------------------------------------

    def _programs_dir(self) -> str:
        local = os.path.join(self.root, "programs")
        return local if os.path.isdir(local) else os.path.join(REPO, "programs")

    def programs(self) -> list[dict]:
        out = []
        directory = self._programs_dir()
        if not os.path.isdir(directory):
            return out
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, name), encoding="utf-8") as fh:
                    doc = json.load(fh)
            except (OSError, ValueError):
                continue  # one unreadable program is not a broken catalogue
            if isinstance(doc, dict):
                doc.setdefault("id", os.path.splitext(name)[0])
                out.append(doc)
        return out

    def program(self, program_id: str) -> dict:
        for doc in self.programs():
            if doc.get("id") == program_id:
                return doc
        raise KeyError(program_id)

    # -- what the LMS holds ----------------------------------------------

    def published(self, refresh: bool = False) -> dict[str, str]:
        """Code -> key for every course the LMS already has."""
        now = self.clock()
        if not refresh and self._keys is not None and now - self._keys_at < DEFAULTS["KEYS_TTL"]:
            return self._keys
        self._keys = key_index(self.lms.course_ids())
        self._keys_at = now
        return self._keys

    # -- entries ----------------------------------------------------------

    def entries(self, program: dict, keys: dict[str, str] | None = None,
                codes=None) -> list[dict]:
        keys = self.published() if keys is None else keys
        wanted = {str(code).strip().upper() for code in (codes or [])}
        term = term_for(program, self.clock)
        out = []
        for semester in program.get("semesters") or []:
            for course in semester.get("courses") or []:
                code = str(course.get("code") or "").strip().upper()
                if not code or (wanted and code not in wanted):
                    continue
                existing = keys.get(code)
                out.append(entry_for(course, program, semester, term,
                                     key=existing, published=existing is not None))
        return out

    def plan(self, program_ids=None, codes=None) -> list[dict]:
        """Every selected course, once: two programmes may share a course code.

        The LMS key is the course, not the programme, so a code taught by two
        programmes is one course — publishing it twice would import the same shell
        over itself. The first programme's entry wins, which is also the one the
        report should name.
        """
        wanted = set(program_ids or [])
        keys = self.published(refresh=True)
        out, seen = [], set()
        for program in self.programs():
            if wanted and program.get("id") not in wanted:
                continue
            for entry in self.entries(program, keys, codes):
                if entry["key"] in seen:
                    continue
                seen.add(entry["key"])
                out.append(entry)
        return out

    # -- publish ----------------------------------------------------------

    def _record(self, entries) -> None:
        path = os.path.join(self.work_dir, "published.json")
        try:
            with open(path, encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            record = {}
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))
        for entry in entries:
            record[entry["key"]] = {
                "code": entry["code"], "title": entry["title"],
                "program": entry["programId"], "at": stamp,
            }
        os.makedirs(self.work_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)

    def publish(self, program_ids=None, codes=None, execute: bool = False) -> dict:
        """Create the missing courses in the LMS and reindex the catalogue."""
        try:
            entries = self.plan(program_ids, codes)
        except LmsError as err:
            return {"available": False, "error": str(err), "planned": [],
                    "published": [], "skipped": [], "failed": []}
        pending = [entry for entry in entries if not entry["published"]]
        answer = {
            "available": True,
            "execute": execute,
            "planned": entries,
            "published": [],
            "skipped": [entry for entry in entries if entry["published"]],
            "failed": [],
        }
        if not execute or not pending:
            return answer
        done = []
        packages = []
        for entry in pending:
            dest = os.path.join(self.work_dir, "shells", entry["slug"])
            try:
                packages.append((build_shell(entry, dest), entry["slug"]))
            except (OSError, ValueError) as err:
                answer["failed"].append({"code": entry["code"], "key": entry["key"],
                                         "error": str(err)})
        if packages:
            by_name = {entry["slug"]: entry for entry in pending}
            batch = getattr(self.lms, "import_batch", None)
            try:
                if batch is None:
                    for olx, name in packages:
                        self.lms.import_olx(olx, name)
                else:
                    batch(packages)
                imported = [name for _, name in packages]
            except LmsError as err:
                # One bad course must not cost a programme the other thirty-nine:
                # fall back to importing them one at a time, which says which one
                # failed and why.
                imported = []
                for olx, name in packages:
                    try:
                        self.lms.import_olx(olx, name)
                        imported.append(name)
                    except LmsError as one:
                        entry = by_name[name]
                        answer["failed"].append({"code": entry["code"], "key": entry["key"],
                                                 "error": str(one) or str(err)})
            for name, entry in ((n, by_name[n]) for n in imported):
                entry["published"] = True
                done.append(entry)
                answer["published"].append(entry)
        done.sort(key=lambda entry: entry["code"])
        if done:
            # The index build is cheap and idempotent, so a busy search service gets
            # a second chance: without it a course exists but never lists in Explore.
            for attempt in range(2):
                try:
                    self.lms.reindex()
                    answer["reindexed"] = True
                    answer.pop("reindexError", None)
                    break
                except LmsError as err:
                    answer["reindexed"] = False
                    answer["reindexError"] = str(err)
                    if attempt == 0 and self.retry_delay:
                        time.sleep(self.retry_delay)
            if answer["reindexed"]:
                self._record(done)
            self._keys = None  # the LMS changed; ask again next time
        return answer

    # -- enrol ------------------------------------------------------------

    def enroll(self, program_id: str, student: str) -> dict:
        """Put one learner into every course of a programme, in the LMS."""
        try:
            program = self.program(program_id)
        except KeyError:
            return {"available": False, "error": f"no program {program_id!r}"}
        try:
            entries = self.entries(program)
            keys = [entry["key"] for entry in entries]
            report = self.lms.enroll([student], keys)
        except LmsError as err:
            return {"available": False, "error": str(err), "courses": []}
        return {"available": True, "courses": keys, **report}

    # -- status -----------------------------------------------------------

    def status(self, program_id: str) -> dict:
        """How much of this programme is real in the LMS, for the console page."""
        try:
            program = self.program(program_id)
            # Cached: this answers a page load, and the course list from the CMS
            # is a docker round-trip. Publishing clears the cache.
            keys = self.published()
        except KeyError:
            return {"available": False, "error": "no such program", "published": 0, "courses": 0}
        except LmsError as err:
            return {"available": False, "error": str(err), "published": 0, "courses": 0}
        entries = self.entries(program, keys)
        return {
            "available": True,
            "courses": len(entries),
            "published": sum(1 for entry in entries if entry["published"]),
            "keys": {entry["code"]: entry["key"] for entry in entries},
        }


# -- CLI ----------------------------------------------------------------------


def _default_root() -> str:
    env = os.environ.get("GENERATION_ROOT")
    if env:
        return env
    return REPO if os.path.isdir(os.path.join(REPO, "programs")) else os.getcwd()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=_default_root(),
                    help="root holding programs/ (GENERATION_ROOT)")
    ap.add_argument("--work-dir", help="where the OLX shells are generated (default <root>/lms)")
    ap.add_argument("--program", action="append", help="program id (repeatable)")
    ap.add_argument("--course", action="append", help="course code (repeatable)")
    ap.add_argument("--execute", action="store_true",
                    help="import the missing courses (operator action)")
    ap.add_argument("--enroll", help="a learner identity to enrol in the selected programs")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    publisher = Publisher(args.root, work_dir=args.work_dir)
    if args.enroll:
        if not args.program:
            raise SystemExit("--enroll needs --program (one or more)")
        reports = [publisher.enroll(program_id, args.enroll) for program_id in args.program]
        print(json.dumps(reports, indent=2) if args.json else
              "\n".join(_enroll_line(report) for report in reports))
        return

    answer = publisher.publish(args.program, args.course, execute=args.execute)
    if args.json:
        print(json.dumps(answer, indent=2, sort_keys=True))
        sys.exit(1 if answer.get("failed") else 0)

    if not answer["available"]:
        print(f"error: the LMS is not reachable: {answer['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"LMS courses — {len(answer['planned'])} course(s) in "
          f"{len({p.get('programId') for p in answer['planned']})} program(s)")
    for entry in answer["skipped"]:
        print(f"  {entry['key']:<44} {entry['title'][:38]:<40} in the LMS")
    for entry in answer["published"]:
        print(f"  {entry['key']:<44} {entry['title'][:38]:<40} published")
    for failure in answer["failed"]:
        print(f"  {failure['key']:<44} FAILED: {failure['error']}", file=sys.stderr)
    if not args.execute:
        print("\n(plan only — pass --execute to create the missing courses)")
    elif answer.get("published"):
        print(f"\nreindexed catalog search: {answer.get('reindexed')}")
        if answer.get("reindexError"):
            print(f"  error: {answer['reindexError']}", file=sys.stderr)
    sys.exit(1 if answer["failed"] else 0)


def _enroll_line(report: dict) -> str:
    if not report.get("available"):
        return f"error: {report.get('error')}"
    lines = []
    for row in report.get("students") or []:
        if row.get("missing"):
            lines.append(f"{row['student']}: no LMS account — they are enrolled when they sign in")
            continue
        lines.append(f"{row['student']} ({row['user']}): {len(row['enrolled'])}/{len(report['courses'])} courses")
        for error in row.get("errors") or []:
            lines.append(f"  {error}")
    return "\n".join(lines) or "nothing to enrol"


if __name__ == "__main__":
    main()
