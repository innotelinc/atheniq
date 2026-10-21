#!/usr/bin/env python3
"""AthenIQ — program management.

A *program* is the whole credential: an ordered set of semesters, each course
carrying credits, prerequisites, and a final assessment, ending in a degree or
certificate that is conferred only when every requirement is satisfied.

This module is the working half of that sentence. It:

    * stores programs as JSON under `programs/`, one file each;
    * builds them from a catalogue template (criminal-justice,
      business-administration, nursing) or from an explicit course list;
    * validates the prerequisite graph — a prerequisite taught in the same term
      as the course that needs it is a scheduling error, not a prerequisite;
    * plans and records OpenMAIC generation, one brief per course, semester by
      semester, because a program is 20-30 classrooms and nobody should click
      that many buttons;
    * tracks a learner: grades, final examinations, credited hours, GPA,
      stackable certificates, and degree conferral.

The store never talks to OpenMAIC itself. The console passes in a `submit`
callable and a `run_status` callable, so this module stays testable without a
gateway and the console keeps its single OpenMAIC client.

Stdlib only, like every other script in this tree.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(HERE, "program-catalog.py")


def _load_catalog():
    """The catalogue, imported by path (the filename has a hyphen).

    The module is registered in `sys.modules` before it executes: dataclasses
    resolve their annotations through their own module entry, and an unregistered
    module makes that lookup fail on newer Python versions.
    """
    name = "atheniq_program_catalog"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, CATALOG_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


class ProgramError(Exception):
    """A request the caller can fix: `status` is the answer's status code."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


#: Credit-weighted grade points, on the usual 4.0 scale.
GRADE_POINTS = (
    (93, 4.0), (90, 3.7), (87, 3.3), (83, 3.0), (80, 2.7),
    (77, 2.3), (73, 2.0), (70, 1.7), (67, 1.3), (63, 1.0), (60, 0.7),
)

#: A course is passed at 60; nursing's clinical courses require 75.
PASS_MARK = 60.0
CLINICAL_PASS_MARK = 75.0


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return cleaned[:48] or "program"


def _now_iso(clock) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))


def _classroom_count(value) -> int:
    """How many classrooms a course generates: 1-10, defaulting to 4."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 4
    return max(1, min(10, count))


def grade_points(score: float) -> float:
    """Grade points for a 0-100 score."""
    for floor, points in GRADE_POINTS:
        if score >= floor:
            return points
    return 0.0


def course_pass_mark(course: dict) -> float:
    """What counts as a pass for this course."""
    return CLINICAL_PASS_MARK if course.get("kind") == "clinical" else PASS_MARK


class ProgramStore:
    """Programs on disk, and the rules that make them real credentials."""

    def __init__(self, root: str, clock=time.time):
        self.root = root
        self.clock = clock
        self.catalog = _load_catalog()
        self._lock = threading.Lock()

    # -- storage ---------------------------------------------------------

    def _dir(self) -> str:
        return self.root

    def _path(self, program_id: str) -> str:
        safe = _slug(program_id)
        return os.path.join(self._dir(), f"{safe}.json")

    def _read(self, program_id: str) -> dict:
        path = self._path(program_id)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except FileNotFoundError:
            raise ProgramError(404, f"no program {program_id!r}") from None
        except (OSError, ValueError) as err:
            raise ProgramError(500, f"program {program_id!r} is unreadable: {err}") from err
        if not isinstance(doc, dict):
            raise ProgramError(500, f"program {program_id!r} is not an object")
        doc.setdefault("id", os.path.splitext(os.path.basename(path))[0])
        return doc

    def _write(self, doc: dict) -> None:
        """Persist one program, turning a disk failure into an answer.

        A store the service user cannot write is a deployment problem, but it
        must not reach the socket as an unhandled exception: the browser then
        sees an empty reply instead of the reason. Raised as `ProgramError` so
        the console answers 500 with a message.
        """
        path = self._path(doc["id"])
        tmp = f"{path}.{os.getpid()}.tmp"
        try:
            os.makedirs(self._dir(), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, path)
        except OSError as err:
            raise ProgramError(500, f"cannot write the program store at {self._dir()}: "
                                    f"{err}") from err

    def template_summaries(self) -> list[dict]:
        return self.catalog.list_templates()

    def list_programs(self) -> list[dict]:
        """Every stored program, newest first, as a summary."""
        out = []
        try:
            names = os.listdir(self._dir())
        except OSError:
            return out
        for name in sorted(names):
            if not name.endswith(".json") or name.endswith(".tmp"):
                continue
            program_id = name[: -len(".json")]
            try:
                doc = self._read(program_id)
            except ProgramError:
                continue
            out.append(self._summary(doc))
        out.sort(key=lambda item: item.get("createdAt") or "", reverse=True)
        return out

    @staticmethod
    def _summary(doc: dict) -> dict:
        semesters = doc.get("semesters") or []
        courses = [course for semester in semesters for course in semester.get("courses", [])]
        generated = sum(1 for course in courses if course.get("classroomIds"))
        built = sum(1 for course in courses
                    if (course.get("lessons") or {}).get("count"))
        enrolled = len(doc.get("enrollments") or {})
        return {
            "id": doc.get("id"),
            "template": doc.get("template"),
            "name": doc.get("name"),
            "credential": doc.get("credential"),
            "credentialKind": doc.get("credentialKind"),
            "level": doc.get("level"),
            "totalCredits": doc.get("totalCredits"),
            "semesters": len(semesters),
            "courses": len(courses),
            "generated": generated,
            "built": built,
            "enrolled": enrolled,
            "createdAt": doc.get("createdAt"),
            "createdBy": doc.get("createdBy"),
        }

    # -- creation --------------------------------------------------------

    def create(self, identity, body: dict) -> dict:
        """Create a program from a template, or from an explicit course list.

        Body:
            template      a catalogue slug (criminal-justice, ...)
            name          override the program name
            credential    override the credential name
            startTerm     informational label, e.g. "Fall 2026"
            semesters     when there is no template: a list of
                          {name, courses:[{code,title,credits,prerequisites,
                          finalExam,kind,classrooms,description}]}
        """
        if not isinstance(body, dict):
            raise ProgramError(400, "expected a JSON object")
        template_slug = str(body.get("template") or "").strip()
        if template_slug:
            try:
                template = self.catalog.get_template(template_slug)
            except KeyError as err:
                raise ProgramError(400, str(err)) from None
            doc = self._from_template(template, body)
        else:
            doc = self._from_body(body)
        problems = self.validate(doc)
        if problems:
            raise ProgramError(400, "the program is not schedulable: " + "; ".join(problems))
        doc["id"] = f"{_slug(doc['name'])}-{secrets.token_hex(3)}"
        doc["createdAt"] = _now_iso(self.clock)
        doc["createdBy"] = getattr(identity, "user", "") or getattr(identity, "email", "") or ""
        doc.setdefault("enrollments", {})
        with self._lock:
            self._write(doc)
        return self.get(doc["id"])

    def _from_template(self, template, body: dict) -> dict:
        doc = template.as_dict()
        doc["template"] = template.slug
        if body.get("name"):
            doc["name"] = str(body["name"]).strip()
        if body.get("credential"):
            doc["credential"] = str(body["credential"]).strip()
        doc["startTerm"] = str(body.get("startTerm") or "").strip() or None
        for semester in doc["semesters"]:
            for course in semester["courses"]:
                course["classroomIds"] = []
                course["runIds"] = []
                course["status"] = "planned"
        return doc

    def _from_body(self, body: dict) -> dict:
        semesters_in = body.get("semesters")
        if not isinstance(semesters_in, list) or not semesters_in:
            raise ProgramError(400, "a custom program needs a non-empty `semesters` list")
        name = str(body.get("name") or "").strip()
        if not name:
            raise ProgramError(400, "a program needs a name")
        semesters = []
        seen: set[str] = set()
        for number, semester in enumerate(semesters_in, start=1):
            if not isinstance(semester, dict):
                raise ProgramError(400, f"semester {number} must be an object")
            courses = []
            for raw in semester.get("courses") or []:
                if not isinstance(raw, dict):
                    raise ProgramError(400, f"semester {number} has a course that is not an object")
                code = str(raw.get("code") or "").strip().upper()
                if not code:
                    raise ProgramError(400, f"semester {number} has a course with no code")
                if code in seen:
                    raise ProgramError(400, f"course {code} appears twice")
                seen.add(code)
                credits = raw.get("credits", 3)
                try:
                    credits = int(credits)
                except (TypeError, ValueError):
                    raise ProgramError(400, f"{code}: credits must be a whole number") from None
                if credits < 1 or credits > 12:
                    raise ProgramError(400, f"{code}: credits must be between 1 and 12")
                prereq = raw.get("prerequisites") or []
                if isinstance(prereq, str):
                    prereq = [prereq]
                courses.append({
                    "code": code,
                    "title": str(raw.get("title") or code).strip(),
                    "credits": credits,
                    "description": str(raw.get("description") or "").strip(),
                    "prerequisites": [str(p).strip().upper() for p in prereq],
                    "finalExam": str(raw.get("finalExam") or "comprehensive").strip(),
                    "kind": str(raw.get("kind") or "core").strip(),
                    "classrooms": _classroom_count(raw.get("classrooms")),
                    "classroomIds": [],
                    "runIds": [],
                    "status": "planned",
                })
            if not courses:
                raise ProgramError(400, f"semester {number} has no courses")
            semesters.append({
                "number": number,
                "name": str(semester.get("name") or f"Semester {number}").strip(),
                "credits": sum(c["credits"] for c in courses),
                "courses": courses,
            })
        total = sum(s["credits"] for s in semesters)
        return {
            "template": None,
            "name": name,
            "credential": str(body.get("credential") or name).strip(),
            "credentialKind": str(body.get("credentialKind") or "degree").strip(),
            "level": str(body.get("level") or "custom").strip(),
            "totalCredits": int(body.get("totalCredits") or total),
            "minGpa": float(body.get("minGpa") or 2.0),
            "capstone": str(body.get("capstone") or "").strip(),
            "description": str(body.get("description") or "").strip(),
            "startTerm": str(body.get("startTerm") or "").strip() or None,
            "semesters": semesters,
            "certificates": body.get("certificates") or [],
        }

    # -- the graph -------------------------------------------------------

    @staticmethod
    def _course_map(doc: dict) -> dict[str, dict]:
        return {course["code"]: course for semester in doc.get("semesters", [])
                for course in semester.get("courses", [])}

    @staticmethod
    def _semester_of(doc: dict, code: str) -> int:
        for semester in doc.get("semesters", []):
            if any(course["code"] == code for course in semester.get("courses", [])):
                return semester["number"]
        return 0

    def validate(self, doc: dict) -> list[str]:
        """Every problem that would make the plan impossible to walk."""
        problems: list[str] = []
        courses = self._course_map(doc)
        if not courses:
            return ["the program has no courses"]
        for semester in doc.get("semesters", []):
            for course in semester.get("courses", []):
                if not course.get("credits", 0) > 0:
                    problems.append(f"{course['code']} has no credits")
                for prereq in course.get("prerequisites") or []:
                    if prereq not in courses:
                        problems.append(f"{course['code']} needs {prereq}, which is not in the program")
                    elif self._semester_of(doc, prereq) >= semester["number"]:
                        problems.append(
                            f"{course['code']} (semester {semester['number']}) needs "
                            f"{prereq}, taught in semester {self._semester_of(doc, prereq)}")
        declared = int(doc.get("totalCredits") or 0)
        actual = sum(course.get("credits", 0) for course in courses.values())
        if declared and actual != declared:
            problems.append(f"totalCredits says {declared} but the courses add up to {actual}")
        if doc.get("level") == "associate" and declared and declared > 90:
            problems.append("an associate credential cannot require more than 90 credits")
        if doc.get("level") == "bachelor" and declared and declared < 120:
            problems.append("a bachelor's credential requires at least 120 credits")
        return problems

    # -- reading ---------------------------------------------------------

    def get(self, program_id: str) -> dict:
        doc = self._read(program_id)
        return {**doc, "plan": self.plan(doc)}

    def plan(self, doc_or_id) -> dict:
        """The semester plan with prerequisite links and final assessments."""
        doc = self._read(doc_or_id) if isinstance(doc_or_id, str) else doc_or_id
        courses = self._course_map(doc)
        semesters = []
        for semester in doc.get("semesters", []):
            rows = []
            for course in semester.get("courses", []):
                rows.append({
                    **course,
                    "prerequisites": list(course.get("prerequisites") or []),
                    "unlocks": sorted(
                        other["code"] for other in courses.values()
                        if course["code"] in (other.get("prerequisites") or [])),
                    "final": final_exam_blueprint(course),
                })
            semesters.append({
                "number": semester["number"],
                "name": semester["name"],
                "credits": semester.get("credits") or sum(r["credits"] for r in rows),
                "courses": rows,
            })
        return {
            "semesters": semesters,
            "totalCredits": doc.get("totalCredits"),
            "earnedCredits": sum(s["credits"] for s in semesters),
            "capstone": doc.get("capstone"),
            "finals": [{"code": row["code"], "title": row["title"],
                        "type": row["final"]["type"], "weight": row["final"]["weight"]}
                       for semester in semesters for row in semester["courses"]],
        }

    # -- generation ------------------------------------------------------

    def brief_for(self, doc: dict, course: dict, semester: dict) -> str:
        """The OpenMAIC brief for one course: what it teaches, who it is for,
        and how it ends."""
        parts = [
            f"{course['title']} ({course['code']}) is a {course['credits']}-credit "
            f"{course.get('kind', 'core')} course in semester {semester['number']} of the "
            f"{doc['credential']} program at AthenIQ.",
        ]
        if course.get("description"):
            parts.append(course["description"])
        if course.get("prerequisites"):
            parts.append("Students have already completed: "
                         + ", ".join(course["prerequisites"]) + ".")
        parts.append(
            "The classroom should be taught as a sequence of "
            f"{course.get('classrooms', 4)} chapter-sized sessions, each ending in "
            "a check for understanding aligned to the course's graded work.")
        blueprint = final_exam_blueprint(course)
        parts.append(
            f"Final assessment: {blueprint['label']}. {blueprint['guidance']}")
        parts.append("Language: en")
        return "\n\n".join(parts)

    def generate_plan(self, doc: dict, semester: int | None = None,
                      codes: list[str] | None = None) -> list[dict]:
        """The ordered courses a generation run would submit, filtered.

        Ordering is semester by semester, then by code, so a run started from a
        phone produces the foundation before the course that depends on it.
        """
        wanted = {str(code).strip().upper() for code in (codes or []) if str(code).strip()}
        out = []
        for term in doc.get("semesters", []):
            if semester and term["number"] != semester:
                continue
            for course in term.get("courses", []):
                if wanted and course["code"] not in wanted:
                    continue
                out.append({"semester": term["number"], "semesterName": term["name"],
                            "course": course, "brief": self.brief_for(doc, course, term)})
        return out

    def generate(self, program_id: str, body: dict, submit) -> dict:
        """Submit one OpenMAIC run per course, semester by semester.

        `submit` is the console's own submit callable: `(requirement) -> run id`.
        A course that already has a run is skipped, and a limit hit stops the
        batch cleanly and names what it did not start — the same contract the
        console uses for `generate-missing`.
        """
        doc = self._read(program_id)
        semester = body.get("semester")
        try:
            semester = int(semester) if semester else None
        except (TypeError, ValueError):
            raise ProgramError(400, "semester must be a whole number") from None
        codes = body.get("courses")
        if codes is not None and not isinstance(codes, list):
            raise ProgramError(400, "courses must be a list of course codes")
        queue = self.generate_plan(doc, semester, codes)
        if not queue:
            raise ProgramError(404, "no courses match that semester or course list")

        started, skipped = [], []
        blocked = ""
        for item in queue:
            course = item["course"]
            if course.get("runIds"):
                skipped.append({"code": course["code"], "reason": "already generating"})
                continue
            if blocked:
                skipped.append({"code": course["code"], "reason": blocked})
                continue
            try:
                run_id = submit(item["brief"])
            except Exception as err:  # noqa: BLE001 — the console turns these into 429/502
                blocked = str(err)
                skipped.append({"code": course["code"], "reason": blocked})
                continue
            course.setdefault("runIds", []).append(run_id)
            course["status"] = "generating"
            started.append({"code": course["code"], "title": course["title"],
                            "semester": item["semester"], "runId": run_id})

        with self._lock:
            self._write(doc)
        return {"program": doc["id"], "started": started, "skipped": skipped,
                "queued": len(queue), "blocked": blocked,
                "next": "runs are recorded into the plan as they finish"}

    def sync(self, program_id: str, run_status, record=None) -> dict:
        """Record finished runs into the plan, and return what changed.

        `run_status(run_id)` returns `{"state", "classroomId"}`. A completed run
        is written into its course's `classroomIds`; when `record` is supplied it
        is called with the course entry so a caller can attach the classroom to a
        spec as well. Idempotent: a run already recorded is skipped.
        """
        doc = self._read(program_id)
        changed = []
        for semester in doc.get("semesters", []):
            for course in semester.get("courses", []):
                pending = [run for run in course.get("runIds", []) if run]
                if not pending:
                    continue
                done = []
                for run_id in pending:
                    try:
                        status = run_status(run_id) or {}
                    except Exception:  # noqa: BLE001 — a dead gateway is not a plan change
                        done.append(run_id)
                        continue
                    stage = status.get("classroomId")
                    if status.get("state") == "completed" and stage:
                        if stage not in course.setdefault("classroomIds", []):
                            course["classroomIds"].append(stage)
                        if record:
                            try:
                                record(course, stage)
                            except Exception:  # noqa: BLE001 — recording is best effort here
                                pass
                        done.append(run_id)
                        changed.append({"code": course["code"], "classroomId": stage})
                for run_id in done:
                    if run_id in course.get("runIds", []):
                        course["runIds"].remove(run_id)
                course["status"] = ("generated" if len(course.get("classroomIds") or [])
                                    >= course.get("classrooms", 1) else "generating")
        if changed:
            with self._lock:
                self._write(doc)
        return {"program": doc["id"], "recorded": changed,
                "summary": self._summary(doc)}

    def set_lessons(self, program_id: str, code: str, summary: dict) -> dict:
        """Record what one course's generated classroom put into the LMS.

        The counts are what the page reports ("4 lessons · 6 graded questions");
        they live in the plan so a course that has been built is distinguishable
        from one that is only promised, without asking the LMS on every render.
        """
        code = str(code or "").strip().upper()
        doc = self._read(program_id)
        course = self._course_map(doc).get(code)
        if course is None:
            raise ProgramError(404, f"no course {code!r} in {doc['name']}")
        course["lessons"] = {
            "count": int(summary.get("lessons") or 0),
            "questions": int(summary.get("questions") or 0),
            "classroomId": summary.get("classroomId") or None,
            "at": _now_iso(self.clock),
        }
        if summary.get("classroomId") and summary["classroomId"] not in (course.get("classroomIds") or []):
            course.setdefault("classroomIds", []).append(summary["classroomId"])
        with self._lock:
            self._write(doc)
        return {"program": doc["id"], "course": code, "lessons": course["lessons"]}

    # -- learners --------------------------------------------------------

    def update(self, program_id: str, body: dict) -> dict:
        """Change the editable parts of a program, keeping the plan intact.

        Name, credential, term and minimum GPA are metadata; the semesters are
        the curriculum and changing them here would invalidate every grade
        recorded against a code. A rename must not do that.
        """
        doc = self._read(program_id)
        if body.get("name"):
            doc["name"] = str(body["name"]).strip()[:120]
        if body.get("credential"):
            doc["credential"] = str(body["credential"]).strip()[:160]
        if "startTerm" in body:
            doc["startTerm"] = str(body.get("startTerm") or "").strip() or None
        if body.get("minGpa") is not None:
            try:
                doc["minGpa"] = round(float(body["minGpa"]), 2)
            except (TypeError, ValueError):
                raise ProgramError(400, "minGpa must be a number") from None
            if not 0 <= doc["minGpa"] <= 4:
                raise ProgramError(400, "minGpa must be between 0 and 4")
        problems = self.validate(doc)
        if problems:
            raise ProgramError(400, "the program is not schedulable: " + "; ".join(problems))
        with self._lock:
            self._write(doc)
        return self.get(doc["id"])

    def archive(self, program_id: str) -> dict:
        """Retire a program without losing it: move its file to `.archive/`.

        A hard delete would take the only record of a credential somebody may
        have been awarded; an archive keeps the file (and the conferrals beside
        it) while removing the program from the catalogue.
        """
        doc = self._read(program_id)
        source = self._path(program_id)
        target_dir = os.path.join(self._dir(), ".archive")
        try:
            os.makedirs(target_dir, exist_ok=True)
            target = os.path.join(
                target_dir, f"{doc['id']}.{time.strftime('%Y%m%dT%H%M%S', time.gmtime(self.clock()))}.json")
            os.replace(source, target)
        except OSError as err:
            raise ProgramError(500, f"cannot archive {program_id!r}: {err}") from err
        return {"ok": True, "program": doc["id"], "archived": target}

    def reset_courses(self, program_id: str, codes: list[str] | None = None) -> dict:
        """Forget generated classrooms so they can be generated again.

        Only the generation bookkeeping is cleared: grades, enrolments and the
        curriculum stay. Retiring a classroom must not retire a learner's work.
        """
        doc = self._read(program_id)
        wanted = {str(code).strip().upper() for code in (codes or []) if str(code).strip()}
        cleared = []
        for semester in doc.get("semesters", []):
            for course in semester.get("courses", []):
                if wanted and course["code"] not in wanted:
                    continue
                if course.get("classroomIds") or course.get("runIds"):
                    cleared.append(course["code"])
                course["classroomIds"] = []
                course["runIds"] = []
                course["status"] = "planned"
        if not cleared and wanted:
            raise ProgramError(404, "no matching course had generated classrooms")
        with self._lock:
            self._write(doc)
        return {"ok": True, "program": doc["id"], "cleared": cleared}

    def enroll(self, program_id: str, student: str) -> dict:
        student = str(student or "").strip()
        if not student:
            raise ProgramError(400, "a learner needs an identity (email or username)")
        doc = self._read(program_id)
        enrollments = doc.setdefault("enrollments", {})
        record = enrollments.get(student)
        if record is None:
            record = {"enrolledAt": _now_iso(self.clock), "grades": {},
                      "finals": {}, "certificates": [], "conferred": None}
            enrollments[student] = record
            with self._lock:
                self._write(doc)
        return {"program": doc["id"], "student": student,
                "progress": self.progress(doc, student)}

    def record_completion(self, program_id: str, student: str, code: str,
                          score: float, final_passed: bool | None = None,
                          source: str = "office") -> dict:
        """Record a grade, and (for examined courses) the final's outcome.

        A course counts as complete only when the score passes *and* the final
        assessment was passed. Recording a failing score un-completes it, so a
        correction is a correction rather than a second version of history.

        `source` says where the mark came from: `lms` when it was read out of the
        course's graded examination, `office` when a person recorded it. The
        progress view reports it so a number is never shown without its origin.
        """
        student = str(student or "").strip()
        code = str(code or "").strip().upper()
        if not student:
            raise ProgramError(400, "a learner needs an identity")
        doc = self._read(program_id)
        courses = self._course_map(doc)
        course = courses.get(code)
        if course is None:
            raise ProgramError(404, f"no course {code!r} in {doc['name']}")
        try:
            score = float(score)
        except (TypeError, ValueError):
            raise ProgramError(400, "score must be a number from 0 to 100") from None
        if not 0 <= score <= 100:
            raise ProgramError(400, "score must be between 0 and 100")
        prereq_missing = [p for p in (course.get("prerequisites") or [])
                         if not self._passed(doc, courses, student, p)]
        if prereq_missing and score >= course_pass_mark(course):
            raise ProgramError(
                409, f"{code} cannot be completed before "
                     f"{', '.join(prereq_missing)}")

        record = doc.setdefault("enrollments", {}).setdefault(
            student, {"enrolledAt": _now_iso(self.clock), "grades": {},
                      "finals": {}, "certificates": [], "conferred": None})
        record.setdefault("grades", {})[code] = round(score, 2)
        record.setdefault("gradeSources", {})[code] = str(source or "office")
        needs_final = course.get("finalExam") not in (None, "", "none")
        if needs_final:
            record.setdefault("finals", {})[code] = bool(
                final_passed if final_passed is not None else score >= course_pass_mark(course))
        # A fail revokes a certificate that depended on the course, because the
        # certificate is a statement about completion, not a participation badge.
        if score < course_pass_mark(course):
            record["certificates"] = [slug for slug in record.get("certificates", [])
                                      if not self._cert_needs(doc, slug, code)]
        with self._lock:
            self._write(doc)
        return {"program": doc["id"], "student": student, "course": code,
                "progress": self.progress(doc, student)}

    @staticmethod
    def _passed(doc: dict, courses: dict, student: str, code: str) -> bool:
        record = (doc.get("enrollments") or {}).get(student) or {}
        course = courses.get(code)
        if course is None:
            return False
        score = (record.get("grades") or {}).get(code)
        if score is None:
            return False
        if score < course_pass_mark(course):
            return False
        if course.get("finalExam") not in (None, "", "none"):
            return bool((record.get("finals") or {}).get(code))
        return True

    @staticmethod
    def _cert_needs(doc: dict, slug: str, code: str) -> bool:
        for cert in doc.get("certificates") or []:
            if cert.get("slug") == slug and code in (cert.get("requiredCourses") or []):
                return True
        return False

    def progress(self, doc_or_id, student: str) -> dict:
        doc = self._read(doc_or_id) if isinstance(doc_or_id, str) else doc_or_id
        student = str(student or "").strip()
        courses = self._course_map(doc)
        record = (doc.get("enrollments") or {}).get(student) or {}
        grades = record.get("grades") or {}
        finals = record.get("finals") or {}
        sources = record.get("gradeSources") or {}

        earned = 0
        points = 0.0
        completed, remaining, failed = [], [], []
        available = []
        final_rows = []
        for semester in doc.get("semesters", []):
            for course in semester.get("courses", []):
                code = course["code"]
                passed = self._passed(doc, courses, student, code)
                score = grades.get(code)
                if passed:
                    completed.append({
                        "code": code, "title": course["title"],
                        "credits": course["credits"], "score": score,
                        "source": sources.get(code) or "office",
                        "gradePoints": grade_points(score),
                        "semester": semester["number"],
                    })
                    earned += course["credits"]
                    points += grade_points(score) * course["credits"]
                else:
                    row = {"code": code, "title": course["title"],
                           "credits": course["credits"], "score": score,
                           "source": sources.get(code), "semester": semester["number"]}
                    if score is not None:
                        failed.append(row)
                    remaining.append(row)
                    if all(self._passed(doc, courses, student, p)
                           for p in (course.get("prerequisites") or [])):
                        available.append({**row, "semester": semester["number"]})
                if course.get("finalExam") not in (None, "", "none"):
                    blueprint = final_exam_blueprint(course)
                    final_rows.append({
                        "code": code, "title": course["title"],
                        "type": blueprint["type"], "label": blueprint["label"],
                        "weight": blueprint["weight"], "semester": semester["number"],
                        "scheduled": course.get("semester") or semester["number"],
                        "passed": bool(finals.get(code)),
                        "score": score, "source": sources.get(code),
                    })

        gpa = round(points / earned, 2) if earned else 0.0
        certificates = self._certificates_earned(doc, student)
        blockers = []
        if earned < int(doc.get("totalCredits") or 0):
            blockers.append(f"{doc.get('totalCredits')} credits required, {earned} earned")
        if remaining:
            blockers.append(f"{len(remaining)} course(s) still incomplete")
        if gpa < float(doc.get("minGpa") or 2.0):
            blockers.append(f"GPA {gpa} is below the {doc.get('minGpa')} minimum")
        failed_finals = [row["code"] for row in final_rows
                         if row["score"] is not None and not row["passed"]]
        if failed_finals:
            blockers.append("final not passed: " + ", ".join(failed_finals))

        semester_views = []
        for semester in doc.get("semesters", []):
            rows = semester.get("courses", [])
            done = sum(1 for course in rows
                       if self._passed(doc, courses, student, course["code"]))
            semester_views.append({
                "number": semester["number"], "name": semester["name"],
                "credits": semester.get("credits"),
                "completed": done, "total": len(rows),
                "state": ("complete" if done == len(rows) else
                          "in-progress" if done else "not-started"),
            })

        return {
            "program": doc.get("id"),
            "student": student,
            "enrolled": bool(record),
            "enrolledAt": record.get("enrolledAt"),
            "creditsEarned": earned,
            "creditsRequired": doc.get("totalCredits"),
            "creditsRemaining": max(0, int(doc.get("totalCredits") or 0) - earned),
            "gpa": gpa,
            "minGpa": doc.get("minGpa"),
            "completed": completed,
            "remaining": remaining,
            "failed": failed,
            "available": available,
            "finals": final_rows,
            "semesters": semester_views,
            "certificates": certificates,
            "eligible": not blockers,
            "blockers": blockers,
            "conferred": (record.get("conferred") or None),
        }

    def _certificates_earned(self, doc: dict, student: str) -> list[dict]:
        courses = self._course_map(doc)
        record = (doc.get("enrollments") or {}).get(student) or {}
        earned = []
        for cert in doc.get("certificates") or []:
            if all(self._passed(doc, courses, student, code)
                   for code in cert.get("requiredCourses") or []):
                earned.append(cert)
                if cert.get("slug") not in (record.get("certificates") or []):
                    record.setdefault("certificates", []).append(cert.get("slug"))
        return earned

    def confer(self, program_id: str, student: str) -> dict:
        """Confer the credential when — and only when — every requirement is met.

        Returns the conferral record. A second call is idempotent and returns the
        stored record rather than minting a new one.
        """
        student = str(student or "").strip()
        if not student:
            raise ProgramError(400, "a learner needs an identity")
        doc = self._read(program_id)
        record = doc.setdefault("enrollments", {}).setdefault(
            student, {"enrolledAt": _now_iso(self.clock), "grades": {},
                      "finals": {}, "certificates": [], "conferred": None})
        if record.get("conferred"):
            return {"program": doc["id"], "student": student,
                    "conferred": record["conferred"], "alreadyConferred": True}
        state = self.progress(doc, student)
        if not state["eligible"]:
            raise ProgramError(409, "the credential is not yet conferrable: "
                                   + "; ".join(state["blockers"]))
        conferral = {
            "id": f"{doc['id']}::{student}",
            "program": doc["id"],
            "programName": doc["name"],
            "credential": doc["credential"],
            "credentialKind": doc.get("credentialKind"),
            "student": student,
            "credits": state["creditsEarned"],
            "gpa": state["gpa"],
            "certificates": [cert.get("name") for cert in state["certificates"]],
            "conferredAt": _now_iso(self.clock),
            "finalExaminationsPassed": [
                row["code"] for row in state["finals"] if row["passed"]],
        }
        record["conferred"] = conferral
        with self._lock:
            self._write(doc)
            self._write_conferral(conferral)
        return {"program": doc["id"], "student": student,
                "conferred": conferral, "alreadyConferred": False}

    def attach_credential_document(self, program_id: str, student: str,
                                   document: dict) -> dict:
        """Store the signing outcome on a conferral, without changing the award."""
        doc = self._read(program_id)
        record = (doc.get("enrollments") or {}).get(str(student or "").strip())
        if not record or not record.get("conferred"):
            raise ProgramError(404, "that learner has no conferral on this program")
        record["conferred"]["document"] = document or {}
        with self._lock:
            self._write(doc)
            self._write_conferral(record["conferred"])
        return {"ok": True, "program": doc["id"], "student": student,
                "document": record["conferred"]["document"]}

    def writable(self) -> dict:
        """Whether the store can be written, and why not — for a health check."""
        try:
            os.makedirs(self._dir(), exist_ok=True)
        except OSError as err:
            return {"ok": False, "path": self._dir(), "error": str(err)}
        if not os.access(self._dir(), os.W_OK):
            return {"ok": False, "path": self._dir(), "error": "directory is not writable"}
        return {"ok": True, "path": self._dir()}

    def _write_conferral(self, conferral: dict) -> None:
        path = os.path.join(os.path.dirname(self._dir()) or ".",
                            "conferrals", f"{conferral['id'].replace('::', '__')}.json")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(conferral, fh, indent=2, ensure_ascii=False, sort_keys=True)
        except OSError:
            # The program file already holds the conferral; the sidecar is for
            # the registrar's export, not the source of truth.
            pass


def final_exam_blueprint(course: dict) -> dict:
    """How one course finally assesses a learner.

    The blueprint is concrete enough to generate a paper from: sections, their
    weight, and what a pass demonstrates.
    """
    kind = str(course.get("finalExam") or "comprehensive")
    title = course.get("title") or course.get("code") or "the course"
    credits = int(course.get("credits") or 3)
    if kind == "practical":
        return {
            "type": "practical",
            "label": f"Practical examination — {title}",
            "weight": 40,
            "duration": "90 minutes, observed",
            "sections": [
                {"name": "Skill demonstration", "weight": 50,
                 "detail": "Perform the assessed procedure under observation."},
                {"name": "Safety and judgement", "weight": 30,
                 "detail": "Recognise a hazard, state the response, and act on it."},
                {"name": "Documentation", "weight": 20,
                 "detail": "Record the encounter accurately and completely."},
            ],
            "guidance": ("Learners are assessed on a supervised performance against "
                         "a checklist; a fail means re-demonstration, not a written resit."),
        }
    if kind in ("project", "portfolio"):
        return {
            "type": kind,
            "label": (f"Final project — {title}" if kind == "project"
                      else f"Final portfolio — {title}"),
            "weight": 35,
            "duration": "two weeks, submitted",
            "sections": [
                {"name": "Artefact", "weight": 50,
                 "detail": "The work itself, judged against the stated criteria."},
                {"name": "Rationale", "weight": 30,
                 "detail": "Why these choices, what was rejected, and on what evidence."},
                {"name": "Reflection", "weight": 20,
                 "detail": "What the learner would do differently and why."},
            ],
            "guidance": ("The submission is assessed against a published rubric; "
                         "the rationale is what separates a pass from a distinction."),
        }
    return {
        "type": "comprehensive",
        "label": f"Comprehensive final examination — {title}",
        "weight": 30,
        "duration": f"{max(60, credits * 30)} minutes, proctored",
        "sections": [
            {"name": "Terminology and concepts", "weight": 30,
             "detail": "Multiple-choice and short answer across every chapter."},
            {"name": "Applied analysis", "weight": 45,
             "detail": "A scenario the learner has not seen, answered with course method."},
            {"name": "Extended response", "weight": 25,
             "detail": "A defended argument or worked problem worth a third of the paper."},
        ],
        "guidance": ("A cumulative examination across the whole course; passing it "
                     "is required for completion, and the score is reported separately."),
    }
