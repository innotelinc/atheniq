#!/usr/bin/env python3
"""AthenIQ — the learner portal.

`lms.innotel.us` is where a learner starts: the programs the platform runs and
the courses it teaches, in one place, before they sign in to the LMS to work.
This service is that front page and the read-only JSON behind it.

WHY IT IS SEPARATE FROM THE CONSOLE. The console is a staff surface: every
route needs an SSO identity and an allowed group, and the things it exposes
include runs, specs and learner records. A catalog must not inherit that
either way — a learner should not need a staff account to read what the school
teaches, and a public page must not be able to reach a gradebook. So this
process serves only:

    GET /                      the portal (web/student/)
    GET /api/public/programs   running programs, as catalog cards
    GET /api/public/programs/<id>  one program: semesters, courses, finals
    GET /api/public/courses    courses and their generated classrooms
    GET /healthz               the process is up

WHAT IS DELIBERATELY ABSENT. Enrolment records, grades, runs, specs and the
signing configuration never cross this boundary. `_public_program` drops the
`enrollments` map and the creator before answering, so the page cannot leak a
learner by being asked the wrong question.

Configuration (environment):

    STUDENT_BIND     address to listen on (default 127.0.0.1)
    STUDENT_PORT     port to listen on (default 8092)
    STUDENT_ROOT     repository root holding programs/, courses/ and web/
    CLASSROOM_HOST   public classroom host for links
                     (default https://classroom.innotel.us)

Python is stdlib only, like every other script in this tree.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import sys
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM_MANAGER_PATH = os.path.join(REPO, "scripts", "program-manager.py")
BUILDER_PATH = os.path.join(REPO, "scripts", "build-classrooms.py")

#: A catalog response is public; a minute of staleness is invisible and keeps
#: a refresh loop from walking the store on every keystroke.
CACHE_SECONDS = 60


def _load(name: str, path: str):
    """Import a hyphenated script by path, registering it for dataclasses."""
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


@dataclass
class Config:
    bind: str = "127.0.0.1"
    port: int = 8092
    root: str = REPO
    classroom_host: str = "https://classroom.innotel.us"

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        return cls(
            bind=env.get("STUDENT_BIND", "127.0.0.1"),
            port=int(env.get("STUDENT_PORT", "8092")),
            root=env.get("STUDENT_ROOT", REPO),
            classroom_host=env.get("CLASSROOM_HOST",
                                   "https://classroom.innotel.us").rstrip("/"),
        )


class Catalog:
    """Read-only views over the program store and the course specs."""

    def __init__(self, config: Config):
        self.config = config
        # `self.store`, not `self.programs`: the class has a `programs()` view,
        # and an attribute of the same name would shadow it.
        self.store = _load("atheniq_program_manager", PROGRAM_MANAGER_PATH).ProgramStore(
            os.path.join(config.root, "programs"))
        builder = _load("atheniq_build_classrooms", BUILDER_PATH)
        self.builder = builder
        self.course_root = os.path.join(config.root, "courses")

    # -- programs --------------------------------------------------------

    def programs(self) -> dict:
        return {
            "programs": [self._card(doc) for doc in self._programs()],
            "templates": self.store.template_summaries(),
        }

    def _programs(self) -> list[dict]:
        out = []
        for summary in self.store.list_programs():
            try:
                out.append(self.store.get(summary["id"]))
            except Exception:  # noqa: BLE001 — one unreadable file is not a dead catalog
                continue
        return out

    def _card(self, doc: dict) -> dict:
        plan = doc.get("plan") or {}
        return {
            "id": doc["id"],
            "name": doc["name"],
            "credential": doc.get("credential"),
            "credentialKind": doc.get("credentialKind"),
            "level": doc.get("level"),
            "totalCredits": doc.get("totalCredits"),
            "description": doc.get("description"),
            "startTerm": doc.get("startTerm"),
            "semesters": len(plan.get("semesters") or []),
            "courses": sum(len(s.get("courses") or []) for s in plan.get("semesters") or []),
            "finals": len(plan.get("finals") or []),
            "certificates": [c.get("name") for c in doc.get("certificates") or []],
            "generated": sum(1 for s in plan.get("semesters") or []
                             for c in s.get("courses") or [] if c.get("classroomIds")),
        }

    def program(self, program_id: str) -> dict | None:
        try:
            doc = self.store.get(program_id)
        except Exception:  # noqa: BLE001 — an unknown id and a broken file are both "no"
            return None
        return self._public_program(doc)

    @staticmethod
    def _public_program(doc: dict) -> dict:
        """One program, with the learner-bearing parts removed.

        `enrollments` holds identities, grades and finals; `createdBy` holds a
        staff account. Neither belongs on a public page, and dropping them here
        — rather than trusting the template not to print them — is what makes
        that true for every future caller.
        """
        plan = doc.get("plan") or {}
        semesters = []
        for semester in plan.get("semesters") or []:
            courses = []
            for course in semester.get("courses") or []:
                courses.append({
                    "code": course.get("code"),
                    "title": course.get("title"),
                    "credits": course.get("credits"),
                    "kind": course.get("kind"),
                    "description": course.get("description"),
                    "prerequisites": course.get("prerequisites") or [],
                    "finalExam": course.get("finalExam"),
                    "final": course.get("final"),
                    "classrooms": len(course.get("classroomIds") or []),
                })
            semesters.append({
                "number": semester.get("number"),
                "name": semester.get("name"),
                "credits": semester.get("credits"),
                "courses": courses,
            })
        return {
            "id": doc.get("id"),
            "name": doc.get("name"),
            "credential": doc.get("credential"),
            "credentialKind": doc.get("credentialKind"),
            "level": doc.get("level"),
            "totalCredits": doc.get("totalCredits"),
            "minGpa": doc.get("minGpa"),
            "description": doc.get("description"),
            "startTerm": doc.get("startTerm"),
            "capstone": doc.get("capstone"),
            "certificates": [{k: c.get(k) for k in
                              ("slug", "name", "afterSemester", "requiredCourses", "description")}
                             for c in doc.get("certificates") or []],
            "semesters": semesters,
            "finals": plan.get("finals") or [],
        }

    # -- courses ---------------------------------------------------------

    @staticmethod
    def _course_code(spec: dict) -> str:
        """The run's course code: `course-v1:InnotelLabs+FAI103+2026_T4` → FAI103.

        A program plan names a course by its code, so this is how a built spec is
        matched to the plan entry it satisfies.
        """
        source = str(spec.get("source_course") or "")
        parts = source.split("+")
        return (parts[1] if len(parts) > 1 else source).strip().upper()

    def _planned_courses(self, built: set[str]) -> list[dict]:
        """Courses that exist only in a program plan.

        A program carries its whole curriculum the moment it is saved, but a
        course spec — and so a course in this catalog — is written only when a
        classroom is generated. So a program created five minutes ago listed its
        courses inside the program and showed none of them under Courses, which
        reads as "the course was not created". These are those courses, marked
        `planned` and pointing at the program that teaches them, so they can be
        found before anything is built.
        """
        out, seen = [], set()
        for summary in self.store.list_programs():
            try:
                doc = self.store.get(summary["id"])
            except Exception:  # noqa: BLE001 — one unreadable file is not a dead catalog
                continue
            for semester in (doc.get("plan") or {}).get("semesters") or []:
                for course in semester.get("courses") or []:
                    code = str(course.get("code") or "").strip().upper()
                    if not code or code in built or code in seen:
                        continue
                    seen.add(code)
                    out.append({
                        "slug": None, "code": code,
                        "title": course.get("title"),
                        "program": {"id": doc.get("id"), "name": doc.get("name")},
                        "course": "", "locale": "",
                        "classrooms": [], "generated": 0, "total": 0,
                        "planned": True,
                    })
        out.sort(key=lambda item: item["code"])
        return out

    def courses(self) -> dict:
        out = []
        classrooms = 0
        built: set[str] = set()
        for slug, path in self.builder.spec_paths(self.course_root):
            try:
                doc = self.builder.read_spec(path)
            except Exception:  # noqa: BLE001 — a broken spec is skipped, not fatal
                continue
            rooms = []
            for classroom in doc.get("classrooms") or []:
                stage = classroom.get("classroom_id") or ""
                rooms.append({
                    "id": classroom.get("id"),
                    "chapter": classroom.get("chapter"),
                    "title": classroom.get("title"),
                    "generated": bool(stage),
                    "url": f"{self.config.classroom_host}/classroom/{stage}" if stage else None,
                })
            built.add(self._course_code(doc))
            classrooms += sum(1 for room in rooms if room["generated"])
            out.append({
                "slug": slug,
                "course": doc.get("source_course") or "",
                "locale": doc.get("locale") or "",
                "classrooms": rooms,
                "generated": sum(1 for room in rooms if room["generated"]),
                "total": len(rooms),
            })
        out.sort(key=lambda item: item["slug"])
        out.extend(self._planned_courses(built))
        return {"courses": out, "classroomsLive": classrooms,
                "classroomHost": self.config.classroom_host}


class Handler(BaseHTTPRequestHandler):
    server_version = "AthenIQStudent/1"
    catalog: Catalog = None  # set by make_server()

    def log_message(self, fmt, *args):  # the portal is public; keep the log quiet
        pass

    def _send(self, status, body=b"", content_type="application/json; charset=utf-8",
              cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, payload, cache=f"public, max-age={CACHE_SECONDS}"):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode(),
                   cache=cache)

    def _error(self, status, message):
        self._json(status, {"error": message}, cache="no-store")

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/healthz":
            return self._json(200, {"ok": True}, cache="no-store")
        if path == "/api/public/programs":
            return self._json(200, self.catalog.programs())
        if path.startswith("/api/public/programs/"):
            program_id = urllib.parse.unquote(path[len("/api/public/programs/"):]).strip("/")
            doc = self.catalog.program(program_id)
            if doc is None:
                return self._error(404, f"no program {program_id!r}")
            return self._json(200, doc)
        if path == "/api/public/courses":
            return self._json(200, self.catalog.courses())
        if path.startswith("/api/"):
            return self._error(404, "no such endpoint")
        return self._static(path)

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        self._error(405, "the learner catalog is read-only")

    def _static(self, path):
        web_root = os.path.join(self.catalog.config.root, "web", "student")
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        target = os.path.normpath(os.path.join(web_root, rel))
        if os.path.commonpath([os.path.abspath(target), os.path.abspath(web_root)]) \
                != os.path.abspath(web_root):
            return self._error(404, "not found")
        if not os.path.isfile(target):
            # A single-page app: an unknown path is the portal, not a 404 page.
            target = os.path.join(web_root, "index.html")
            if not os.path.isfile(target):
                return self._error(404, "not found")
        with open(target, "rb") as fh:
            body = fh.read()
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype, cache="public, max-age=300")


def make_server(config: Config):
    catalog = Catalog(config)
    handler = type("BoundHandler", (Handler,), {"catalog": catalog})
    return ThreadingHTTPServer((config.bind, config.port), handler), catalog


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", help="address to listen on (STUDENT_BIND)")
    ap.add_argument("--port", type=int, help="port to listen on (STUDENT_PORT)")
    ap.add_argument("--root", help="repository root (STUDENT_ROOT)")
    args = ap.parse_args()

    config = Config.from_env()
    if args.bind:
        config.bind = args.bind
    if args.port:
        config.port = args.port
    if args.root:
        config.root = args.root

    server, _ = make_server(config)
    print(f"learner portal on http://{config.bind}:{config.port} "
          f"(programs: {config.root}/programs)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
