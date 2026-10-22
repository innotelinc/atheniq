#!/usr/bin/env python3
"""AthenIQ — publish a program's courses into the LMS as real courses.

A program in the console is a plan: semesters, course codes, credits,
prerequisites, final examinations. Until this tool existed those codes were only
that — a line in a JSON file. A learner could read the program, but the course
was not in the LMS: it was not in *Explore courses*, it could not be enrolled in,
and so it could never appear in *My courses*.

This tool closes that gap. For every course in a program it writes a real OLX
course package and imports it into the running CMS, so the course exists in the
LMS exactly like the hand-authored ones under `courses/`:

    course-v1:InnotelLabs+ACCT201+2026_T1

The package is a *course shell*, not invented courseware. It carries what the
plan actually says — the description, credits, prerequisites, the program and
semester it belongs to, how many classroom modules it runs, and the final
examination blueprint with its weights and pass mark — plus the orientation and
syllabus pages every learner needs on day one.

A shell becomes a course when its classroom is generated. `attach()` reads that
classroom's outline (the lessons the teacher-agent actually planned: a title,
key points, a description) and its quizzes (questions with the answers), writes
one chapter per lesson plus a graded final examination assembled from those
questions, and imports the course again under the same key. The LMS then holds
real lessons and a real exam, so a learner's course grade is computed there
rather than typed in by an office — see `grades()`.

Publishing is idempotent. A course already in the LMS is left alone, so running
this on every boot is safe; a course that is missing is added. Attaching lessons
rebuilds one course in place, with stable component ids, so importing again
updates it without orphaning a learner's grades.

    python3 scripts/publish-courses.py                      # plan, touches nothing
    python3 scripts/publish-courses.py --execute            # publish what is missing
    python3 scripts/publish-courses.py --program <id> --execute
    python3 scripts/publish-courses.py --course ACCT201 --execute
    python3 scripts/publish-courses.py --attach <program> --course BUS101 --classroom <id>
    python3 scripts/publish-courses.py --program <id> --grades
    python3 scripts/publish-courses.py --program <id> --enroll learner@x.edu
    python3 scripts/publish-courses.py --images             # (re)apply card photographs
    python3 scripts/publish-courses.py --cards              # upload each course's rendered card
    python3 scripts/publish-courses.py --delete-all         # remove every course, reindex
    python3 scripts/publish-courses.py --json

After the imports the CMS is reindexed so the new courses appear in the catalog
search the learner dashboard and *Explore courses* read from. Reindexing also
prunes search documents whose course no longer exists, so a deleted program
cannot leave orphan cards in the catalog.

`--cards` is the catalog's picture half: `scripts/course-cards.py` renders one
card per course from the program plans (title, program, semester, code), and
this uploads each as the course's card asset and points `CourseOverview` at the
matching `/static/atheniq/images/courses/<CODE>.jpg`. The MFE grid reads the
asset through the search index, so both records have to agree.

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
    #: The enrollment mode a learner is given. Everything on this deployment is
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


def photos_module():
    """`course-photos.py`: the course-card photographs."""
    return _module("course_photos", os.path.join(HERE, "course-photos.py"))


def course_image_url(code: str, title: str, description: str = "") -> str:
    """The card photograph for a course, as the LMS will serve it.

    The one place the publisher and the catalog page agree on a course's
    photograph: both call the same resolver, so the same course cannot show one
    picture in the learner catalog and another in the LMS.
    """
    return photos_module().resolve(code, title, description)["url"]


class LmsError(RuntimeError):
    """The LMS could not be reached or refused a command."""


# -- keys and terms -----------------------------------------------------------


def term_for(program: dict, clock=time.time) -> str:
    """The run a new course is created under, e.g. `2026_T4`.

    A program names its first term ("Fall 2026", "2027_T2"); when it does not,
    the term the program was created in is the next best answer, and the current
    quarter when even that is missing. The run is part of the course key, so it is
    derived once and then left alone — publishing again must not mint a second run
    of the same course.

    `runTerm` is an explicit override for a cohort whose calendar label and
    quarter disagree — "Spring 2027" that opens in January, for instance. The
    label stays the human-facing one; the key stays a term.
    """
    explicit_run = str(program.get("runTerm") or "").strip()
    if re.fullmatch(r"20\d{2}_T[1-4]", explicit_run):
        return explicit_run
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
    rather than the term a program would derive. The code, not the run, is what
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


def _dates(term: str, early_start: str | None = None,
           first_day: str | None = None) -> dict[str, str]:
    """The run's dates: it opens two months early and stays open for two years.

    `early_start` is an ISO date the course actually opens on, when the cohort
    wants learners to begin before the term's first day. The advertised start
    stays the term's, so the catalogue still says which semester the run belongs
    to; the linked material is open from the earlier date.

    `first_day` is the cohort's real first day, when the calendar and the
    quarter disagree: Spring 2027 opens on 11 January, not on the 1st, and the
    catalogue reads the advertised start — a course that says 1 January in a
    cohort that begins on the 11th is wrong to every applicant who reads it.
    """
    match = re.match(r"^(\d{4})_T([1-4])$", term)
    year = int(match.group(1)) if match else dt.date.today().year
    quarter = int(match.group(2)) if match else _quarter(dt.date.today())
    start = dt.datetime(year, 3 * (quarter - 1) + 1, 1, tzinfo=dt.timezone.utc)
    if first_day:
        try:
            start = dt.datetime.fromisoformat(str(first_day)).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
    opens = start
    if early_start:
        try:
            opens = dt.datetime.fromisoformat(str(early_start)).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            opens = start
    enrollment_start = min(opens, start) - dt.timedelta(days=60)
    return {
        "start": opens.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "advertised_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enrollment_start": enrollment_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        "earlyStart": program.get("earlyAccessStart") or None,
        "firstDay": program.get("firstDay") or None,
        "credential": program.get("credential") or "",
        "credentialKind": program.get("credentialKind") or "degree",
        "totalCredits": program.get("totalCredits"),
        "term": term,
        "key": key or course_key(code, term),
        "published": bool(published),
        "slug": f"{code}-{term}",
        #: The generated classroom that teaches this course, once there is one,
        #: and the lessons read out of it by `attach()`.
        "classroomId": next(iter(course.get("classroomIds") or []), None),
        "lessons": list(course.get("lessons") if isinstance(course.get("lessons"), list) else []),
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
        "<h3>Credits and place in the program</h3>\n",
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
        (f"<p>{len(questions)} question{'s' if len(questions) != 1 else ''} from the "
         "course's generated lessons form the examination in this course; the LMS "
         "grades it and reports the mark here and in the program office.</p>\n"
         if (questions := [q for lesson in (entry.get("lessons") or [])
                           for q in (lesson.get("questions") or [])])
         else "<p>Grades are recorded by the program office and shown in your progress "
              "on the learner portal.</p>\n"),
    ])


def _plan_html(entry: dict) -> str:
    lessons = entry.get("lessons") or []
    seats = entry["classrooms"]
    if lessons:
        items = "".join(
            f"<li>{html.escape(lesson['title'])}"
            f"{' — ' + str(len(lesson['questions'])) + ' check' + ('s' if len(lesson['questions']) != 1 else '') if lesson['questions'] else ''}</li>\n"
            for lesson in lessons)
        return "".join([
            "<h2>Course plan</h2>\n",
            f"<p>{html.escape(entry['title'])} is taught in {len(lessons)} "
            f"lesson{'s' if len(lessons) != 1 else ''}, in this order:</p>\n",
            f"<ol>\n{items}</ol>\n",
            "<p>Each lesson is a chapter of the course's generated classroom: the "
            "live multi-agent session, followed by the checks it produced. The "
            "final examination is assembled from those checks.</p>\n",
        ])
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


def _classroom_url(stage_id: str) -> str:
    host = os.environ.get("CLASSROOM_HOST", "https://classroom.innotel.us").rstrip("/")
    return f"{host}/classroom/{stage_id}"


def _lesson_html(entry: dict, lesson: dict, index: int) -> str:
    """One generated lesson: what it teaches, then the live classroom itself."""
    points = lesson.get("key_points") or []
    parts = [
        f"<h2>Module {index} — {html.escape(lesson.get('title') or 'Lesson')}</h2>\n",
        f"<p>{html.escape(lesson['description'])}</p>\n" if lesson.get("description") else "",
        "<h3>What this lesson covers</h3>\n",
        "<ul>\n" + "".join(f"<li>{html.escape(point)}</li>\n" for point in points) + "</ul>\n"
        if points else "",
    ]
    stage = entry.get("classroomId") or lesson.get("classroomId")
    if stage:
        url = _classroom_url(stage)
        title = html.escape(lesson.get("title") or "classroom")
        parts.append(
            '<div class="openmaic-classroom">\n'
            f'<h4>Live classroom: {title}</h4>\n'
            "<p>Run this lesson as a multi-agent classroom: an AI teacher, AI "
            "classmates, and the scenario from the lesson — with you in the room.</p>\n"
            f'<p><a href="{url}" target="_blank" rel="noopener">Open “{title}” at '
            'classroom.innotel.us</a></p>\n'
            f'<iframe src="{url}" title="{title} — OpenMAIC classroom" width="100%"\n'
            '  height="680" loading="lazy" allow="microphone; camera; fullscreen"\n'
            '  allowfullscreen\n'
            '  style="border:1px solid #22323d;border-radius:12px;background:#0a1118"></iframe>\n'
            "<p><small>If the classroom does not load in the page, open it in a new "
            "tab and sign in with your AthenIQ account.</small></p>\n"
            "</div>\n")
    return "".join(parts)


def _problem_xml(question: dict, display_name: str) -> str:
    """One generated quiz question as a graded Open edX problem."""
    prompt = html.escape(str(question.get("prompt") or ""), quote=False)
    options = question.get("options") or []
    choices = "".join(
        f'<choice correct="{"true" if option.get("correct") else "false"}">'
        f'<div>{html.escape(str(option.get("label") or option.get("value") or ""))}</div>'
        '</choice>\n' for option in options)
    if question.get("kind") == "multiple":
        body = ("<choiceresponse>\n"
                f"<p>{prompt}</p>\n"
                "<checkboxgroup>\n" + choices + "</checkboxgroup>\n")
    else:
        body = ("<multiplechoiceresponse>\n"
                f"<p>{prompt}</p>\n"
                '<choicegroup type="MultipleChoice">\n' + choices + "</choicegroup>\n")
    if question.get("solution"):
        body += ('<solution>\n<div class="detailed-solution">\n'
                 f"<p>{html.escape(str(question['solution']))}</p>\n"
                 "</div>\n</solution>\n")
    body += "</multiplechoiceresponse>" if question.get("kind") != "multiple" else "</choiceresponse>"
    return (f'<problem display_name="{_xml(display_name)}" max_attempts="3" '
            f'showanswer="finished" weight="1.0">\n{body}\n</problem>')


def build_shell(entry: dict, dest: str) -> str:
    """Write one course's OLX package under `dest`, returning its `olx/` path.

    The layout is the one the Studio importer and `check-course-olx.py` expect:
    chapter -> sequential -> vertical -> component, with policies, about pages and
    the run's dates. Content is only what the program plan supports — plus, once
    the classroom exists, the lessons that classroom actually generated and the
    final examination assembled from their questions.
    """
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    olx = os.path.join(dest, "olx")
    os.makedirs(olx)
    term = entry["term"]
    dates = _dates(term, entry.get("earlyStart"), entry.get("firstDay"))
    name = f"{entry['code']} — {entry['title']}"
    lessons = list(entry.get("lessons") or [])
    exam = [(index, question)
            for index, lesson in enumerate(lessons, 1)
            for question in (lesson.get("questions") or [])]
    chapters = [("c1_start", "Start here", [
        ("s1_welcome", "Welcome", "u1_welcome", "l1_welcome", "Welcome"),
        ("s2_syllabus", "Syllabus", "u2_syllabus", "l2_syllabus", "Syllabus"),
    ]), ("c2_plan", "Course plan", [
        ("s3_plan", "Course plan", "u3_plan", "l3_plan", "Course plan"),
    ])]

    _write(os.path.join(olx, "course.xml"),
           f'<course url_name="{_xml(term)}" org="{_xml(DEFAULTS["ORG"])}" '
           f'course="{_xml(entry["code"])}"/>')
    children = ([ref for ref, _, _ in chapters]
                + [f"l{index}" for index in range(1, len(lessons) + 1)]
                + ["c3_assessment"])
    course_children = "".join(f'<chapter url_name="{ref}"/>\n' for ref in children)
    _write(os.path.join(olx, "course", f"{term}.xml"), (
        f'<course display_name="{_xml(name)}" language="en" '
        f'start="{dates["start"]}" advertised_start="{dates["advertised_start"]}" '
        f'enrollment_start="{dates["enrollment_start"]}" '
        f'enrollment_end="{dates["enrollment_end"]}" cert_html_view_enabled="true" '
        f'certificates_display_behavior="CertificatesDisplayBehaviors.END">\n'
        f'{course_children}'
        f'<wiki slug="{_xml(DEFAULTS["ORG"])}.{_xml(entry["code"])}.{_xml(term)}"/>\n'
        '</course>'))

    for chapter_ref, chapter_name, sequentials in chapters:
        kids = "".join(f'<sequential url_name="{seq}"/>\n' for seq, _, _, _, _ in sequentials)
        _write(os.path.join(olx, "chapter", f"{chapter_ref}.xml"),
               f'<chapter display_name="{_xml(chapter_name)}">\n{kids}</chapter>')
        for seq, seq_name, unit, lesson_ref, lesson_name in sequentials:
            _write(os.path.join(olx, "sequential", f"{seq}.xml"), (
                f'<sequential display_name="{_xml(seq_name)}" graded="false" '
                f'show_correctness="always">\n'
                f'<vertical url_name="{unit}"/>\n</sequential>'))
            _write(os.path.join(olx, "vertical", f"{unit}.xml"),
                   f'<vertical display_name="{_xml(seq_name)}">\n'
                   f'<html url_name="{lesson_ref}"/>\n</vertical>')
            _write(os.path.join(olx, "html", f"{lesson_ref}.xml"),
                   f'<html filename="{lesson_ref}" display_name="{_xml(lesson_name)}"/>')

    # One chapter per generated lesson. The lesson page is the classroom; the
    # questions the classroom produced sit beside it as a check, so a learner can
    # see where they stand before the final.
    for index, lesson in enumerate(lessons, 1):
        ref = f"l{index}"
        title = lesson.get("title") or "Lesson"
        chapter_name = f"Module {index} — {title}"
        questions = lesson.get("questions") or []
        kids = f'<sequential url_name="{ref}_study"/>\n'
        if questions:
            kids += f'<sequential url_name="{ref}_check"/>\n'
        _write(os.path.join(olx, "chapter", f"{ref}.xml"), (
            f'<chapter display_name="{_xml(chapter_name)}">\n'
            f'{kids}</chapter>'))
        _write(os.path.join(olx, "sequential", f"{ref}_study.xml"), (
            f'<sequential display_name="{_xml(title)}" '
            f'graded="false" show_correctness="always">\n'
            f'<vertical url_name="{ref}_study"/>\n</sequential>'))
        _write(os.path.join(olx, "vertical", f"{ref}_study.xml"), (
            f'<vertical display_name="{_xml(title)}">\n'
            f'<html url_name="{ref}_html"/>\n</vertical>'))
        _write(os.path.join(olx, "html", f"{ref}_html.xml"),
               f'<html filename="{ref}_html" display_name="{_xml(title)}"/>')
        _write(os.path.join(olx, "html", f"{ref}_html.html"),
               _lesson_html(entry, lesson, index))
        if not questions:
            continue
        problems = "".join(f'<problem url_name="{ref}_q{number}"/>\n'
                           for number in range(1, len(questions) + 1))
        _write(os.path.join(olx, "sequential", f"{ref}_check.xml"), (
            '<sequential display_name="Check your understanding" graded="false" '
            'show_correctness="always">\n'
            f'<vertical url_name="{ref}_check"/>\n</sequential>'))
        _write(os.path.join(olx, "vertical", f"{ref}_check.xml"), (
            '<vertical display_name="Check your understanding">\n'
            f'{problems}</vertical>'))
        for number, question in enumerate(questions, 1):
            _write(os.path.join(olx, "problem", f"{ref}_q{number}.xml"),
                   _problem_xml(question, f"Module {index} check {number}"))

    # The assessment chapter: what the final asks for, and — once the lessons
    # exist — the graded examination itself, built from their questions.
    label = blueprint_label(entry)
    kids = '<sequential url_name="s4_assessment"/>\n'
    if exam:
        kids += '<sequential url_name="s5_exam"/>\n'
    _write(os.path.join(olx, "chapter", "c3_assessment.xml"),
           f'<chapter display_name="Assessment">\n{kids}</chapter>')
    _write(os.path.join(olx, "sequential", "s4_assessment.xml"), (
        f'<sequential display_name="{_xml(label)}" graded="false" '
        f'show_correctness="always">\n<vertical url_name="u4_assessment"/>\n</sequential>'))
    _write(os.path.join(olx, "vertical", "u4_assessment.xml"),
           f'<vertical display_name="{_xml(label)}">\n<html url_name="l4_assessment"/>\n</vertical>')
    _write(os.path.join(olx, "html", "l4_assessment.xml"),
           '<html filename="l4_assessment" display_name="Final examination"/>')
    if exam:
        problems = "".join(f'<problem url_name="exam_q{number}"/>\n'
                           for number in range(1, len(exam) + 1))
        _write(os.path.join(olx, "sequential", "s5_exam.xml"), (
            f'<sequential display_name="Final examination" format="Final Exam" '
            f'graded="true" show_correctness="always">\n'
            '<vertical url_name="u5_exam"/>\n</sequential>'))
        _write(os.path.join(olx, "vertical", "u5_exam.xml"), (
            f'<vertical display_name="Final examination">\n{problems}</vertical>'))
        for number, (lesson_index, question) in enumerate(exam, 1):
            _write(os.path.join(olx, "problem", f"exam_q{number}.xml"),
                   _problem_xml(question, f"Final examination — question {number}"))

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
            "advertised_start": dates["advertised_start"],
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
    # valid: the mark comes from the program office until the classroom's
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

    def course_list(self) -> list[tuple[str, str]]:
        """Every course the LMS holds, as `(key, display name)`.

        `course_ids()` answers "what exists" for the publisher's key index; this
        answers "what is *visible*" for the photographs, and a course can be the
        second without being the first: `DATA101` runs under an older key than
        any current program produces, and the catalog still lists it.
        """
        script = """
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

for key, name in CourseOverview.objects.values_list("id", "display_name"):
    print("ATHENIQ_COURSE\\t" + str(key) + "\\t" + str(name or ""))
"""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms shell"],
                            stdin_text=script)
        rows = []
        for line in (result.stdout or "").splitlines():
            if not line.startswith("ATHENIQ_COURSE\t"):
                continue
            _, key, name = line.split("\t", 2)
            rows.append((key.strip(), name.strip()))
        return rows

    def import_olx(self, olx_dir: str, name: str) -> str:
        """Bundle one course's OLX and import it into the CMS."""
        return self.import_batch([(olx_dir, name)])[0]

    def import_batch(self, packages) -> list[str]:
        """Import several courses in one CMS process.

        `manage.py cms import` takes a data directory and any number of course
        directories, and each invocation pays a full Django start-up (tens of
        seconds). A program is thirty or forty courses, so they are staged with
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

    def delete_courses(self, keys) -> dict:
        """Remove courses from the LMS, with their content and enrollments.

        A deleted program must not leave its courses in Explore for a learner to
        enroll in, so the course is deleted rather than hidden. The CMS command
        asks twice and cannot be skipped, so it is answered here: a person
        deleting a program has already been asked.
        """
        keys = [str(key).strip() for key in keys if str(key).strip()]
        deleted, failed = [], []
        for key in keys:
            if not re.match(r"^course-v1:[A-Za-z0-9_.:+\-]+$", key):
                failed.append({"key": key, "error": "that is not a course key"})
                continue
            try:
                self._exec(self.cms, ["sh", "-c",
                                      f"cd {self.platform} && {self.python} ./manage.py cms "
                                      f"delete_course {key}"],
                           stdin_text="yes\nyes\n")
                deleted.append(key)
            except LmsError as err:
                failed.append({"key": key, "error": str(err)})
        return {"deleted": deleted, "failed": failed}

    def delete_all_courses(self) -> dict:
        """Delete every course the CMS holds, in one process.

        `delete_course` is a management command that asks twice; calling it once
        per course would also pay a Django start-up per course, which on a
        hundred-course estate is most of an hour. This runs the same function
        (`contentstore.utils.delete_course`) in a loop inside one shell, then
        removes the learner records that belong to the course: its enrollments
        and its `CourseOverview` row, so a deleted course cannot linger in
        Explore or in a learner's *My courses*.
        """
        try:
            keys = self.course_ids()
        except LmsError as err:
            return {"available": False, "error": str(err), "deleted": [], "failed": []}
        if not keys:
            return {"available": True, "deleted": [], "failed": []}
        script = f"""
import json
from common.djangoapps.student.models import CourseEnrollment
from cms.djangoapps.contentstore.utils import delete_course
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore

keys = json.loads({json.dumps(keys)!r})
deleted, failed = [], []
for raw in keys:
    try:
        key = CourseKey.from_string(raw)
        if modulestore().get_course(key):
            delete_course(key, ModuleStoreEnum.UserID.mgmt_command, False)
        CourseEnrollment.objects.filter(course_id=key).delete()
        CourseOverview.objects.filter(id=key).delete()
        deleted.append(raw)
    except Exception as err:  # noqa: BLE001 - one bad course must not stop the rest
        failed.append({{"key": raw, "error": str(err)[:300]}})
print("ATHENIQ_DELETED " + json.dumps({{"deleted": deleted, "failed": failed}}))
"""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms shell"],
                            stdin_text=script)
        report = None
        for line in (result.stdout or "").splitlines():
            if line.startswith("ATHENIQ_DELETED "):
                report = json.loads(line[len("ATHENIQ_DELETED "):])
        if report is None:
            return {"available": False, "error": "the CMS returned no deletion report",
                    "deleted": [], "failed": []}
        return {"available": True, **report}

    def set_course_images(self, mapping) -> dict:
        """Write each course's card photograph into its `CourseOverview`.

        `course_image_url` is what the catalog API, the learner dashboard and
        Studio's schedule page all read; `banner_image_url` is the wide image on
        the course home. Both are set to the same photograph — an imported shell
        otherwise carries the platform's placeholder asset, so a learner would
        see the wrong picture on the course page and the right one on its card.
        The photograph itself is a URL into the LMS's own static files
        (`/static/atheniq/images/courses/…`) — not an upload per course — so one
        pool serves every course and a re-publish only rewrites a string.

        The overview is cached, and the LMS keeps its own cache namespace, so
        both are cleared: without that, the card can show the old tile until the
        cache expires, which reads as "the photo did not apply".
        """
        plan = {str(key).strip(): str(url).strip()
                for key, url in (mapping or {}).items() if key and url}
        if not plan:
            return {"updated": [], "missing": []}
        script = f"""
import json
from django.core.cache import cache
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

plan = json.loads({json.dumps(plan)!r})
updated, missing = [], []
for key, url in plan.items():
    if CourseOverview.objects.filter(id=key).update(course_image_url=url, banner_image_url=url):
        updated.append(key)
    else:
        missing.append(key)
cache.clear()
print("ATHENIQ_IMAGES " + json.dumps({{"updated": updated, "missing": missing}}))
"""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms shell"],
                            stdin_text=script)
        report = None
        for line in (result.stdout or "").splitlines():
            if line.startswith("ATHENIQ_IMAGES "):
                report = json.loads(line[len("ATHENIQ_IMAGES "):])
        if report is None:
            raise LmsError("the CMS did not report which course images were written")
        # The LMS caches overviews under its own key prefix; a clear on the CMS
        # side does not reach them.
        self._exec(self.lms, ["sh", "-c",
                              f"cd {self.platform} && {self.python} ./manage.py lms shell"],
                   stdin_text="from django.core.cache import cache\ncache.clear()\n")
        return report

    def set_course_dates(self, mapping) -> dict:
        """Write each course's cohort dates into the course itself.

        The catalogue's "Starts" line and the course page's schedule both read
        the run's own `start` and `advertised_start`; neither is a display
        preference, so a cohort that opens on 11 January has to be written into
        every existing run, not just the one published next.

        `advertised_start` is what the catalogue shows, `start` is when the
        material opens — the cohort's early-access date when there is one — so a
        learner can begin now while the card still says when the class begins.
        """
        plan = {str(key).strip(): value for key, value in (mapping or {}).items()
                if key and value}
        if not plan:
            return {"updated": [], "missing": []}
        script = f"""
import datetime
import json
from django.core.cache import cache
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore

plan = json.loads({json.dumps(plan)!r})
updated, missing = [], []
for key, dates in plan.items():
    course_key = CourseKey.from_string(key)
    course = modulestore().get_course(course_key)
    if course is None:
        missing.append(key)
        continue
    opens = datetime.datetime.fromisoformat(dates["start"]).replace(tzinfo=datetime.timezone.utc)
    course.start = opens
    course.advertised_start = dates["advertisedStart"]
    modulestore().update_item(course, ModuleStoreEnum.UserID.mgmt_command)
    updated.append(key)
if updated:
    CourseOverview.update_select_courses(
        [CourseKey.from_string(key) for key in updated], force_update=True)
cache.clear()
print("ATHENIQ_DATES " + json.dumps({{"updated": updated, "missing": missing}}))
"""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms shell"],
                            stdin_text=script)
        report = None
        for line in (result.stdout or "").splitlines():
            if line.startswith("ATHENIQ_DATES "):
                report = json.loads(line[len("ATHENIQ_DATES "):])
        if report is None:
            raise LmsError("the CMS did not report which course dates were written")
        self._exec(self.lms, ["sh", "-c",
                              f"cd {self.platform} && {self.python} ./manage.py lms shell"],
                   stdin_text="from django.core.cache import cache\ncache.clear()\n")
        return report

    def apply_course_cards(self, plan) -> dict:
        """Upload each course's rendered card as its own card asset.

        The learner catalog does not read `CourseOverview.course_image_url` for
        its grid: it reads `image_url` from the search index, and the index
        takes that from the course's *card asset*. A course whose asset is
        missing therefore shows the platform's graduation-cap placeholder no
        matter how correct its overview is. So the rendered card is uploaded as
        `images_course_image.jpg` — the name the shells' course block already
        carries — and the block is pointed at it explicitly.

        `plan` maps course key -> rendered JPEG path.
        """
        plan = {str(key).strip(): str(path) for key, path in (plan or {}).items()
                if key and path and os.path.isfile(path)}
        if not plan:
            return {"uploaded": [], "failed": []}

        stage = os.path.join(self.work_dir, "cards")
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        names = {}
        for index, (key, path) in enumerate(sorted(plan.items())):
            name = f"{index:03d}.jpg"
            shutil.copyfile(path, os.path.join(stage, name))
            names[name] = key
        with open(os.path.join(stage, "plan.json"), "w", encoding="utf-8") as fh:
            json.dump(names, fh)

        archive = os.path.join(self.work_dir, "cards.tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(stage, arcname="atheniq-cards")
        # The CMS runs as `app`; an archive docker-cp'd as root cannot be
        # removed by it, and failing to clean a /tmp file must not abort the
        # upload. Stale copies are overwritten by the extraction below.
        self._exec(self.cms, ["sh", "-c",
                              "rm -rf /tmp/atheniq-cards /tmp/atheniq-cards.tar.gz || true"])
        self._docker(["cp", archive, f"{self.cms}:/tmp/atheniq-cards.tar.gz"])
        self._exec(self.cms, ["sh", "-c", "cd /tmp && tar xzf atheniq-cards.tar.gz"])

        script = """
import json
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from cms.djangoapps.contentstore.views.assets import update_course_run_asset
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import modulestore

with open("/tmp/atheniq-cards/plan.json", encoding="utf-8") as fh:
    plan = json.load(fh)

uploaded, failed = [], []
for name, key in sorted(plan.items()):
    try:
        course_key = CourseKey.from_string(key)
        with open("/tmp/atheniq-cards/" + name, "rb") as fh:
            data = fh.read()
        upload = SimpleUploadedFile("images_course_image.jpg", data, content_type="image/jpeg")
        update_course_run_asset(course_key, upload)
        course = modulestore().get_course(course_key)
        if course is not None and course.course_image != "images_course_image.jpg":
            course.course_image = "images_course_image.jpg"
            modulestore().update_item(course, ModuleStoreEnum.UserID.mgmt_command)
        uploaded.append(key)
    except Exception as err:  # noqa: BLE001 - one bad card must not stop the rest
        failed.append({"key": key, "error": str(err)[:300]})
cache.clear()
print("ATHENIQ_CARDS " + json.dumps({"uploaded": uploaded, "failed": failed}))
"""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms shell"],
                            stdin_text=script)
        report = None
        for line in (result.stdout or "").splitlines():
            if line.startswith("ATHENIQ_CARDS "):
                report = json.loads(line[len("ATHENIQ_CARDS "):])
        if report is None:
            raise LmsError("the CMS did not report which course cards were uploaded")
        return report

    def check_course_cards(self, keys) -> dict:
        """Ask the LMS to serve each course's card asset and report the misses.

        A card that 404s is the failure this whole path exists to prevent, and it
        is invisible from the database: the overview and the asset name can both
        be right while the stored file is gone. So the check is an HTTP request
        against the URL the catalog itself loads.
        """
        script = f"""
import json
import requests
from django.conf import settings

keys = json.loads({json.dumps([str(key) for key in keys])!r})
bad, checked = [], 0
for key in keys:
    path = f"/asset-{{key.replace('course-v1:', 'v1:', 1)}}+type@asset+block@images_course_image.jpg"
    url = settings.LMS_ROOT_URL.rstrip("/") + path
    checked += 1
    try:
        response = requests.get(url, timeout=30)
        size = len(response.content)
        if response.status_code != 200 or size < 20000:
            bad.append({{"key": key, "status": response.status_code, "bytes": size}})
    except Exception as err:  # noqa: BLE001 - report, do not abort the sweep
        bad.append({{"key": key, "error": str(err)[:200]}})
print("ATHENIQ_CARDS_CHECK " + json.dumps({{"checked": checked, "bad": bad}}))
"""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms shell"],
                            stdin_text=script)
        for line in (result.stdout or "").splitlines():
            if line.startswith("ATHENIQ_CARDS_CHECK "):
                return json.loads(line[len("ATHENIQ_CARDS_CHECK "):])
        raise LmsError("the card check returned no report")

    def reindex(self) -> str:
        """Rebuild the catalog search index the MFE catalog reads.

        Reindexing updates the documents of courses that still exist, but it
        does not remove the documents of courses that were deleted: a deleted
        course kept appearing in *Explore courses* with a card and no way to
        open it. So the stale documents are pruned here too, against the
        overviews the LMS actually holds.
        """
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms "
                                       f"reindex_course --all --setup"])
        try:
            self._prune_catalog()
        except LmsError:
            pass  # a running catalog is better than a failed publish
        return (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""

    def _prune_catalog(self) -> dict:
        """Delete search documents whose course the LMS no longer has."""
        script = """
import json
import requests
from django.conf import settings
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview

base = settings.MEILISEARCH_URL.rstrip("/")
key = settings.MEILISEARCH_MASTER_KEY
index = f"{settings.MEILISEARCH_INDEX_PREFIX}course_info"
headers = {"Authorization": f"Bearer {key}"}
# Meilisearch deletes by *primary key*, which for course_info is `_pk`,
# not the course id; sending ids alone silently deletes nothing.
docs = requests.get(f"{base}/indexes/{index}/documents",
                    headers=headers, params={"limit": 10000, "fields": "id,_pk"}, timeout=60).json()
keep = {str(course.id) for course in CourseOverview.objects.all()}
stale = [doc for doc in docs.get("results", []) if doc.get("id") not in keep]
if stale:
    requests.post(f"{base}/indexes/{index}/documents/delete-batch",
                  headers=headers, json=[doc["_pk"] for doc in stale], timeout=120)
print("ATHENIQ_PRUNE " + json.dumps({"stale": [doc["id"] for doc in stale]}))
"""
        result = self._exec(self.cms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py cms shell"],
                            stdin_text=script)
        for line in (result.stdout or "").splitlines():
            if line.startswith("ATHENIQ_PRUNE "):
                return json.loads(line[len("ATHENIQ_PRUNE "):])
        raise LmsError("the catalog prune returned no report")

    def enroll(self, students, keys) -> dict:
        """Enroll learners in courses, creating the honor mode when the course has none.

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
        raise LmsError("the LMS answered without an enrollment report")

    def grades(self, students, keys) -> dict:
        """Each learner's current course grade, computed by the LMS itself.

        The grade comes from the graded problems in the course — which, for a
        published program course, are the final examination's questions — so a
        completion recorded from this is a fact about work the learner did in the
        LMS, not a number typed into an office.
        """
        students = [str(s).strip() for s in students if str(s).strip()]
        keys = [str(k).strip() for k in keys if str(k).strip()]
        if not students or not keys:
            return {"students": []}
        plan = json.dumps({"students": students, "courses": keys})
        script = f"""
import json
from django.contrib.auth import get_user_model
from opaque_keys.edx.keys import CourseKey
from lms.djangoapps.grades.course_grade_factory import CourseGradeFactory

plan = json.loads({plan!r})
User = get_user_model()
factory = CourseGradeFactory()
out = []
for ident in plan["students"]:
    user = (User.objects.filter(email__iexact=ident).first()
            or User.objects.filter(username__iexact=ident).first())
    if user is None:
        out.append({{"student": ident, "missing": True, "courses": []}})
        continue
    rows = []
    for key in plan["courses"]:
        try:
            course_key = CourseKey.from_string(key)
            # The stored grade is written when a problem is submitted, so a
            # learner who has not done the work has no grade at all. `read` (not
            # `update`) is what preserves that distinction: recomputing would
            # hand every course a 0% and look like forty failures.
            grade = factory.read(user, course_key=course_key)
            attempted = bool(getattr(grade, "attempted", False))
            percent = grade.percent if attempted else None
            rows.append({{"course": key,
                         "percent": None if percent is None else round(float(percent) * 100, 2),
                         "passed": bool(attempted and grade.passed),
                         "letter": (grade.letter_grade or "") if attempted else ""}})
        except Exception as err:
            rows.append({{"course": key, "percent": None, "passed": False,
                         "error": str(err)[:200]}})
    out.append({{"student": ident, "user": user.username,
                 "missing": False, "courses": rows}})
print("ATHENIQ_GRADES " + json.dumps(out))
"""
        result = self._exec(self.lms, ["sh", "-c",
                                       f"cd {self.platform} && {self.python} ./manage.py lms shell"],
                            stdin_text=script)
        for line in reversed((result.stdout or "").splitlines()):
            if line.startswith("ATHENIQ_GRADES "):
                return {"students": json.loads(line[len("ATHENIQ_GRADES "):])}
        raise LmsError("the LMS answered without a grade report")


# -- the generated classroom -------------------------------------------------


class OpenmaicLessons:
    """The lessons and checks inside a generated classroom, read from OpenMAIC.

    OpenMAIC stores a classroom as an outline (one entry per chapter: title, key
    points, description) plus one scene per chapter, and a quiz scene carries the
    questions with their answers. That is the courseware a program shell has been
    waiting for, so it is read here and written into the course by `attach()`.
    Nothing is invented: a course with no classroom has no lessons.
    """

    def __init__(self, container=None, database="openmaic", user="openmaic",
                 run=None, timeout=90):
        self.container = container or os.environ.get("OPENMAIC_PG_CONTAINER",
                                                     "openmaic-postgres-1")
        self.database = database
        self.user = user
        self._run = run or subprocess.run
        self.timeout = timeout

    def _query(self, sql: str) -> str:
        result = self._run(
            ["docker", "exec", self.container, "psql", "-U", self.user,
             "-d", self.database, "-Atc", sql],
            capture_output=True, text=True, timeout=self.timeout)
        if result.returncode != 0:
            tail = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()[-3:]
            raise LmsError("reading the classroom failed ("
                           + str(result.returncode) + "): " + " / ".join(tail))
        return result.stdout or ""

    @staticmethod
    def _stage(stage_id: str) -> str:
        stage = str(stage_id or "").strip()
        if not re.match(r"^[A-Za-z0-9_-]{1,80}$", stage):
            raise LmsError(f"that is not a classroom id: {stage_id!r}")
        return stage

    def delete(self, stage_id: str) -> dict:
        """Delete a classroom and everything generated inside it.

        The housekeeping tables that reference a stage carry no foreign key, so
        they are deleted in the same transaction as the stage: scene revisions
        (the drafts and their undo history), stage revisions, the asset
        references it made, the withdrawals recorded against it, and the import
        bookkeeping. `document_outlines`, `document_scenes` and `stage_meta`
        cascade from the stage itself.

        The HTTP API cannot do this: its delete is owner-scoped, and a classroom
        submitted without an owner (which is how this deployment generates) is
        matched by no owner, so it answers `{"ok": true}` and removes nothing.
        The delete therefore goes through the same Postgres channel the lessons
        are read from, and is verified by reading the row back.
        """
        stage = self._stage(stage_id)
        statements = [
            f"delete from document_scene_revision where stage_id='{stage}'",
            f"delete from document_stage_revision where stage_id='{stage}'",
            f"delete from document_asset_refs where stage_id='{stage}'",
            f"delete from document_asset_withdrawals where stage_id='{stage}'",
            f"delete from legacy_classroom_imports where stage_id='{stage}'",
            f"delete from document_stages where id='{stage}'",
        ]
        self._query("begin; " + "; ".join(statements) + "; commit;")
        remaining = self._query(
            f"select count(*) from document_stages where id='{stage}'").strip()
        if remaining not in ("0", ""):
            raise LmsError(f"the classroom {stage} is still there after deleting it")
        return {"classroomId": stage, "deleted": True}

    def lessons(self, stage_id: str) -> list[dict]:
        """One entry per outline chapter, with that chapter's questions."""
        stage = self._stage(stage_id)
        outline_row = self._query(
            f"select data::text from document_outlines where stage_id='{stage}'").strip()
        try:
            outline = (json.loads(outline_row).get("outlines") or []) if outline_row else []
        except ValueError as err:
            raise LmsError(f"the classroom outline is not readable: {err}") from err
        scene_rows = self._query(
            "select data::text from document_scenes "
            f"where stage_id='{stage}' order by scene_order").splitlines()
        quizzes: dict[str, list[dict]] = {}
        for row in scene_rows:
            row = row.strip()
            if not row:
                continue
            try:
                scene = json.loads(row)
            except ValueError:
                continue
            questions = _questions(scene)
            if questions:
                quizzes[str(scene.get("outlineId") or "")] = questions
        lessons = []
        for index, item in enumerate(outline, 1):
            if not isinstance(item, dict):
                continue
            lessons.append({
                "id": str(item.get("id") or f"scene_{index}"),
                "title": str(item.get("title") or f"Lesson {index}"),
                "description": str(item.get("description") or ""),
                "key_points": [str(point) for point in (item.get("keyPoints") or [])],
                "questions": quizzes.get(str(item.get("id") or ""), []),
                "classroomId": stage,
            })
        return lessons


def _questions(scene: dict) -> list[dict]:
    """The graded questions in one quiz scene, normalized for OLX."""
    content = scene.get("content") if isinstance(scene, dict) else None
    if not isinstance(content, dict) or content.get("type") != "quiz":
        return []
    out = []
    for question in content.get("questions") or []:
        if not isinstance(question, dict):
            continue
        options = []
        for option in question.get("options") or []:
            if not isinstance(option, dict):
                continue
            value = str(option.get("value") or option.get("label") or "").strip()
            label = str(option.get("label") or value).strip()
            if value and label:
                options.append({"value": value, "label": label})
        answers = {str(answer) for answer in (question.get("answer") or [])}
        prompt = str(question.get("question") or "").strip()
        if len(options) < 2 or not answers or not prompt:
            continue
        for option in options:
            option["correct"] = option["value"] in answers
        if not any(option["correct"] for option in options):
            continue
        kind = "multiple" if str(question.get("type") or "single") == "multiple" else "single"
        out.append({
            "prompt": prompt,
            "kind": kind,
            "options": options,
            "solution": str(question.get("analysis") or ""),
        })
    return out


# -- the publisher ------------------------------------------------------------


class Publisher:
    """Program courses -> real LMS courses, and learners into them.

    The publisher owns no HTTP and no page: the console calls it, and so does the
    CLI. Its only state on disk is the generated OLX under `work_dir` and a record
    of what it published, so a second run is a no-op rather than a duplicate.
    """

    def __init__(self, root: str, work_dir: str | None = None, lms=None,
                 clock=time.time, org: str = DEFAULTS["ORG"], lessons=None):
        self.root = root
        self.work_dir = work_dir or os.path.join(root, "lms")
        self.lms = lms or DockerLms(work_dir=self.work_dir)
        self.clock = clock
        self.org = org
        #: Where the generated classroom's lessons are read from. A real
        #: publisher reads OpenMAIC through docker; tests pass a stand-in.
        self.lessons = lessons if lessons is not None else OpenmaicLessons()
        self._keys: dict[str, str] | None = None
        self._keys_at = 0.0
        #: Seconds between a failed reindex and its one retry.
        self.retry_delay = 5

    # -- programs -------------------------------------------------------

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
                continue  # one unreadable program is not a broken catalog
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
                # A course code is the course for a learner, but a run is the
                # cohort. A key from an earlier term is a different run; reusing
                # it would silently keep publishing into last year's cohort.
                if existing and not existing.endswith("+" + term):
                    existing = None
                out.append(entry_for(course, program, semester, term,
                                     key=existing, published=existing is not None))
        return out

    def plan(self, program_ids=None, codes=None) -> list[dict]:
        """Every selected course, once: two programs may share a course code.

        The LMS key is the course, not the program, so a code taught by two
        programs is one course — publishing it twice would import the same shell
        over itself. The first program's entry wins, which is also the one the
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
                "lessons": int(entry.get("lessonCount") or 0),
                "questions": int(entry.get("questionCount") or 0),
            }
        os.makedirs(self.work_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)

    def publish(self, program_ids=None, codes=None, execute: bool = False) -> dict:
        """Create the missing courses in the LMS and reindex the catalog."""
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
                # One bad course must not cost a program the other thirty-nine:
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
        if execute:
            # A card photograph is part of publishing, not a separate chore, and
            # it is re-applied to courses that already existed so a pool update
            # reaches the whole catalog the next time anything is published.
            try:
                answer["images"] = self.set_images(entries)
            except LmsError as err:
                answer["images"] = {"available": False, "error": str(err)}
            # A newly imported course has no card yet: render one per course
            # (Pillow, best effort) and upload it as the course's card asset, so
            # the catalog never shows the placeholder for a course the publisher
            # just created. No second reindex: the asset path is unchanged.
            if hasattr(self.lms, "apply_course_cards"):
                answer["render"] = self.render_cards(entries)
                try:
                    answer["cards"] = self.apply_cards(entries, reindex=False)
                except LmsError as err:
                    answer["cards"] = {"available": False, "error": str(err)}
        return answer

    # -- photographs ------------------------------------------------------

    def visible_courses(self) -> list[tuple[str, str]]:
        """Every course the catalog shows, as `(key, display name)`.

        A plan is what the publisher *creates*; the catalog shows what the LMS
        *holds*, and those are not the same set. `DATA101` runs under an older
        key than any current program produces, and it stays listed — with
        whatever picture it was published with, which after a redesign is the
        previous one. So the photographs are applied to the catalog, not to the
        plan.
        """
        lister = getattr(self.lms, "course_list", None)
        if lister is None:
            return []
        try:
            return list(lister())
        except LmsError:
            return []

    @staticmethod
    def _code_of(key: str) -> str:
        """`course-v1:ORG+CODE+RUN` -> `CODE`."""
        parts = str(key).split("+")
        return parts[1].strip().upper() if len(parts) == 3 else str(key)

    def _outside_plan(self, covered) -> dict[str, str]:
        """The photographs for courses no current plan names, key -> URL."""
        return {key: course_image_url(self._code_of(key), name)
                for key, name in self.visible_courses() if key not in covered}

    def set_images(self, entries=None) -> dict:
        """Give every course in the catalog its Unity-pool card photograph.

        Both images a learner can see — the card and the course page's banner —
        are written, and this covers courses no plan names, because those stay
        in the catalog after the plan that made them is replaced.
        """
        if entries is None:
            try:
                entries = self.plan()
            except LmsError as err:
                return {"available": False, "error": str(err)}
        mapping = {
            entry["key"]: course_image_url(entry["code"], entry["title"],
                                           entry.get("description") or "")
            for entry in entries
        }
        outside = self._outside_plan(mapping)
        mapping.update(outside)
        if not mapping:
            return {"available": True, "updated": [], "missing": []}
        try:
            report = self.lms.set_course_images(mapping)
        except LmsError as err:
            return {"available": False, "error": str(err), "planned": len(mapping)}
        return {"available": True, **report, "planned": len(mapping),
                "outsidePlan": len(outside)}

    # -- dates --------------------------------------------------------------

    def cohort_first_day(self) -> str | None:
        """The day the cohort's classes begin, as its programs state it."""
        days = [str(program.get("firstDay") or "").strip() for program in self.programs()]
        days = [day for day in days if day]
        return min(days) if days else None

    def set_dates(self, first_day=None) -> dict:
        """Put the cohort's first day on every course in the catalog.

        The marketing calendar says Spring 2027 begins on 11 January; a course
        that advertises the term's quarter start (1 January) contradicts the
        page a learner applied from. The date lives on the run, so it is written
        into every run the catalog holds — planned or not — and the index is
        rebuilt, because "Starts" is read out of the search index, not the
        database.
        """
        first_day = str(first_day or self.cohort_first_day() or "").strip()
        if not first_day:
            return {"available": False,
                    "error": "no cohort first day: set `firstDay` on a program or pass --first-day"}
        try:
            planned = {entry["key"]: entry for entry in self.plan()}
        except LmsError as err:
            return {"available": False, "error": str(err)}
        keys = list(planned)
        for key, _name in self.visible_courses():
            if key not in planned:
                keys.append(key)
        mapping = {}
        for key in keys:
            parts = str(key).split("+")
            term = parts[2] if len(parts) == 3 else ""
            entry = planned.get(key) or {}
            dates = _dates(term, entry.get("earlyStart"), first_day)
            mapping[key] = {"start": dates["start"],
                            "advertisedStart": dates["advertised_start"]}
        try:
            report = self.lms.set_course_dates(mapping)
        except LmsError as err:
            return {"available": False, "error": str(err), "planned": len(mapping)}
        answer = {"available": True, **report, "planned": len(mapping),
                  "firstDay": first_day, "reindexed": False}
        try:
            self.lms.reindex()
            answer["reindexed"] = True
        except LmsError as err:
            answer["reindexError"] = str(err)
        return answer

    def render_cards(self, entries=None) -> dict:
        """Render one catalog card per course, from the program plans.

        Runs `scripts/course-cards.py` with the interpreter running this script,
        because Pillow is a dependency of the renderer, not of publishing: a host
        without it still publishes and keeps the cards it already has. The
        renderer is idempotent — the same plans produce the same 100 JPEGs.
        """
        renderer = os.path.join(REPO, "scripts", "course-cards.py")
        out = photos_module().PHOTO_DIR
        command = [sys.executable, renderer, "--programs", self._programs_dir(),
                   "--out", out]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as err:
            return {"available": False, "error": str(err)}
        if result.returncode != 0:
            tail = ((result.stderr or "") + (result.stdout or "")).strip().splitlines()[-3:]
            return {"available": False, "error": " / ".join(tail) or "renderer failed"}
        wanted = {str(entry.get("code")).upper() for entry in (entries or [])}
        rendered = sorted(name for name in os.listdir(out)
                          if name.endswith(".jpg") and name[:-4] in wanted)
        return {"available": True, "rendered": rendered}

    def check_cards(self) -> dict:
        """Every published course's card asset must be served, not just named."""
        try:
            keys = self.lms.course_ids()
            report = self.lms.check_course_cards(keys)
        except LmsError as err:
            return {"available": False, "error": str(err)}
        return {"available": True, **report}

    def apply_cards(self, entries=None, reindex: bool = True) -> dict:
        """Put each course's card on its catalog card.

        Two records have to agree for a card to show: the course *asset* the
        search index links to, and the `CourseOverview` image the course-about
        page reads. This writes both, then reindexes so the catalog stops
        serving the URLs the shells were imported with.

        Cards are rendered by `scripts/course-cards.py`; a planned course
        uploads whatever it finds in the theme's `images/courses/<CODE>.jpg`.
        A course outside every plan — a standalone course, or a run from an
        earlier cohort — has no rendered card, so its subject photograph from
        the pool is uploaded instead: it is still in the catalog, so it still
        needs a picture that belongs to this design.
        """
        if entries is None:
            try:
                entries = self.plan()
            except LmsError as err:
                return {"available": False, "error": str(err)}
        photo_dir = photos_module().PHOTO_DIR
        # Everything the catalog can show, by key: the courses this run plans,
        # and the ones the LMS already holds that no plan names. `resolve()`
        # prefers a rendered card and falls back to the subject photograph, so
        # one pass gives every course a picture from this design.
        known = {entry["key"]: (str(entry.get("code") or "").upper(),
                               entry.get("title") or "")
                 for entry in entries}
        for key, name in self.visible_courses():
            known.setdefault(key, (self._code_of(key), name))
        plan, missing = {}, []
        for key, (code, title) in known.items():
            photo = photos_module().resolve(code, title)
            path = os.path.join(photo_dir, photo["file"])
            if os.path.isfile(path):
                plan[key] = path
            else:
                missing.append(code)
        if not plan:
            return {"available": True, "planned": 0, "uploaded": [], "missing": missing,
                    "failed": [], "reindexed": False}
        try:
            report = self.lms.apply_course_cards(plan)
        except LmsError as err:
            return {"available": False, "error": str(err), "planned": len(plan),
                    "uploaded": [], "missing": missing, "failed": []}
        images = self.set_images(entries)
        answer = {"available": True, "planned": len(plan), "uploaded": report.get("uploaded", []),
                  "failed": report.get("failed", []), "missing": missing, "images": images,
                  "reindexed": False}
        if reindex:
            try:
                self.lms.reindex()
                answer["reindexed"] = True
            except LmsError as err:
                answer["reindexError"] = str(err)
        return answer

    # -- deleting ---------------------------------------------------------

    def delete_all(self) -> dict:
        """Remove every course from the LMS, for a start from scratch.

        Deliberately not a filter: "delete all" has to mean all, or the course
        that was forgotten keeps its key and re-publishing it is a no-op.
        """
        try:
            report = self.lms.delete_all_courses()
        except LmsError as err:
            return {"available": False, "error": str(err), "deleted": [], "failed": []}
        if not report.get("available"):
            return report
        answer = {**report, "reindexed": False}
        if report.get("deleted"):
            try:
                self.lms.reindex()
                answer["reindexed"] = True
            except LmsError as err:
                answer["reindexError"] = str(err)
            self._forget(report["deleted"])
            self._keys = None
        return answer

    def delete_courses(self, codes=None, keys=None) -> dict:
        """Delete program courses from the LMS and refresh what the LMS holds.

        Only the courses named are removed: a course two programs teach is one
        course, and the caller has already decided it belongs to neither.
        """
        wanted = [str(key).strip() for key in (keys or []) if str(key).strip()]
        if codes is not None:
            try:
                index = self.published(refresh=True)
            except LmsError as err:
                return {"available": False, "error": str(err),
                        "deleted": [], "failed": []}
            for code in codes:
                key = index.get(str(code).strip().upper())
                if key and key not in wanted:
                    wanted.append(key)
        if not wanted:
            return {"available": True, "deleted": [], "failed": []}
        try:
            report = self.lms.delete_courses(wanted)
        except LmsError as err:
            return {"available": False, "error": str(err),
                    "deleted": [], "failed": []}
        answer = {"available": True, **report, "reindexed": False}
        if report["deleted"]:
            try:
                self.lms.reindex()
                answer["reindexed"] = True
            except LmsError as err:
                answer["reindexError"] = str(err)
            self._forget(report["deleted"])
            self._keys = None
        return answer

    def delete_classrooms(self, stages) -> dict:
        """Delete the classrooms that existed only for a deleted course or program.

        One classroom failing must not leave the rest behind, so each is deleted
        on its own and the answer names the ones that would not go.
        """
        wanted = [str(stage).strip() for stage in (stages or []) if str(stage).strip()]
        deleted, failed = [], []
        for stage in dict.fromkeys(wanted):
            try:
                self.lessons.delete(stage)
                deleted.append(stage)
            except LmsError as err:
                failed.append({"classroomId": stage, "error": str(err)[:300]})
        return {"deleted": deleted, "failed": failed}

    def _forget(self, keys) -> None:
        """Drop deleted courses from the publishing record."""
        path = os.path.join(self.work_dir, "published.json")
        try:
            with open(path, encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(record, dict):
            return
        for key in keys:
            record.pop(key, None)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(record, fh, indent=2, sort_keys=True)
        except OSError:
            pass

    # -- lessons ----------------------------------------------------------

    def attach(self, program_id: str, code: str, classroom_id: str | None = None) -> dict:
        """Write a generated classroom's lessons into its course, then reimport it.

        The shell is rebuilt from the program plan plus the classroom's own
        outline and quizzes, so the course in the LMS gains one chapter per
        lesson and a graded final examination — the same course key, the same
        enrollment, and stable component ids so no learner's grade is orphaned.
        """
        try:
            program = self.program(program_id)
        except KeyError:
            return {"available": False, "attached": False,
                    "error": f"no program {program_id!r}"}
        try:
            entries = self.entries(program, self.published(refresh=True), [code])
        except LmsError as err:
            return {"available": False, "attached": False, "error": str(err)}
        entry = entries[0] if entries else None
        if entry is None:
            return {"available": True, "attached": False,
                    "error": f"no course {code!r} in {program_id}"}
        stage = str(classroom_id or entry.get("classroomId") or "").strip()
        if not stage:
            return {"available": True, "attached": False,
                    "error": f"{code} has no generated classroom yet"}
        if not entry["published"]:
            return {"available": True, "attached": False,
                    "error": f"{code} is not in the LMS yet — publish it first"}
        try:
            lessons = self.lessons.lessons(stage)
        except LmsError as err:
            return {"available": False, "attached": False, "error": str(err)}
        entry.update({
            "classroomId": stage,
            "lessons": lessons,
            "lessonCount": len(lessons),
            "questionCount": sum(len(lesson.get("questions") or []) for lesson in lessons),
        })
        dest = os.path.join(self.work_dir, "shells", entry["slug"])
        try:
            olx = build_shell(entry, dest)
            self.lms.import_olx(olx, entry["slug"])
        except (OSError, ValueError, LmsError) as err:
            return {"available": True, "attached": False, "key": entry["key"],
                    "error": str(err)}
        answer = {
            "available": True,
            "attached": True,
            "key": entry["key"],
            "code": entry["code"],
            "classroomId": stage,
            "lessons": len(lessons),
            "questions": entry["questionCount"],
            "graded": bool(entry["questionCount"]),
            "olx": olx,
        }
        for attempt in range(2):
            try:
                self.lms.reindex()
                answer["reindexed"] = True
                break
            except LmsError as err:
                answer["reindexed"] = False
                answer["reindexError"] = str(err)
                if attempt == 0 and self.retry_delay:
                    time.sleep(self.retry_delay)
        self._record([entry])
        self._keys = None
        return answer

    def grades(self, program_id: str, students=None) -> dict:
        """Every learner on a program, against every course of it, graded by the LMS."""
        try:
            program = self.program(program_id)
            entries = self.entries(program, self.published(refresh=True))
        except KeyError:
            return {"available": False, "error": f"no program {program_id!r}", "rows": []}
        except LmsError as err:
            return {"available": False, "error": str(err), "rows": []}
        learners = [str(s).strip()
                    for s in (students if students is not None
                              else list((program.get("enrollments") or {}).keys()))
                    if str(s).strip()]
        keys = [entry["key"] for entry in entries]
        if not learners or not keys:
            return {"available": True, "students": learners,
                    "courses": len(keys), "rows": []}
        try:
            report = self.lms.grades(learners, keys)
        except LmsError as err:
            return {"available": False, "error": str(err), "rows": []}
        rows = []
        for student in report.get("students") or []:
            if student.get("missing"):
                continue
            for row in student.get("courses") or []:
                rows.append({"student": student["student"],
                             "course": str(row.get("course") or "").split("+")[1].upper(),
                             "key": row.get("course"),
                             "percent": row.get("percent"),
                             "passed": bool(row.get("passed")),
                             "letter": row.get("letter") or "",
                             "error": row.get("error") or ""})
        return {"available": True, "students": learners,
                "courses": len(keys), "rows": rows}

    # -- enroll ------------------------------------------------------------

    def enroll(self, program_id: str, student: str) -> dict:
        """Put one learner into every course of a program, in the LMS."""
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
        """How much of this program is real in the LMS, for the console page."""
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
    ap.add_argument("--attach", metavar="PROGRAM",
                    help="write a generated classroom's lessons into one of the program's courses")
    ap.add_argument("--classroom", help="the classroom id to attach (default: the one on the plan)")
    ap.add_argument("--grades", action="store_true",
                    help="read each enrolled learner's course grades from the LMS")
    ap.add_argument("--enroll", help="a learner identity to enroll in the selected programs")
    ap.add_argument("--delete", action="store_true",
                    help="delete the selected programs' (or --course) courses from the LMS")
    ap.add_argument("--delete-all", action="store_true",
                    help="delete every course in the LMS, then reindex (a start from scratch)")
    ap.add_argument("--images", action="store_true",
                    help="(re)apply the course photographs to every course in the catalog")
    ap.add_argument("--cards", action="store_true",
                    help="upload each course's rendered card (scripts/course-cards.py) as its catalog card")
    ap.add_argument("--dates", action="store_true",
                    help="write the cohort's first day onto every course in the catalog, then reindex")
    ap.add_argument("--first-day", metavar="YYYY-MM-DD",
                    help="the cohort's first day (default: the earliest `firstDay` on a program)")
    ap.add_argument("--check-cards", action="store_true",
                    help="fail if any published course's card asset is not served")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    publisher = Publisher(args.root, work_dir=args.work_dir)

    if args.delete_all:
        answer = publisher.delete_all()
        if args.json:
            print(json.dumps(answer, indent=2, sort_keys=True))
            sys.exit(1 if answer.get("failed") or not answer.get("available") else 0)
        if not answer.get("available"):
            print(f"error: the LMS is not reachable: {answer.get('error')}", file=sys.stderr)
            sys.exit(1)
        for failure in answer["failed"]:
            print(f"  {failure['key']:<52} FAILED: {failure['error']}", file=sys.stderr)
        print(f"{len(answer['deleted'])} course(s) deleted from the LMS"
              + (" and the catalog reindexed" if answer.get("reindexed") else ""))
        sys.exit(1 if answer["failed"] else 0)

    if args.check_cards:
        answer = publisher.check_cards()
        if args.json:
            print(json.dumps(answer, indent=2, sort_keys=True))
            sys.exit(0 if answer.get("available") and not answer.get("bad") else 1)
        if not answer.get("available"):
            print(f"error: {answer.get('error')}", file=sys.stderr)
            sys.exit(1)
        bad = answer.get("bad") or []
        print(f"course cards: {answer.get('checked', 0) - len(bad)} of "
              f"{answer.get('checked', 0)} served")
        for row in bad:
            print(f"  {row.get('key'):<52} {row.get('status') or row.get('error')} "
                  f"{row.get('bytes') or ''}", file=sys.stderr)
        sys.exit(1 if bad else 0)

    if args.cards:
        answer = publisher.apply_cards()
        if args.json:
            print(json.dumps(answer, indent=2, sort_keys=True))
            sys.exit(0 if answer.get("available") and not answer.get("failed") else 1)
        if not answer.get("available"):
            print(f"error: {answer.get('error')}", file=sys.stderr)
            sys.exit(1)
        print(f"course cards: {len(answer.get('uploaded') or [])} of "
              f"{answer.get('planned') or 0} course(s) uploaded"
              + (" and the catalog reindexed" if answer.get("reindexed") else ""))
        for failure in answer.get("failed") or []:
            print(f"  {failure['key']:<52} FAILED: {failure['error']}", file=sys.stderr)
        if answer.get("missing"):
            print("  no rendered card for: " + ", ".join(answer["missing"]), file=sys.stderr)
        sys.exit(1 if answer.get("failed") else 0)

    if args.dates:
        answer = publisher.set_dates(args.first_day)
        if args.json:
            print(json.dumps(answer, indent=2, sort_keys=True))
            sys.exit(0 if answer.get("available") else 1)
        if not answer.get("available"):
            print(f"error: {answer.get('error')}", file=sys.stderr)
            sys.exit(1)
        print(f"cohort start: {answer.get('firstDay')} on "
              f"{len(answer.get('updated') or [])} of {answer.get('planned') or 0} course(s)"
              + (" and the catalog reindexed" if answer.get("reindexed") else ""))
        for key in answer.get("missing") or []:
            print(f"  {key:<52} not in the CMS", file=sys.stderr)
        sys.exit(0)

    if args.images:
        answer = publisher.set_images()
        if args.json:
            print(json.dumps(answer, indent=2, sort_keys=True))
            sys.exit(0 if answer.get("available") else 1)
        if not answer.get("available"):
            print(f"error: {answer.get('error')}", file=sys.stderr)
            sys.exit(1)
        print(f"course photographs: {len(answer.get('updated') or [])} of "
              f"{answer.get('planned') or 0} course(s) updated")
        for key in answer.get("missing") or []:
            print(f"  {key:<52} not in the CMS", file=sys.stderr)
        sys.exit(0)
    if args.attach:
        if not args.course or len(args.course) != 1:
            raise SystemExit("--attach needs exactly one --course")
        answer = publisher.attach(args.attach, args.course[0], args.classroom)
        if args.json:
            print(json.dumps(answer, indent=2, sort_keys=True))
        elif not answer.get("attached"):
            print(f"error: {answer.get('error')}", file=sys.stderr)
        else:
            print(f"{answer['key']}: {answer['lessons']} lesson(s), "
                  f"{answer['questions']} graded question(s)")
        sys.exit(0 if answer.get("attached") else 1)

    if args.grades:
        if not args.program:
            raise SystemExit("--grades needs --program (one or more)")
        reports = [publisher.grades(program_id) for program_id in args.program]
        if args.json:
            print(json.dumps(reports, indent=2, sort_keys=True))
        else:
            for report in reports:
                if not report.get("available"):
                    print(f"error: {report.get('error')}", file=sys.stderr)
                    continue
                for row in report.get("rows") or []:
                    mark = "—" if row["percent"] is None else f"{row['percent']:.0f}%"
                    print(f"  {row['student']:<32} {row['course']:<10} {mark:>6} "
                          f"{'passed' if row['passed'] else 'not passed'}"
                          + (f"  ({row['error']})" if row.get("error") else ""))
        sys.exit(0 if all(report.get("available") for report in reports) else 1)

    if args.delete:
        codes = list(args.course or [])
        if args.program:
            for program_id in args.program:
                try:
                    doc = publisher.program(program_id)
                except KeyError:
                    raise SystemExit(f"no program {program_id!r}") from None
                codes += [course["code"] for semester in doc.get("semesters") or []
                          for course in semester.get("courses") or []]
        if not codes:
            raise SystemExit("--delete needs --program or --course")
        answer = publisher.delete_courses(codes=codes)
        if args.json:
            print(json.dumps(answer, indent=2, sort_keys=True))
            sys.exit(1 if answer.get("failed") or not answer.get("available") else 0)
        if not answer.get("available"):
            print(f"error: the LMS is not reachable: {answer['error']}", file=sys.stderr)
            sys.exit(1)
        for key in answer["deleted"]:
            print(f"  {key:<52} deleted")
        for failure in answer["failed"]:
            print(f"  {failure['key']:<52} FAILED: {failure['error']}", file=sys.stderr)
        print(f"{len(answer['deleted'])} course(s) deleted from the LMS")
        sys.exit(1 if answer["failed"] else 0)

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
    return "\n".join(lines) or "nothing to enroll"


if __name__ == "__main__":
    main()
