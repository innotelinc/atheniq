#!/usr/bin/env python3
"""AthenIQ — the course-generation console.

The operator surface for turning a course's classroom briefs into live
OpenMAIC classrooms. `scripts/build-classrooms.py` does the same work from a
shell; this is that work from a browser, for the people who write the briefs
rather than the people who run the batch.

WHAT IT SERVES. One page (`web/generate/`) and the JSON behind it:

    GET    /api/me                 who the proxy says you are, and whether you may generate
    GET    /api/health             OpenMAIC's health and the model each slot resolves to
    GET    /api/courses            every course's classrooms: generated, missing, or in flight
    GET    /api/runs               the runs OpenMAIC still holds, plus what was recorded
    GET    /api/runs/<id>          one run, with its step, error and progress
    POST   /api/generate           submit a classroom — from a spec, or a free-form brief
    POST   /api/generate-missing   submit every classroom the specs say is missing
    POST   /api/runs/<id>/retry    resume a paused run
    POST   /api/runs/<id>/record   write a finished classroom's id back into its spec
    DELETE /api/runs/<id>          discard a paused run that has no classroom

    GET    /api/programs           running programs and the catalog templates
    POST   /api/programs           create a program from a template or a course list
    GET    /api/programs/<id>      one program, with its semester plan and finals
    GET    /api/programs/<id>/progress?student=…  one learner's standing
    POST   /api/programs/<id>/generate  submit a classroom run per course
    POST   /api/programs/<id>/sync      record finished runs into the plan
    POST   /api/programs/<id>/lessons   write generated lessons + exams into the courses
    POST   /api/programs/<id>/grades    read each learner's course grades from the LMS
    POST   /api/programs/<id>/enroll    enroll a learner (in the program and the LMS)
    POST   /api/programs/<id>/publish   create the program's courses in the LMS
    POST   /api/programs/<id>/complete  record a grade and final result
    POST   /api/programs/<id>/confer    confer the degree/certificate and sign it
    DELETE /api/programs/<id>           delete it with the courses and classes it owned
    DELETE /api/programs/<id>/courses/<code>  remove one course and its classes
    GET    /api/templates               the catalog templates
    POST   /api/templates               create one
    GET    /api/templates/<slug>        one template, with its curriculum
    PUT    /api/templates/<slug>        replace one (a shipped one is overridden)
    DELETE /api/templates/<slug>        remove one from the catalog

RECORDING IS NOT A STEP. A run that came from a spec writes its classroom back
into that spec as soon as it completes — during the page's poll, and on a timer
(`GENERATION_AUTORECORD_SECONDS`) so an overnight run is recorded before anybody
looks — and the entry leaves the list. The manual `/record` route remains for a
run that was started before the console learned to do this.

WHO MAY USE IT. It sits behind oauth2-proxy, and it does not trust that: every
request has to carry the identity headers the proxy sets (`--set-xauthrequest`
and `--pass-user-headers`), and the caller has to hold one of
`GENERATION_ALLOWED_GROUPS`. A request with no identity is a 401 and a request
with the wrong groups is a 403 — so a misrouted proxy fails closed instead of
publishing an endpoint that spends model budget. `GENERATION_TRUST_LOCAL=1`
is the only way around that, for the box's own `make generation-console`.

WHY A SEPARATE SERVICE. OpenMAIC's own UI is the classroom: it lets whoever can
reach it generate anything and shows every classroom's workspace. This is the
narrow, staff-only half — the course specs are the allowlist, the briefs are
the ones committed in the repo, and the only thing it can create is a classroom.

Configuration (environment):

    OPENMAIC_BASE_URL          where OpenMAIC's HTTP API is (default http://127.0.0.1:3000)
    GENERATION_BIND            address to listen on (default 127.0.0.1)
    GENERATION_PORT            port to listen on (default 8090)
    GENERATION_ALLOWED_GROUPS  comma-separated groups that may generate
                               (default atheniq-admins,instructors)
    GENERATION_TRUST_LOCAL     "1" accepts requests without proxy headers (local only)
    GENERATION_MAX_REQUIREMENT longest brief accepted, in characters (default 6000 —
                               the gateway refuses prompts longer than that)
    GENERATION_SUBMITS_PER_HOUR submissions one person may start per hour
                               (default 10; 0 disables the ceiling, which is
                               how a deployment that starts a whole course
                               at once runs)
    GENERATION_ROOT            repository root holding courses/ and web/ (default: this repo)
    CLASSROOM_HOST             public classroom host for links (default https://classroom.innotel.us)

Python is stdlib only, like every other script here: no dependency to install on
the box that runs it.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import mimetypes
import os
import posixpath
import shutil
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER_PATH = os.path.join(REPO, "scripts", "build-classrooms.py")
PROGRAM_MANAGER_PATH = os.path.join(REPO, "scripts", "program-manager.py")
PUBLISHER_PATH = os.path.join(REPO, "scripts", "publish-courses.py")
CERT_BRIDGE_PATH = os.path.join(REPO, "scripts", "cert-bridge.py")
COURSE_MATERIALS_PATH = os.path.join(REPO, "scripts", "course-materials.py")

#: A brief longer than this is refused by the gateway ("Prompt too long (max
#: 6000 characters)"), so the console refuses it first with a message that says
#: what to cut instead of a 502 an hour later.
DEFAULT_MAX_REQUIREMENT = 6000

#: The identity headers oauth2-proxy can supply. Two families, because the two
#: flags write to different places: `--set-xauthrequest` sets `X-Auth-Request-*`
#: on the *response* (for an nginx `auth_request` in front of it), while
#: `--pass-user-headers` sets `X-Forwarded-*` on the request it proxies
#: *upstream* — which is the request this console actually receives. Accept
#: both, preferring the explicit `X-Auth-Request-*` names, and treat a request
#: that carries neither as unauthenticated.
USER_HEADERS = (("X-Auth-Request-User", "X-Forwarded-User"),
                ("X-Auth-Request-Email", "X-Forwarded-Email"))
GROUPS_HEADERS = ("X-Auth-Request-Groups", "X-Forwarded-Groups")

#: A mutating request must carry this header. A browser form cannot set it
#: cross-origin without a CORS preflight (which this server never grants), so it
#: is the CSRF guard: the console's own JS always sends it, a hostile page cannot.
CONSOLE_HEADER = "X-Atheniq-Console"

MAX_BODY = 64 * 1024


def _library_slug(name: str) -> str:
    """A folder name for a library: its words, joined, lower case.

    The name is what an operator typed and the slug is what the spec and the
    courseware reference, so it is derived once, here, and never trusted from
    the client — a `..` in a name must not become a path.
    """
    cleaned = "".join(ch if ch.isalnum() or ch in " -_" else " " for ch in name)
    return "-".join(part for part in cleaned.lower().replace("_", " ").split() if part)[:48]


def _load_builder():
    """The batch tool, imported for its brief-building and API client.

    One source of truth for what a spec's brief says and how OpenMAIC is
    called: if `build-classrooms.py` learns a new field, the console submits it
    too. The module is standalone (its `main()` is behind a guard).
    """
    name = "atheniq_build_classrooms"
    spec = importlib.util.spec_from_file_location(name, BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _load_publisher():
    """The LMS publisher, imported by path.

    A program's courses are only useful once the LMS has them: that is what
    *Explore courses* lists and what a learner can be enrolled in. The publisher is
    where the OLX shell and the CMS import live, so the console does not grow a
    second copy of that knowledge.
    """
    name = "atheniq_publish_courses"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, PUBLISHER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _load_program_manager():
    """The degree-program store, imported by path.

    It has no HTTP of its own: the console is the only surface, so programs get
    the same identity, rate limits, and OpenMAIC client as classrooms instead
    of a second service with a second set of rules.
    """
    name = "atheniq_program_manager"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, PROGRAM_MANAGER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _load_course_materials():
    """The syllabus and quiz generator, imported by path.

    The scripts here are standalone files rather than a package, so a relative
    `from .course_materials import …` cannot resolve; this is that import done
    the way the rest of the tree does it.
    """
    name = "atheniq_course_materials"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, COURSE_MATERIALS_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _load_cert_bridge():
    """The Signara renderer and client, imported only when a degree is conferred.

    A console with no Signara key never needs this module, so it is not loaded
    at boot: importing it is a credential, not a convenience.
    """
    name = "atheniq_cert_bridge"
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, CERT_BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _error_text(value) -> str:
    """The sentence inside an upstream error, whatever shape it arrived in.

    OpenMAIC reports `error` as either a string or an object with a `message`.
    Reading only the object raised AttributeError on the string form, inside
    the request handler, which closed the socket, and a closed socket is what
    the SSO proxy in front of this console reports as a 502. The refusal was
    real; the crash was in describing it.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        error = value.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail"):
                if error.get(key):
                    return str(error[key])
        elif error:
            return str(error)
        for key in ("message", "detail", "error_description"):
            if value.get(key):
                return str(value[key])
        return json.dumps(value, default=str)[:500]
    return str(value)


@dataclass
class Config:
    base_url: str = "http://127.0.0.1:3000"
    bind: str = "127.0.0.1"
    port: int = 8090
    allowed_groups: tuple[str, ...] = ("atheniq-admins", "instructors")
    trust_local: bool = False
    max_requirement: int = DEFAULT_MAX_REQUIREMENT
    submits_per_hour: int = 10
    root: str = REPO
    classroom_host: str = "https://classroom.innotel.us"
    #: How often the service records finished classrooms on its own, in seconds.
    #: 0 is "only when the page polls": the sweeper exists so a classroom is
    #: written back while nobody is looking, which is the whole point of doing it
    #: automatically, so a deployment sets this (the unit ships 20).
    autorecord_seconds: int = 0
    #: Where the run -> spec map is kept, so a restart does not forget a classroom
    #: that finished while the process was down. Empty keeps it in memory.
    state_path: str = ""
    #: Publish a program's courses into the LMS as it is created (and when the
    #: page asks): a course that is not in the LMS cannot be enrolled in, so it can
    #: never appear in *My courses* or *Explore courses*. Off by default here so a
    #: test or a laptop needs no docker; `from_env` turns it on unless the
    #: deployment sets `GENERATION_PUBLISH=0`.
    publish_courses: bool = False
    #: Where the generated OLX shells and the publishing record are kept.
    lms_work_dir: str = ""

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        groups = tuple(g.strip() for g in env.get("GENERATION_ALLOWED_GROUPS",
                                                  "atheniq-admins,instructors").split(",")
                       if g.strip())
        return cls(
            base_url=env.get("OPENMAIC_BASE_URL", "http://127.0.0.1:3000"),
            bind=env.get("GENERATION_BIND", "127.0.0.1"),
            port=int(env.get("GENERATION_PORT", "8090")),
            allowed_groups=groups,
            trust_local=env.get("GENERATION_TRUST_LOCAL", "") in ("1", "true", "yes"),
            max_requirement=int(env.get("GENERATION_MAX_REQUIREMENT", DEFAULT_MAX_REQUIREMENT)),
            submits_per_hour=int(env.get("GENERATION_SUBMITS_PER_HOUR", "10")),
            root=env.get("GENERATION_ROOT", REPO),
            classroom_host=env.get("CLASSROOM_HOST", "https://classroom.innotel.us").rstrip("/"),
            autorecord_seconds=int(env.get("GENERATION_AUTORECORD_SECONDS", "0")),
            state_path=env.get("GENERATION_STATE", ""),
            publish_courses=env.get("GENERATION_PUBLISH", "1").strip().lower()
            not in ("0", "false", "no", "off"),
            lms_work_dir=env.get("GENERATION_LMS_DIR", ""),
        )


@dataclass
class Identity:
    user: str
    email: str = ""
    groups: tuple[str, ...] = ()

    def holds(self, allowed) -> bool:
        """Whether this person may generate: group match, case-insensitive.

        oauth2-proxy forwards Authentik's group names verbatim, and those are
        written by hand in the IdP, so a case difference is a typo, not a
        different group.
        """
        mine = {g.strip().lower() for g in (self.groups or ())}
        return any(a.strip().lower() in mine for a in allowed)

    def as_view(self, allowed) -> dict:
        return {"user": self.user, "email": self.email,
                "groups": list(self.groups), "mayGenerate": self.holds(allowed)}


class Unavailable(RuntimeError):
    """OpenMAIC could not be reached or the gateway refused the call."""


class Console:
    """The console's behavior, separated from HTTP so tests can drive it.

    Every method returns plain data and raises `Bad` for a request the operator
    should fix (400/403/409) or `Unavailable` for anything OpenMAIC's side did
    (502), so the HTTP layer is only about status codes and shapes.
    """

    def __init__(self, config, builder=None, clock=time.time, programs=None, publisher=None):
        self.config = config
        self.builder = builder or _load_builder()
        self.clock = clock
        self.publisher = publisher
        if self.publisher is None and config.publish_courses:
            # A host without docker (or without the LMS) must still start the
            # console: publishing then reports that it is unavailable instead of
            # taking the page down with it.
            try:
                module = _load_publisher()
                self.publisher = module.Publisher(
                    config.root,
                    work_dir=config.lms_work_dir or os.path.join(config.root, "lms"),
                    clock=clock)
            except Exception:  # noqa: BLE001 — a broken publisher is not a broken console
                self.publisher = None
        #: program id -> the last publish run, so the page can say what happened
        #: without the request having to last as long as a whole program's imports.
        self._publish_runs = {}
        #: program id -> the last lesson build, for the same reason: one course is
        #: an OLX rewrite plus a CMS import, and a program has dozens.
        self._lesson_runs = {}
        self._program_module = _load_program_manager()
        self._program_error = self._program_module.ProgramError
        if programs is None:
            programs = self._program_module.ProgramStore(
                os.path.join(config.root, "programs"), clock=clock)
        self.programs = programs
        self._submissions = collections.defaultdict(collections.deque)
        #: run id -> where it came from (`course`/`classroom`/spec path, or free).
        #: The console is where the run was started, so it is the only place
        #: that can write the result back to the right line of the right spec.
        self._started = collections.OrderedDict()
        #: classrooms a batch asked for that OpenMAIC had no room for yet, in the
        #: order they were asked for. They are started by `pump()` as runs finish,
        #: so one click covers a course with more classrooms than the generator
        #: will run at once. Each entry carries the identity that asked, because
        #: the hourly limit is that person's whatever thread ends up submitting.
        self._queue = collections.deque()
        #: runs that left the active list, kept so the page can still show how
        #: they ended (a completed run is not "active" and would vanish).
        self._finished = {}
        #: the classrooms written back without a click, newest last. Shown so an
        #: operator sees the recording happened rather than inferring it from a
        #: run disappearing out of a list.
        self._recorded = collections.deque(maxlen=20)
        self._lock = threading.Lock()
        #: Held for a whole pass of `pump()`. The sweeper thread and an open page
        #: both pump, and this is what stops them starting the same classroom
        #: twice; it is separate from `_lock`, which only guards the data.
        self._pump_lock = threading.Lock()
        self._load_state()

    # -- what survives a restart ------------------------------------------

    def _load_state(self) -> None:
        """Remember which run belongs to which spec, across a service restart.

        Without this, a classroom that finished while the process was restarting
        is never recorded: the run's origin lived only in memory, and the spec is
        the only thing the course actually embeds.
        """
        path = self.config.state_path
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        started = data.get("started") if isinstance(data, dict) else None
        queued = data.get("queue") if isinstance(data, dict) else None
        if isinstance(started, dict):
            for run_id, source in list(started.items())[-50:]:
                if isinstance(source, dict):
                    self._started[str(run_id)] = source
        if isinstance(queued, list):
            for item in queued[:100]:
                if isinstance(item, dict) and item.get("course") and item.get("classroom"):
                    self._queue.append(item)

    def _save_state(self) -> None:
        """Write the run -> spec map, atomically, and never fail a request for it.

        The state file is an optimization for the restart case; a read-only
        GENERATION_STATE must not turn a generation into an error.
        """
        path = self.config.state_path
        if not path:
            return
        with self._lock:
            payload = {"started": dict(self._started), "queue": list(self._queue)}
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = f"{path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except OSError:
            pass

    # -- courses ---------------------------------------------------------

    def courses(self) -> list[dict]:
        """Every classroom in every spec, with the state a person can act on.

        `generated` is the spec's own record (`classroom_id`), which is what the
        embeds point at; a classroom generated from the console is written back
        by that same field, so the page agrees with the courseware.
        """
        root = os.path.join(self.config.root, "courses")
        out = []
        for slug, path in self.builder.spec_paths(root):
            doc = self.builder.read_spec(path)
            classrooms = []
            for classroom in doc.get("classrooms", []):
                stage = classroom.get("classroom_id") or ""
                classrooms.append({
                    "id": classroom.get("id"),
                    "chapter": classroom.get("chapter"),
                    "title": classroom.get("title"),
                    "units": classroom.get("linked_units") or [],
                    "generated": bool(stage),
                    "classroomId": stage or None,
                    "url": f"{self.config.classroom_host}/classroom/{stage}" if stage else None,
                    "model": classroom.get("model"),
                })
            out.append({
                "slug": slug,
                "course": doc.get("source_course") or "",
                "locale": doc.get("locale") or "",
                "classrooms": classrooms,
                "generated": sum(1 for c in classrooms if c["generated"]),
                "total": len(classrooms),
            })
        return out

    def find_classroom(self, slug: str, classroom_id: str) -> tuple[dict, dict, str]:
        """The spec doc, the classroom entry in it, and the brief to submit."""
        root = os.path.join(self.config.root, "courses")
        for found_slug, path in self.builder.spec_paths(root):
            if found_slug != slug:
                continue
            doc = self.builder.read_spec(path)
            for classroom in doc.get("classrooms", []):
                if classroom.get("id") == classroom_id:
                    return doc, classroom, self.builder.requirement_text(doc, classroom), path
        raise Bad(404, f"no classroom {classroom_id!r} in course {slug!r}")

    # -- OpenMAIC --------------------------------------------------------

    def _client(self):
        return self.builder.OpenMAIC(self.config.base_url, timeout=20)

    def _call(self, call, *args):
        """One OpenMAIC call, with its dead-host failure as a 502 word.

        The builder raises `SystemExit` when it cannot reach the server (it is
        written for a shell, where that is the right way to stop). Here it is a
        bad gateway: the console stays up and says so.
        """
        try:
            return call(*args)
        except SystemExit as err:
            raise Unavailable(str(err)) from err
        except ValueError as err:
            # A status with no JSON body (a bare 204, a proxy's error page): the
            # builder parses every answer as JSON, so this surfaces here.
            raise Unavailable(f"OpenMAIC answered without a usable body: {err}") from err
        except (urllib.error.URLError, OSError) as err:
            raise Unavailable(f"cannot reach OpenMAIC: {err}") from err

    def health(self) -> dict:
        status, body = self._call(self._client().health)
        ok = status == 200 and bool(body.get("success", True))
        slots = []
        if ok:
            status, view = self._call(self._client().model_config)
            if status == 200:
                for slot in view.get("slots", []):
                    if slot.get("slot") in ("llm", "classroom", "agent", "course.content"):
                        slots.append({"slot": slot["slot"],
                                      "model": slot.get("assignment") or
                                               (slot.get("effective") or {}).get("modelId")})
        return {"ok": ok, "version": body.get("version") if ok else None,
                "capabilities": body.get("capabilities", {}) if ok else {},
                "slots": slots}

    def runs(self) -> list[dict]:
        """The runs OpenMAIC still holds, newest first.

        Only active ones: a finished run's classroom is what matters and the
        spec already carries its id. A paused run is the opposite — it holds a
        slot until somebody discards it, which is why it is listed.
        """
        status, body = self._call(self._client().active_runs)
        if status != 200:
            raise Unavailable(f"OpenMAIC listed no runs: {status} {body}")
        seen = {run.get("id"): self._run_view(run) for run in body.get("runs", [])}
        for run_id in list(self._started)[-12:]:
            if run_id in seen:
                continue
            known = self._finished.get(run_id)
            if known is None:
                try:
                    known = self.run(run_id)
                except (Bad, Unavailable):
                    continue
                if known.get("state") in ("completed", "failed", "ended"):
                    self._finished[run_id] = known
            seen[run_id] = known
        runs = list(seen.values())
        for run in runs:
            started = self._started.get(run["id"]) or {}
            # The spec path stays on this side; the page only needs to say where
            # the run came from.
            run["source"] = ({k: v for k, v in started.items() if k != "spec"} or None)
            run["recordable"] = bool(started.get("spec")) and run.get("state") == "completed" \
                and bool(run.get("classroomId"))
        runs.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
        # A finished classroom is written back here rather than by a click, and its
        # entry leaves the list: the spec is what the course embeds, and a run that
        # has produced one has nothing left for a person to decide.
        return [run for run in runs if not self._record_and_drop(run)]

    def recent_recordings(self) -> list[dict]:
        """The classrooms recorded automatically, newest last."""
        with self._lock:
            return list(self._recorded)

    def run(self, run_id: str) -> dict:
        status, body = self._call(self._client().run, run_id)
        if status != 200:
            raise Bad(404, f"no run {run_id!r}")
        return self._run_view(body.get("run", body))

    def _run_view(self, run: dict) -> dict:
        error = run.get("error")
        progress = run.get("progress") or {}
        if isinstance(error, dict):
            error = {"code": error.get("errorCode"), "status": error.get("statusCode"),
                     "message": _error_text(error)}
        elif error:
            error = {"code": None, "status": None, "message": _error_text(error)}
        return {
            "id": run.get("id"),
            "state": run.get("state"),
            "step": run.get("step"),
            "progress": {"done": progress.get("completed"), "total": progress.get("total")},
            "error": error if error else None,
            "classroomId": run.get("stageId") or run.get("classroomId"),
            "createdAt": run.get("createdAt"),
            "updatedAt": run.get("updatedAt"),
        }

    # -- submission ------------------------------------------------------

    def submit(self, identity: Identity, body: dict) -> dict:
        """Start a generation run, from a spec entry or a free-form brief."""
        requirement, source = self._requirement_for(body)
        self._rate_limit(identity)
        status, answer = self._call(self._client().submit, requirement)
        if status not in (200, 202):
            raise Bad(429 if status == 429 else 502,
                      f"OpenMAIC refused the brief ({status}): {_error_text(answer)}")
        run_id = answer.get("jobId") or answer.get("runId")
        if not run_id:
            raise Unavailable(f"OpenMAIC accepted the brief but named no run: {answer}")
        with self._lock:
            self._started[run_id] = dict(source)
            self._started.move_to_end(run_id)
            while len(self._started) > 50:
                self._started.popitem(last=False)
        self._save_state()
        return {"runId": run_id, "source": source, "characters": len(requirement)}

    def _check_length(self, requirement: str) -> str:
        """Refuse a brief the gateway will refuse anyway, with a usable reason.

        The gateway's limit is 6000 characters and its message arrives an hour
        later, attached to a failed run. Checking here names the problem while
        the person who wrote the brief is still looking at it.
        """
        limit = self.config.max_requirement
        if len(requirement) > limit:
            raise Bad(400, f"that brief is {len(requirement)} characters; the limit is "
                           f"{limit}. Cut the part that repeats what the chapters "
                           f"already cover.")
        return requirement

    def _requirement_for(self, body) -> tuple[str, dict]:
        """(brief, where it came from), validated.

        The two shapes are deliberately separate: `course`+`classroom` is a
        classroom somebody wrote and reviewed in the repo, and it comes with its
        chapter and unit links. `requirement` alone is the escape hatch for a
        one-off, and it still has to be substantial — a two-word prompt produces
        a classroom that teaches nothing and costs the same tokens.
        """
        if not isinstance(body, dict):
            raise Bad(400, "expected a JSON object")
        slug, classroom_id = body.get("course"), body.get("classroom")
        if slug or classroom_id:
            if not (slug and classroom_id):
                raise Bad(400, "a spec submission needs both course and classroom")
            doc, classroom, requirement, path = self.find_classroom(str(slug), str(classroom_id))
            if classroom.get("classroom_id"):
                raise Bad(409, f"{slug}/{classroom_id} already has a classroom "
                               f"({classroom['classroom_id']}); discard or reuse it")
            return self._check_length(requirement), {
                "kind": "spec", "course": slug, "classroom": classroom_id,
                "chapter": classroom.get("chapter"), "title": classroom.get("title"),
                "units": classroom.get("linked_units") or [], "spec": path,
            }
        requirement = str(body.get("requirement") or "").strip()
        if len(requirement) < 80:
            raise Bad(400, "a free-form brief needs at least 80 characters — "
                           "what the class does, who is in it, and how it is assessed")
        return self._check_length(requirement), {
            "kind": "free", "title": str(body.get("title") or "").strip() or None,
        }

    def create_course(self, identity: Identity, body: dict) -> dict:
        """Start a course creation run with full classroom + materials + entitlements.

        This is the heart of the end-to-end flow:
          1. Generate OpenMAIC brief from the subject
          2. Submit to OpenMAIC to create a classroom run
          3. If paid course: grant onyx credits + add user to Authentik paid_users group
          4. If certificate: record the grade threshold for later Signara issuance
          5. Return run ID and next steps
        """
        requirement, source = self._requirement_for(body)
        self._rate_limit(identity)
        status, answer = self._call(self._client().submit, requirement)
        if status not in (200, 202):
            message = answer if isinstance(answer, str) else (answer.get("error") or {}).get("message") \
                or answer.get("error") or answer
            raise Bad(429 if status == 429 else 502,
                      f"OpenMAIC refused the brief ({status}): {message}")
        run_id = answer.get("jobId") or answer.get("runId")
        if not run_id:
            raise Unavailable(f"OpenMAIC accepted the brief but named no run: {answer}")
        with self._lock:
            self._started[run_id] = dict(source)
            self._started.move_to_end(run_id)
            while len(self._started) > 50:
                self._started.popitem(last=False)
        self._save_state()
        cert_status = body.get("certificate", False)
        paid = body.get("paid", False)
        credits = body.get("credits", 0)
        cert_type = body.get("certType", "completion")
        grade_threshold = body.get("gradeThreshold", 80)
        # Return the run ID and all options configured for later processing
        result = {
            "runId": run_id, "source": source, "characters": len(requirement),
            "certificate": cert_status, "paid": paid, "credits": credits,
            "certType": cert_type, "gradeThreshold": grade_threshold,
        }
        # If paid course, grant onyx credits and add user to Authentik paid_users group
        if paid and credits > 0:
            try:
                credit_result = self._grant_onyx_credits(identity, credits)
                result["onyx_credits_granted"] = credit_result
                # Add user to Authentik paid_users group if identity available
                if identity:
                    result["auth_entitlement"] = self._add_auth_entitlement(identity, "paid_users")
            except Exception as e:
                result["entitlement_error"] = str(e)
        # If certificate, record grade threshold for Signara issuance later
        if cert_status:
            result["certificate_config"] = {
                "type": cert_type,
                "grade_threshold": grade_threshold,
            }
        # If materials requested, generate syllabus and quiz questions
        if body.get("generateMaterials", False):
            result["materials"] = self._generate_course_materials(body)
        return result

    def _grant_onyx_credits(self, identity: Identity, amount: int) -> dict:
        """Grant credits to a user via the onyx credit API.

        Calls the onyx admin credits endpoint to grant credits to the user.
        The onyx credit system uses a ledger with reference/audit fields.
        """
        # The onyx credit API endpoint for granting credits
        # POST /api/admin/credits/grant with: user, amount, reference, audit
        user_id = identity.user or identity.email or ""
        if not user_id:
            raise ValueError("Cannot grant credits: no user identity")
        # Call the onyx admin API to grant credits
        import urllib.request
        import urllib.parse
        import json
        import ssl

        # Build the API request to onyx
        url = "https://api.onyx.innotel.us/api/admin/credits/grant"
        payload = {
            "user": user_id,
            "amount": amount,
            "reference": f"course-completion-{run_id}" if 'run_id' in dir() else "course-creation",
            "audit": "atheniq-course-creation",
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        # Try with trusted TLS, fall back if needed
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {"status": "ok"}
        except Exception as e:
            # If onyx not available, return a graceful fallback
            raise ValueError(f"Cannot grant onyx credits (onyx API unavailable): {e}")

    def _add_auth_entitlement(self, identity: Identity, group_name: str) -> dict:
        """Add a user to an Authentik group for entitlement.

        Uses the Authentik API to add the user identified by the identity
        to the specified group. Requires AUTHENTIK_API_URL and AUTHENTIK_API_TOKEN
        to be configured in the environment.
        """
        import urllib.request
        import urllib.parse
        import json
        import ssl

        # Read Authentik config from environment
        import os
        base_url = os.environ.get('AUTHENTIK_API_URL', 'https://auth.cerulean.innotel.us')
        token = os.environ.get('AUTHENTIK_API_TOKEN', '')

        if not token:
            # No Authentik token configured - this is OK, just record intent
            return {"status": "skipped", "reason": "no_authentik_token"}

        user = identity.user or identity.email
        if not user:
            return {"status": "skipped", "reason": "no_user_identity"}

        # First, look up the user in Authentik by username
        ctx = ssl.create_default_context()
        if not ctx.verify_mode:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        try:
            # Look up user by username
            search_url = f"{base_url}/api/v3/core/users/?username={urllib.parse.quote(user)}"
            req = urllib.request.Request(search_url, method="GET")
            req.add_header("Authorization", "Bearer " + token)
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            users = data.get("results", [])
            if not users:
                return {"status": "skipped", "reason": f"user_{user}_not_found_in_authentik"}
            auth_user = users[0]
            user_pk = auth_user.get("pk")

            # Look up the paid_users group UUID
            group_search_url = f"{base_url}/api/v3/core/groups/?name={urllib.parse.quote(group_name)}"
            req2 = urllib.request.Request(group_search_url, method="GET")
            req2.add_header("Authorization", "Bearer " + token)
            req2.add_header("Accept", "application/json")
            with urllib.request.urlopen(req2, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            groups = data.get("results", [])
            if not groups:
                return {"status": "skipped", "reason": f"group_{group_name}_not_found_in_authentik"}
            paid_group = groups[0]
            group_pk = paid_group.get("pk")

            # Add user to the group
            add_url = f"{base_url}/api/v3/core/groups/{group_pk}/add_user/"
            add_data = json.dumps({"pk": user_pk}).encode("utf-8")
            req3 = urllib.request.Request(add_url, data=add_data, method="POST")
            req3.add_header("Authorization", "Bearer " + token)
            req3.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req3, timeout=30, context=ctx) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return {"status": "added", "user": user, "group": group_name}
        except Exception as e:
            return {"status": "error", "error": str(e)}


    def _generate_course_materials(self, body: dict) -> dict:
        """Generate course materials: syllabus and quiz questions.

        Uses the course_materials module to generate a syllabus and optional
        quiz questions from the subject matter brief.
        """
        materials = _load_course_materials()

        subject = body.get("requirement", "")
        title = body.get("title", "")

        syllabus = materials.generate_syllabus(subject, title)

        quiz_count = body.get("quizCount", 5)
        quiz_questions = materials.generate_quiz_questions(subject, quiz_count)

        return {
            "syllabus": syllabus,
            "quizQuestions": quiz_questions,
            "quizCount": quiz_count,
        }

    def _issue_signara_certificate(self, run: dict, cert_config: dict, started: dict) -> dict:
        """Issue a Signara certificate for a completed course run.

        This triggers the Signara signing workflow to produce a signed certificate PDF
        for the learner. Uses the certificate configuration from the original course
        creation (grade threshold, certificate type) and the run information.

        The flow is:
          1. Render a certificate PDF with the learner's grade and course info
          2. Upload the PDF to Signara as a document
          3. Create a signing request with the issuer/signatory
          4. Sign the request via the public token
          5. Record the outcome in the ledger for idempotency
        """
        import urllib.request
        import urllib.parse
        import json
        import os
        import ssl
        import uuid

        # Read Signara config from environment
        signara_url = os.environ.get('SIGNARA_API_URL', 'https://api.signara.innotel.us')
        signara_key = os.environ.get('SIGNARA_API_KEY', '')

        if not signara_key:
            print("Warning: SIGNARA_API_KEY not set, skipping certificate issuance")
            return {"status": "skipped", "reason": "no_signara_key"}

        # Get learner info from the run/source
        source = started.get("source", {})
        cert_type = cert_config.get("type", "completion")
        grade_threshold = cert_config.get("grade_threshold", 80)
        user_email = source.get("email", "")
        user_name = source.get("user", "")
        course_id = source.get("course", "")

        # Render the certificate PDF with the same renderer the bridge uses, so
        # a course certificate and a conferred degree are one format.
        pdf_path = f"/tmp/atheniq-cert-{run['id']}-{uuid.uuid4().hex[:8]}.pdf"
        try:
            bridge = _load_cert_bridge()
            bridge.render_cert_pdf({
                "org": os.environ.get("CERT_ORG", "Innotel"),
                "course_id": course_id or "AthenIQ course",
                "course_name": course_id or "AthenIQ course",
                "grade": str(grade_threshold),
                "created_date": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                "verify_uuid": str(run.get("id") or ""),
                "learner_name": user_name or user_email or "Learner",
            }, os.environ.get("CERT_SIGNER_NAME", "D. Hunter"),
               os.environ.get("CERT_SIGNER_TITLE", "Founder - Innotel"), pdf_path)
        except Exception as e:
            print(f"Warning: Certificate PDF rendering failed: {e}")
            return {"status": "error", "reason": f"pdf_render_failed: {e}"}

        # Generate title and description for Signara
        learner_display = user_name or user_email or "Learner"
        course_display = course_id or "Unknown Course"
        title = f"{course_display} - Certificate of Completion ({learner_display})"
        message = (f"AthenIQ course completion certificate - {course_id} "
                   f"(grade threshold {grade_threshold}%), auto-issued upon completion.")

        # Step 1: Upload document to Signara
        try:
            # Read the PDF we just created (or the fallback)
            pdf_data = None
            if os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    pdf_data = f.read()

            # Upload to Signara
            boundary = "----atheniq" + uuid.uuid4().hex
            blob = pdf_data or b""
            parts = []
            def field(k, v):
                parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
            field("title", title)
            field("description", message)
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; ")
            parts.append("filename=atheniq-cert.pdf\r\nContent-Type: application/pdf\r\n\r\n".encode())
            parts.append(blob)
            parts.append(f"\r\n--{boundary}--\r\n".encode())
            body = b"".join(parts)

            headers = {"X-API-Key": signara_key}
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            req = urllib.request.Request(signara_url + "/api/v1/documents/upload",
                                         data=body, method="POST", headers=headers)
            ctx = ssl.create_default_context()
            try:
                with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                    doc_result = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"Warning: Signara document upload failed: {e}")
                return {"status": "error", "reason": f"doc_upload_failed: {e}"}

            doc_id = doc_result.get("id")
            if not doc_id:
                return {"status": "error", "reason": "no_document_id"}

            # Step 2: Create signing request
            request_payload = {
                "documentId": doc_id,
                "title": title,
                "message": message,
                "mode": "SEQUENTIAL",
                "sendInvites": False,
                "signers": [{
                    "email": os.environ.get('CERT_SIGNER_EMAIL', 'dhunter@innotel.us'),
                    "name": os.environ.get('CERT_SIGNER_NAME', 'D. Hunter'),
                    "role": "SIGNER",
                    "orderIndex": 0,
                }],
            }
            req2 = urllib.request.Request(signara_url + "/api/v1/signatures/requests",
                                          data=json.dumps(request_payload).encode(),
                                          method="POST",
                                          headers={"X-API-Key": signara_key,
                                                   "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req2, timeout=90, context=ctx) as resp:
                    req_result = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"Warning: Signara request creation failed: {e}")
                return {"status": "error", "reason": f"request_create_failed: {e}"}

            req_id = req_result.get("id")
            if not req_id:
                return {"status": "error", "reason": "no_request_id"}

            # Step 3: Sign the request
            signer_token = None
            signers = req_result.get("signers", []) or []
            if signers:
                signer_token = signers[0].get("token")

            if not signer_token:
                # Fetch the request to get the signer token
                req_get = urllib.request.Request(signara_url + f"/api/v1/signatures/requests/{req_id}",
                                                 method="GET",
                                                 headers={"X-API-Key": signara_key})
                try:
                    with urllib.request.urlopen(req_get, timeout=30, context=ctx) as resp:
                        rq_data = json.loads(resp.read().decode("utf-8"))
                    signers = rq_data.get("signers", []) or []
                    if signers:
                        signer_token = signers[0].get("token")
                except Exception as e:
                    print(f"Warning: Could not fetch signer token: {e}")
                    return {"status": "error", "reason": f"signer_token_fetch_failed: {e}"}

            if not signer_token:
                return {"status": "error", "reason": "no_signer_token"}

            # Step 4: Sign the document
            signature_data = f"COMPLETED_{run['id']}_{grade_threshold}%".encode()
            req3 = urllib.request.Request(signara_url + f"/api/v1/signatures/public/{signer_token}/sign",
                                          data=json.dumps({"type": "TYPED", "signatureData": signature_data.decode()}).encode(),
                                          method="POST",
                                          headers={"X-API-Key": signara_key,
                                                   "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req3, timeout=90, context=ctx) as resp:
                    sign_result = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"Warning: Signara signing failed: {e}")
                # Try to resume as PARTIAL
                return {"status": "partial", "reason": f"sign_failed: {e}"}

            # Step 5: Record outcome - certificate is SIGNED
            print(f"Signara certificate signed successfully for run {run['id']}")
            return {"status": "SIGNED", "doc_id": doc_id, "req_id": req_id}

        except Exception as e:
            print(f"Warning: Signara certificate issuance failed: {e}")
            return {"status": "error", "reason": f"unexpected_error: {e}"}

        finally:
            # Clean up temp PDF if it exists
            try:
                if 'pdf_path' in locals() and os.path.exists(pdf_path):
                    os.remove(pdf_path)
            except:
                pass


    def _rate_limit(self, identity: Identity) -> None:
        """At most N submissions an hour per person, counted before the call.

        A classroom costs minutes of model time, and the fastest way to exhaust
        the gateway is a stuck button. The window is the person's, not the
        process's, so one operator cannot starve another.
        """
        limit = self.config.submits_per_hour
        if limit <= 0:
            return
        now = self.clock()
        key = identity.email or identity.user
        with self._lock:
            recent = self._submissions[key]
            while recent and now - recent[0] > 3600:
                recent.popleft()
            if len(recent) >= limit:
                wait = int(3600 - (now - recent[0]))
                raise Bad(429, f"{limit} classrooms an hour is the limit for one person; "
                               f"try again in {max(wait, 1) // 60 or 1} minutes")
            recent.append(now)

    def record(self, run_id: str) -> dict:
        """Write a finished classroom's id back into the spec it came from.

        This is the step `build-classrooms.py --execute` does for a batch: the
        spec is the record of what the course embeds, so a classroom that only
        exists in OpenMAIC is not attached to anything. Idempotent — recording
        the same run twice leaves the same value — and it refuses to overwrite a
        different classroom a spec already points at.

        Additionally, if the original course creation had certificate options enabled,
        this method will trigger Signara certificate issuance for the completed learner.
        """
        started = self._started.get(run_id)
        if not started or not started.get("spec"):
            raise Bad(400, "this run did not come from a course spec, so there is "
                           "nothing to record — the classroom is at the link")
        run = self.run(run_id)
        stage = run.get("classroomId")
        if run.get("state") != "completed" or not stage:
            raise Bad(409, f"that run is {run.get('state')} and has no classroom yet")
        path = started["spec"]
        if not os.path.isfile(path):
            raise Bad(409, f"the spec it came from is gone: {path}")
        doc = self.builder.read_spec(path)
        for classroom in doc.get("classrooms", []):
            if classroom.get("id") != started["classroom"]:
                continue
            existing = classroom.get("classroom_id")
            if existing and existing != stage:
                raise Bad(409, f"{started['course']}/{started['classroom']} already records "
                               f"{existing}")
            classroom["classroom_id"] = stage
            self.builder.write_spec(path, doc)
            # Trigger certificate issuance if certificate was configured for this course
            cert_config = started.get("cert_config")
            if cert_config and cert_config.get("issue_certificate"):
                try:
                    self._issue_signara_certificate(run, cert_config, started)
                except Exception as e:
                    # Log but don't fail the recording - certificate issuance is best-effort
                    print(f"Warning: Signara certificate issuance failed: {e}")
            return {"ok": True, "course": started["course"],
                    "classroom": started["classroom"], "classroomId": stage, "spec": path}
        raise Bad(404, f"{started['classroom']} is no longer in that spec")

    def _record_and_drop(self, run: dict) -> bool:
        """Record one finished run's classroom, and forget the run if it worked.

        Returns True when the entry should leave the list. A spec that already
        points at a different classroom is the one case kept visible: overwriting
        it would silently repoint a course's embeds, so the run stays with the
        reason attached for somebody to settle.
        """
        run_id = run.get("id")
        started = self._started.get(run_id) or {}
        if started.get("kind") == "program":
            # Program runs are recorded by `/api/programs/<id>/sync`, not here;
            # once finished there is nothing for the classroom list to show.
            if run.get("state") in ("completed", "failed", "ended"):
                with self._lock:
                    self._started.pop(run_id, None)
                    self._finished.pop(run_id, None)
                self._save_state()
                return True
            return False
        if not started.get("spec"):
            return False
        if run.get("state") != "completed" or not run.get("classroomId"):
            return False
        try:
            result = self.record(run_id)
        except Bad as err:
            run["recordError"] = str(err)
            return False
        except Unavailable as err:
            run["recordError"] = str(err)
            return False
        with self._lock:
            self._started.pop(run_id, None)
            self._finished.pop(run_id, None)
            self._recorded.append(result)
        self._save_state()
        return True

    def sweep(self) -> list[dict]:
        """Record finished classrooms without waiting for a page to be open.

        Called on a timer by the service (see `GENERATION_AUTORECORD_SECONDS`), so
        a classroom generated overnight is in its spec before anybody looks. Each
        run is read from OpenMAIC and then decided by the same `_record_and_drop`
        the page's poll uses, so there is one behavior rather than two.
        """
        with self._lock:
            pending = [run_id for run_id, started in self._started.items()
                       if started.get("spec")]
        recorded: list[dict] = []
        for run_id in pending:
            try:
                run = self._finished.get(run_id) or self.run(run_id)
            except (Bad, Unavailable):
                # A run OpenMAIC no longer knows about, or a generator that is down:
                # the next tick asks again. Nothing here is decided by a failure.
                continue
            if self._record_and_drop(dict(run)):
                recorded.append(run)
        # A finished run frees the slot it held, so this is also when the next
        # queued classroom goes out — whether or not this tick recorded anything.
        self.pump()
        return recorded

    # -- the whole course -----------------------------------------------

    def missing(self) -> list[dict]:
        """Every classroom a spec describes that has no classroom yet."""
        out: list[dict] = []
        for course in self.courses():
            for classroom in course["classrooms"]:
                if not classroom["generated"]:
                    out.append({"course": course["slug"], "classroom": classroom["id"],
                                "title": classroom["title"]})
        return out

    def queued(self) -> list[dict]:
        """The classrooms waiting for a slot, in the order they will start."""
        with self._lock:
            return [{key: item[key] for key in ("course", "classroom", "title")
                     if key in item} for item in self._queue]

    def _enqueue(self, identity: Identity | None, items: list[dict]) -> list[dict]:
        """Append classrooms that are neither queued nor already in flight.

        Deduplication is by (course, classroom) against both the queue and the
        console's own run map: the spec does not know about a run until it
        finishes, so without the second half a second click would pay for the
        same classroom twice.
        """
        added: list[dict] = []
        owner = {"user": identity.user if identity else "console",
                 "email": identity.email if identity else "",
                 "groups": list(identity.groups) if identity else []}
        with self._lock:
            known = {(item.get("course"), item.get("classroom")) for item in self._queue}
            known |= {(started.get("course"), started.get("classroom"))
                      for started in self._started.values()
                      if started.get("kind") == "spec"}
            for item in items:
                key = (item["course"], item["classroom"])
                if key in known:
                    continue
                self._queue.append({"course": item["course"], "classroom": item["classroom"],
                                    "title": item.get("title"), "owner": owner})
                known.add(key)
                added.append(item)
        if added:
            self._save_state()
        return added

    def _drop_queued(self, item: dict) -> None:
        """Forget one queued classroom, whether it started or was refused for good."""
        with self._lock:
            try:
                self._queue.remove(item)
            except ValueError:
                pass

    @staticmethod
    def _owner(item: dict) -> Identity:
        """The person who asked for a queued classroom, for the hourly limit.

        A state file written before the queue carried an owner gives the bucket
        `console`: the limit still exists, it is just not attributable.
        """
        owner = item.get("owner") or {}
        return Identity(owner.get("user") or "console", owner.get("email") or "",
                        tuple(owner.get("groups") or ()))

    def pump(self) -> dict:
        """Start queued classrooms until OpenMAIC runs out of room.

        A course has more classrooms than the generator will run at once, so the
        spare ones wait here instead of being reported as skipped and left for
        the operator to click again. Each starts through `submit`, so a classroom
        that came off the queue is recorded into its spec exactly like one
        started by a click.

        A refusal that waiting cannot fix (the spec has since been given a
        classroom) leaves the queue with its reason. One that waiting can fix —
        the active-run cap, the hourly limit, a generator that is down — leaves
        the item at the head and ends the pass, because the next tick asks again
        and hammering a refusal only spends calls.
        """
        started: list[dict] = []
        skipped: list[dict] = []
        blocked = ""
        if not self._pump_lock.acquire(blocking=False):
            return {"started": started, "skipped": skipped, "blocked": "",
                    "remaining": self._queue_depth()}
        try:
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    item = self._queue[0]
                    in_flight = {(started_run.get("course"), started_run.get("classroom"))
                                 for started_run in self._started.values()
                                 if started_run.get("kind") == "spec"}
                label = {key: item[key] for key in ("course", "classroom", "title")
                         if key in item}
                if (item["course"], item["classroom"]) in in_flight:
                    self._drop_queued(item)
                    skipped.append({**label, "reason": "already generating"})
                    continue
                try:
                    answer = self.submit(self._owner(item),
                                         {"course": item["course"],
                                          "classroom": item["classroom"]})
                except Bad as err:
                    if err.status == 429:
                        blocked = str(err)
                        break
                    self._drop_queued(item)
                    skipped.append({**label, "reason": str(err)})
                    continue
                except Unavailable as err:
                    blocked = str(err)
                    break
                self._drop_queued(item)
                started.append({**label, "runId": answer["runId"]})
            remaining = self._queue_depth()
        finally:
            self._pump_lock.release()
        self._save_state()
        return {"started": started, "skipped": skipped, "blocked": blocked,
                "remaining": remaining}

    def _queue_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    def submit_missing(self, identity: Identity) -> dict:
        """Queue every classroom the specs say is missing, then start what fits.

        The batch no longer treats "the generator is full" as a reason to drop
        classrooms: the ones that do not fit wait in the queue and go out as
        runs finish, so one click covers a whole course. A classroom that
        already has a run in flight is never queued again — the spec only learns
        about it when the run finishes, which is the gap this closes.
        """
        with self._lock:
            in_flight = {(started.get("course"), started.get("classroom"))
                         for started in self._started.values() if started.get("kind") == "spec"}
        queue = self.missing()
        skipped = [{**item, "reason": "already generating"} for item in queue
                   if (item["course"], item["classroom"]) in in_flight]
        self._enqueue(identity, [item for item in queue
                                 if (item["course"], item["classroom"]) not in in_flight])
        pumped = self.pump()
        skipped.extend(pumped["skipped"])
        return {"started": pumped["started"], "skipped": skipped,
                "missing": len(queue), "blocked": pumped["blocked"],
                "queued": pumped["remaining"]}

    def retry(self, run_id: str) -> dict:
        status, body = self._call(self._client().retry, run_id)
        if status not in (200, 202):
            raise Bad(409 if status == 409 else 502, f"OpenMAIC refused the retry ({status}): {body}")
        return {"runId": run_id, "ok": True}

    def discard(self, run_id: str) -> dict:
        status, body = self._call(self._client().discard, run_id)
        if status == 409:
            raise Bad(409, "that run already produced a classroom, so it is kept")
        if status not in (200, 204):
            raise Bad(502, f"OpenMAIC refused the discard ({status}): {body}")
        return {"runId": run_id, "ok": True}

    # -- programs ---------------------------------------------------------

    def _program(self, call, *args):
        """Run a ProgramStore method, turning its refusal into this server's Bad."""
        try:
            return call(*args)
        except self._program_error as err:
            raise Bad(err.status, str(err)) from err

    def programs_list(self) -> dict:
        """Every stored program plus the catalog templates to create from."""
        return self._program(lambda: {
            "programs": self.programs.list_programs(),
            "templates": self.programs.template_summaries(),
        })

    def program_get(self, program_id: str) -> dict:
        """One program, with where it stands in the LMS right now.

        `lms` is the answer to the question the page has to ask out loud — is
        this program's curriculum real in the LMS, and how much of it? — so a
        course that was created in the console is never only a line in a JSON
        file without saying so.
        """
        doc = self._program(self.programs.get, program_id)
        doc["lms"] = self.program_lms_status(program_id)
        with self._lock:
            doc["lessonsRun"] = dict(self._lesson_runs.get(program_id) or {}) or None
        return doc

    def program_create(self, identity: Identity, body: dict) -> dict:
        doc = self._program(self.programs.create, identity, body)
        # Publish in the background: a degree is forty courses, and the page must
        # come back with the program rather than block on the CMS imports. A
        # console without the publisher still creates programs; the page says
        # the LMS part is off.
        try:
            self.program_publish(doc["id"])
        except Bad:
            pass
        return doc

    # -- the LMS ----------------------------------------------------------

    def _publisher(self):
        if self.publisher is None:
            raise Bad(503, "publishing to the LMS is off on this console "
                           "(set GENERATION_PUBLISH=1 on a host with docker)")
        return self.publisher

    def program_lms_status(self, program_id: str) -> dict:
        """How many of a program's courses the LMS holds, and the last publish run."""
        with self._lock:
            run = dict(self._publish_runs.get(program_id) or {})
        if self.publisher is None:
            return {"available": False, "reason": "publishing is off", "run": run or None}
        try:
            status = self.publisher.status(program_id)
        except Exception as err:  # noqa: BLE001 — the page must still render
            status = {"available": False, "error": str(err),
                      "published": 0, "courses": 0}
        status["run"] = run or None
        return status

    def program_publish(self, program_id: str) -> dict:
        """Start creating this program's missing courses in the LMS.

        Idempotent and asynchronous: a course already in the LMS is skipped, so
        calling this on every page open is cheap, and the caller gets an answer at
        once while the imports run in the background. Progress is visible through
        `program_lms_status`.
        """
        publisher = self._publisher()
        # The store is the authority on whether this id exists, so a typo is a 404
        # here rather than a background thread that fails silently.
        self._program(self.programs.get, program_id)
        with self._lock:
            if (self._publish_runs.get(program_id) or {}).get("running"):
                return {"running": True, "alreadyRunning": True, "program": program_id}
            self._publish_runs[program_id] = {"running": True, "startedAt": self._stamp()}

        def work() -> None:
            try:
                answer = publisher.publish([program_id], execute=True)
            except Exception as err:  # noqa: BLE001 — reported, not raised in a thread
                answer = {"available": False, "error": str(err),
                          "published": [], "failed": []}
            summary = {
                "running": False,
                "finishedAt": self._stamp(),
                "available": answer.get("available", True),
                "published": len(answer.get("published") or []),
                "skipped": len(answer.get("skipped") or []),
                "failed": (answer.get("failed") or [])[:10],
                "reindexed": answer.get("reindexed"),
                "error": answer.get("error"),
            }
            # A course that was just imported is a shell again: whatever lessons
            # it had were lost with the course, so mark them unbuilt rather than
            # claiming courseware the LMS no longer holds.
            for entry in answer.get("published") or []:
                try:
                    self._program(self.programs.set_lessons, program_id,
                                  entry["code"], {"lessons": 0, "questions": 0})
                except Bad:
                    pass
            with self._lock:
                self._publish_runs[program_id] = summary
            if summary["published"] or summary["failed"]:
                print(f"publish {program_id}: {summary['published']} published, "
                      f"{len(summary['failed'])} failed", file=sys.stderr)

        threading.Thread(target=work, name=f"atheniq-publish-{program_id}",
                         daemon=True).start()
        return {"running": True, "program": program_id}

    def _stamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))

    def program_generate(self, identity: Identity, program_id: str, body: dict) -> dict:
        """Submit one classroom run per course, semester by semester.

        The per-person hourly limit is the same one classrooms use, so a 30-course
        degree stops at the limit cleanly and names what it did not start rather
        than half-submitting in silence.
        """
        def submit(requirement: str) -> str:
            answer = self.submit(identity, {"requirement": requirement})
            run_id = answer["runId"]
            # Tag the run with its program: the program page is where it is
            # recorded, so the classroom console should not keep listing it once
            # it finishes (see `_record_and_drop`).
            with self._lock:
                source = dict(self._started.get(run_id) or {})
                source.update({"kind": "program", "program": program_id})
                self._started[run_id] = source
            self._save_state()
            return run_id
        return self._program(self.programs.generate, program_id, body, submit)

    def program_sync(self, program_id: str) -> dict:
        """Record finished runs into the plan, then build their lessons.

        Recording is the cheap half; writing the lessons into the LMS courses is
        a CMS import per course, so it starts in the background and the page polls
        the program rather than the request holding the socket open.
        """
        answer = self._program(self.programs.sync, program_id, self.run)
        if self.publisher is not None and (answer.get("recorded") or []):
            try:
                answer["lessons"] = self.program_lessons(program_id)
            except Bad as err:
                answer["lessons"] = {"running": False, "error": str(err)}
        return answer

    def program_lessons(self, program_id: str) -> dict:
        """Write every recorded classroom's lessons and exam into its course.

        For each course with a generated classroom and no lessons yet, the shell
        is rebuilt from the classroom's outline and quizzes and imported again
        under the same key. Idempotent: a course already built is left alone, and
        running it again after a regenerate replaces that course's lessons.
        """
        publisher = self._publisher()
        self._program(self.programs.get, program_id)
        with self._lock:
            if (self._lesson_runs.get(program_id) or {}).get("running"):
                return {"running": True, "alreadyRunning": True, "program": program_id}
            self._lesson_runs[program_id] = {"running": True, "startedAt": self._stamp()}

        def work() -> None:
            built, failed = [], []
            try:
                doc = self._program(self.programs.get, program_id)
                for semester in doc.get("semesters") or []:
                    for course in semester.get("courses") or []:
                        stages = [stage for stage in (course.get("classroomIds") or []) if stage]
                        if not stages or (course.get("lessons") or {}).get("count"):
                            continue
                        answer = publisher.attach(program_id, course["code"], stages[0])
                        if answer.get("attached"):
                            self._program(self.programs.set_lessons, program_id,
                                          course["code"], answer)
                            built.append({"code": course["code"],
                                          "lessons": answer["lessons"],
                                          "questions": answer["questions"]})
                        else:
                            failed.append({"code": course["code"],
                                           "error": answer.get("error") or "not attached"})
            except Exception as err:  # noqa: BLE001 — reported, not raised in a thread
                failed.append({"code": "", "error": str(err)})
            summary = {"running": False, "finishedAt": self._stamp(),
                       "built": built, "failed": failed[:10],
                       "lessons": sum(row["lessons"] for row in built),
                       "questions": sum(row["questions"] for row in built)}
            with self._lock:
                self._lesson_runs[program_id] = summary
            if built or failed:
                print(f"lessons {program_id}: {len(built)} course(s) built, "
                      f"{len(failed)} failed", file=sys.stderr)

        threading.Thread(target=work, name=f"atheniq-lessons-{program_id}",
                         daemon=True).start()
        return {"running": True, "program": program_id}

    def program_grades(self, program_id: str) -> dict:
        """Read the LMS's own grade for every learner and course, and record it.

        Completion is a fact about graded work, so the LMS computes it and this
        copies the result into the program record with `source: lms`. A course
        with no grade yet is skipped, not recorded as a zero; a grade that would
        break a prerequisite is reported rather than written.
        """
        publisher = self._publisher()
        self._program(self.programs.get, program_id)
        report = publisher.grades(program_id)
        if not report.get("available"):
            raise Bad(503, report.get("error") or "the LMS is unreachable")
        recorded, skipped = [], []
        for row in report.get("rows") or []:
            if row.get("error"):
                skipped.append({**row, "reason": row["error"]})
                continue
            if row.get("percent") is None:
                skipped.append({**row, "reason": "no grade in the LMS yet"})
                continue
            try:
                self._program(self.programs.record_completion, program_id,
                              row["student"], row["course"], row["percent"],
                              row["passed"], "lms")
            except Bad as err:
                skipped.append({**row, "reason": str(err)})
                continue
            recorded.append(row)
        return {"program": program_id, "available": True,
                "courses": report.get("courses"),
                "students": len(report.get("students") or []),
                "recorded": recorded, "skipped": skipped}

    def program_enroll(self, program_id: str, body: dict) -> dict:
        """Enroll a learner in the program, and in its courses in the LMS.

        The program record is what the registrar's report is built from; the LMS
        enrollment is what puts the course in the learner's *My courses*. Both, in
        that order: a learner who is on the program must not lose that because
        the LMS was briefly unreachable.
        """
        student = str(body.get("student") or "")
        answer = self._program(self.programs.enroll, program_id, student)
        if self.publisher is not None:
            try:
                answer["lms"] = self.publisher.enroll(program_id, student)
            except Exception as err:  # noqa: BLE001 — the local enrollment stands
                answer["lms"] = {"available": False, "error": str(err)}
        return answer

    def program_complete(self, program_id: str, body: dict) -> dict:
        return self._program(self.programs.record_completion, program_id,
                             str(body.get("student") or ""),
                             str(body.get("course") or ""),
                             body.get("score"), body.get("finalPassed"))

    def program_confer(self, program_id: str, body: dict) -> dict:
        """Confer the credential, then sign its document through Signara.

        The conferral is written first and the signature is best-effort: a
        Signara outage must not un-award a degree that every requirement has
        already satisfied. The signature outcome — including `skipped` when no
        key is configured — is attached to the record either way.
        """
        student = str(body.get("student") or "")
        answer = self._program(self.programs.confer, program_id, student)
        if answer.get("conferred") and not answer.get("alreadyConferred"):
            document = self._issue_program_credential(answer["conferred"])
            answer["document"] = document
            answer["conferred"]["document"] = document
            self._program(self.programs.attach_credential_document,
                          program_id, student, document)
        return answer

    def _issue_program_credential(self, conferral: dict) -> dict:
        """Render and sign the degree or certificate PDF via Signara.

        Reuses `cert-bridge.py`'s renderer and client, so a degree and a course
        certificate come out of one pipeline with one signatory and one audit
        trail rather than two that drift apart.
        """
        import tempfile
        import uuid

        key = os.environ.get("SIGNARA_API_KEY", "").strip()
        if not key:
            return {"status": "skipped", "reason": "no_signara_key"}
        try:
            bridge = _load_cert_bridge()
        except Exception as err:  # noqa: BLE001 — a broken bridge cannot block a degree
            return {"status": "error", "reason": f"cert_bridge_unavailable: {err}"}

        learner = conferral.get("student") or "Learner"
        credential = conferral.get("credential") or "Credential"
        gpa = float(conferral.get("gpa") or 0)
        cert = {
            "org": os.environ.get("CERT_ORG", "Innotel"),
            "course_id": conferral.get("id") or credential,
            "course_name": credential,
            "grade": f"GPA {gpa:.2f}",
            "created_date": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "verify_uuid": conferral.get("id") or credential,
            "heading": credential,
            "statement": "has completed every requirement of the program and is awarded",
            "award": (f"{conferral.get('credits')} credits · grade point average "
                      f"{gpa:.2f} · conferred {conferral.get('conferredAt', '')}"),
            "learner_name": learner,
        }
        title = f"{credential} — {learner}"
        message = (f"AthenIQ program conferral — {credential} awarded to {learner} "
                   f"({conferral.get('credits')} credits, GPA {gpa:.2f}).")
        base = os.environ.get("SIGNARA_API_URL", "https://api.signara.innotel.us")
        verify = os.environ.get("SIGNARA_INSECURE", "") not in ("1", "true", "yes")
        signer = os.environ.get("CERT_SIGNER_NAME", "D. Hunter")
        tmp = os.path.join(tempfile.gettempdir(), f"atheniq-credential-{uuid.uuid4().hex[:10]}.pdf")
        try:
            bridge.render_cert_pdf(cert, signer,
                                   os.environ.get("CERT_SIGNER_TITLE", "Founder - Innotel"), tmp)
            client = bridge.Signara(base, key, verify=verify)
            status, document = client.upload_document(title, message, tmp)
            if status not in (200, 201) or not document.get("id"):
                return {"status": "error", "stage": "upload",
                        "reason": f"{status} {document}"[:300]}
            doc_id = document["id"]
            status, request = client.create_request(doc_id, title, message)
            if status not in (200, 201) or not request.get("id"):
                return {"status": "partial", "stage": "request", "documentId": doc_id,
                        "reason": f"{status} {request}"[:300]}
            req_id = request["id"]
            token = next((s.get("token") for s in (request.get("signers") or [])
                          if s.get("token")), None)
            if not token:
                status, fetched = client.get_request(req_id)
                token = next((s.get("token") for s in (fetched.get("signers") or [])
                              if s.get("token")), None)
            if not token:
                return {"status": "partial", "stage": "signer_token", "documentId": doc_id,
                        "requestId": req_id, "reason": "no signer token"}
            status, signed = client.sign(token, signer)
            if status not in (200, 201):
                return {"status": "partial", "stage": "sign", "documentId": doc_id,
                        "requestId": req_id, "reason": f"{status} {signed}"[:300]}
            return {"status": "SIGNED", "documentId": doc_id, "requestId": req_id,
                    "signature": signed.get("status") or "signed"}
        except Exception as err:  # noqa: BLE001 — the conferral stands without a signature
            return {"status": "error", "reason": str(err)[:300]}
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    def program_progress(self, program_id: str, student: str) -> dict:
        return self._program(self.programs.progress, program_id, student)

    def program_update(self, program_id: str, body: dict) -> dict:
        return self._program(self.programs.update, program_id, body)

    def _delete_classrooms(self, stages) -> dict:
        """Delete generated classrooms, and say which could not go.

        The publisher owns the classroom store as well as the LMS — it is the one
        component on this host that can reach OpenMAIC's database — so a console
        with publishing off cannot delete a classroom, and says so rather than
        answering that it did. OpenMAIC's own HTTP delete is owner-scoped and
        removes nothing for a classroom submitted without an owner, which is
        every classroom this console generates; that is why the delete is not
        routed through it.
        """
        wanted = [str(stage).strip() for stage in stages if str(stage).strip()]
        if not wanted:
            return {"deleted": [], "failed": []}
        if self.publisher is None or not hasattr(self.publisher, "delete_classrooms"):
            return {"deleted": [], "failed": [
                {"classroomId": stage,
                 "error": "classroom deletion needs the publisher (GENERATION_PUBLISH=1 "
                          "on a host with docker)"} for stage in dict.fromkeys(wanted)]}
        try:
            return self.publisher.delete_classrooms(list(dict.fromkeys(wanted)))
        except Exception as err:  # noqa: BLE001 — a delete must still answer
            return {"deleted": [], "failed": [
                {"classroomId": stage, "error": str(err)[:300]}
                for stage in dict.fromkeys(wanted)]}

    def _delete_lms_courses(self, codes=None, keys=None) -> dict:
        """Remove courses from the LMS when a publisher is configured."""
        if self.publisher is None:
            return {"available": False, "reason": "publishing is off",
                    "deleted": [], "failed": []}
        try:
            return self.publisher.delete_courses(codes=codes, keys=keys)
        except Exception as err:  # noqa: BLE001 — a delete must still answer
            return {"available": False, "error": str(err),
                    "deleted": [], "failed": []}

    def program_delete(self, program_id: str) -> dict:
        """Delete a program, the courses it taught, and their classrooms.

        The program record goes first, and everything below it goes only if
        nothing else still points at it: two programs can teach the same course
        code, and the LMS key is the course, so deleting the shared course would
        break the program that remains. A course unique to this program takes its
        classes out of OpenMAIC and its course out of the LMS with it.
        """
        self._program(self.programs.get, program_id)  # 404 before anything is removed
        rolled = self._program(self.programs.delete, program_id)
        still_taught = self._program(self.programs.codes_by_program)
        orphans = [course for course in rolled["courses"] if course["code"] not in still_taught]
        kept = sorted({course["code"] for course in rolled["courses"]} & set(still_taught))
        stages = [stage for course in orphans for stage in course["classroomIds"]]
        answer = {
            "ok": True,
            "program": rolled["program"],
            "name": rolled.get("name"),
            "courses": [{"code": course["code"], "title": course["title"],
                         "classroomIds": course["classroomIds"],
                         "lessons": course["lessons"]} for course in orphans],
            "kept": kept,
            "classrooms": self._delete_classrooms(stages),
            "lms": self._delete_lms_courses(codes=[course["code"] for course in orphans]),
            "conferrals": rolled.get("conferrals") or [],
        }
        print(f"delete program {program_id}: {len(orphans)} course(s), "
              f"{len(answer['classrooms']['deleted'])} classroom(s), "
              f"{len(answer['lms'].get('deleted') or [])} LMS course(s)", file=sys.stderr)
        return answer

    def program_remove_course(self, program_id: str, code: str, force: bool = False) -> dict:
        """Take one course out of a program, with the classes it owned.

        The course leaves the curriculum first; the LMS course and its
        classrooms go only if no other program teaches that code.
        """
        answer = self._program(self.programs.remove_course, program_id, code, force)
        code = answer["removed"]["code"]
        still_taught = self._program(self.programs.codes_by_program)
        if code in still_taught:
            return {**answer, "kept": [code],
                    "classrooms": {"deleted": [], "failed": []},
                    "lms": {"available": self.publisher is not None,
                            "reason": "another program still teaches this course",
                            "deleted": [], "failed": []}}
        return {**answer, "kept": [],
                "classrooms": self._delete_classrooms(answer["removed"]["classroomIds"]),
                "lms": self._delete_lms_courses(codes=[code])}

    def templates_list(self) -> dict:
        return {"templates": self._program(self.programs.template_summaries)}

    def template_get(self, slug: str) -> dict:
        return self._program(self.programs.templates.get, slug)

    def template_save(self, body: dict, slug: str | None = None) -> dict:
        return self._program(self.programs.templates.save, body, slug)

    def template_delete(self, slug: str) -> dict:
        return self._program(self.programs.templates.delete, slug)

    def program_regenerate(self, identity: Identity, program_id: str, body: dict) -> dict:
        """Forget the selected classrooms, then queue them again.

        Two calls, in this order, so a failure to submit leaves the plan honest:
        the old ids are gone only because the new run is what will fill them.
        """
        codes = body.get("courses") if isinstance(body.get("courses"), list) else None
        cleared = self._program(self.programs.reset_courses, program_id, codes)
        queued = self.program_generate(identity, program_id, body)
        return {**queued, "cleared": cleared.get("cleared", [])}

    # -- courses and classrooms -------------------------------------------

    def _spec_path(self, slug: str) -> tuple[str, str]:
        root = os.path.join(self.config.root, "courses")
        for found_slug, path in self.builder.spec_paths(root):
            if found_slug == slug:
                return path, root
        raise Bad(404, f"no course {slug!r}")

    # -- library -----------------------------------------------------------

    def library(self) -> dict:
        """The shared shelves a course draws media from.

        A library is one folder under `library/` with a `library.json` beside
        its assets. The console records and creates the shelf; the files in it
        are uploaded through the storage host, so a library that exists and is
        empty says exactly that instead of pretending to hold content.
        """
        root = os.path.join(self.config.root, "library")
        out = []
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                shelf = os.path.join(root, name)
                manifest = os.path.join(shelf, "library.json")
                if not os.path.isfile(manifest):
                    continue
                try:
                    with open(manifest, encoding="utf-8") as fh:
                        doc = json.load(fh)
                except (OSError, ValueError):
                    continue
                assets = [item for item in os.listdir(shelf)
                          if item != "library.json"
                          and not item.startswith(".")]
                out.append({
                    "slug": name,
                    "name": doc.get("name") or name,
                    "description": doc.get("description") or "",
                    "source": doc.get("source") or "",
                    "assets": len(assets),
                    "created": doc.get("created") or "",
                })
        return {"libraries": out}

    def library_create(self, body: dict) -> dict:
        name = str(body.get("name") or "").strip()
        if not name:
            raise Bad(400, "a library needs a name")
        slug = _library_slug(name)
        if not slug:
            raise Bad(400, "that name has no letters or digits to make a folder from")
        root = os.path.join(self.config.root, "library")
        shelf = os.path.join(root, slug)
        manifest = os.path.join(shelf, "library.json")
        if os.path.isfile(manifest):
            raise Bad(409, f"a library called {slug!r} already exists")
        doc = {"name": name, "slug": slug,
               "description": str(body.get("description") or "").strip()[:400],
               "source": str(body.get("source") or "onyx").strip()[:40],
               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))}
        try:
            os.makedirs(shelf, exist_ok=True)
            with open(manifest, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, sort_keys=True)
                fh.write("\n")
        except OSError as err:
            raise Bad(500, f"cannot create {slug!r}: {err}") from err
        return self.library() | {"created": doc}

    def course_delete(self, slug: str) -> dict:
        """Delete a course and the classes generated for it.

        A course is its spec directory plus the classrooms that spec recorded,
        so removing it removes both: a classroom left behind is paid-for
        generation nothing points at, and its LMS course is a shell a learner
        could still enroll in.
        """
        path, _ = self._spec_path(slug)
        doc = self.builder.read_spec(path)
        stages = []
        for classroom in doc.get("classrooms") or []:
            if classroom.get("classroom_id"):
                stages.append(classroom["classroom_id"])
            stages.extend(classroom.get("retired_classroom_ids") or [])
        key = str(doc.get("source_course") or "").strip()
        classrooms = self._delete_classrooms(stages)
        lms = self._delete_lms_courses(keys=[key]) if key else \
            {"available": self.publisher is not None, "deleted": [], "failed": [],
             "reason": "the spec names no LMS course"}
        # The spec sits at `<course>/openmaic/classrooms.json`, so the course is
        # two levels up: removing the spec's directory left an empty course
        # folder behind, which the catalog then listed as a course with no spec.
        course_dir = os.path.dirname(os.path.dirname(path))
        try:
            shutil.rmtree(course_dir)
        except OSError as err:
            raise Bad(500, f"cannot delete course {slug!r}: {err}") from err
        print(f"delete course {slug}: {len(stages)} classroom(s), {key or 'no LMS course'}",
              file=sys.stderr)
        return {"ok": True, "course": slug, "lmsCourse": key or None,
                "classrooms": classrooms, "lms": lms}

    def course_regenerate(self, identity: Identity, slug: str) -> dict:
        """Submit every classroom in one course that has none yet."""
        root = os.path.join(self.config.root, "courses")
        for found_slug, path in self.builder.spec_paths(root):
            if found_slug != slug:
                continue
            doc = self.builder.read_spec(path)
            started, skipped = [], []
            for classroom in doc.get("classrooms") or []:
                if classroom.get("classroom_id"):
                    continue
                try:
                    answer = self.submit(identity, {"course": slug,
                                                   "classroom": classroom["id"]})
                except Bad as err:
                    skipped.append({"id": classroom["id"], "reason": str(err)})
                    if err.status == 429:
                        break
                    continue
                started.append({"id": classroom["id"], "runId": answer["runId"]})
            return {"course": slug, "started": started, "skipped": skipped}
        raise Bad(404, f"no course {slug!r}")

    def classroom_retire(self, slug: str, classroom_id: str) -> dict:
        """Unhook one classroom from its spec, keeping the record of it.

        The id goes into `retired_classroom_ids` rather than being erased: a
        classroom that existed is a thing that happened, and its link may be in
        a course email or a student's history.
        """
        path, _ = self._spec_path(slug)
        doc = self.builder.read_spec(path)
        for classroom in doc.get("classrooms") or []:
            if classroom.get("id") != classroom_id:
                continue
            stage = classroom.get("classroom_id")
            if stage:
                classroom.setdefault("retired_classroom_ids", []).append(stage)
            classroom["classroom_id"] = None
            self.builder.write_spec(path, doc)
            return {"ok": True, "course": slug, "classroom": classroom_id,
                    "retired": stage, "spec": path}
        raise Bad(404, f"no classroom {classroom_id!r} in {slug!r}")

    def classroom_regenerate(self, identity: Identity, slug: str,
                             classroom_id: str) -> dict:
        """Retire the current classroom and start a fresh run for the brief."""
        self.classroom_retire(slug, classroom_id)
        answer = self.submit(identity, {"course": slug, "classroom": classroom_id})
        return {**answer, "course": slug, "classroom": classroom_id,
                "next": "the new classroom replaces the retired one when recorded"}


class Bad(Exception):
    """A request the caller can fix: status is the answer's status code."""

    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def _first_header(headers, names) -> str:
    """The first of `names` that carries a value; empty string if none does."""
    for name in names:
        value = (headers.get(name) or "").strip()
        if value:
            return value
    return ""


def identity_from_headers(headers, config) -> Identity | None:
    """The caller as the SSO proxy described them, or None."""
    user = _first_header(headers, USER_HEADERS[0])
    email = _first_header(headers, USER_HEADERS[1])
    groups = tuple(g.strip() for g in _first_header(headers, GROUPS_HEADERS).split(",")
                   if g.strip())
    if user or email:
        return Identity(user or email, email, groups)
    if config.trust_local:
        return Identity("local", "", ("atheniq-admins",))
    return None


def same_origin(headers) -> bool:
    """Whether to let a mutating request through.

    Two independent checks, either of which is enough to refuse: an `Origin`
    that is not this host, and a missing console header. The second is what
    actually stops CSRF — a cross-origin form cannot add a header — while the
    first also catches a page served from the wrong name.
    """
    if (headers.get(CONSOLE_HEADER) or "") != "1":
        return False
    origin = headers.get("Origin")
    if not origin:
        return True
    host = (headers.get("Host") or "").split(",")[0].strip().lower()
    return urllib.parse.urlsplit(origin).netloc.lower() == host


class Handler(BaseHTTPRequestHandler):
    server_version = "AthenIQGeneration/1"
    console: Console = None  # set by make_server()

    # -- plumbing --------------------------------------------------------

    def log_message(self, fmt, *args):  # quieter than the default access log
        pass

    def _send(self, status, body=b"", content_type="application/json; charset=utf-8",
              extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json")
                         else "no-cache")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self._send(status, body)

    def _error(self, status, message):
        self._json(status, {"error": message})

    def _identity(self):
        ident = identity_from_headers(self.headers, self.console.config)
        if ident is None:
            self._error(401, "sign in first — this console is behind the atheniq SSO")
            return None
        if not ident.holds(self.console.config.allowed_groups):
            self._error(403, "this console generates classrooms for staff "
                             f"({' / '.join(self.console.config.allowed_groups)})")
            return None
        return ident

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise Bad(413, "that request is too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise Bad(400, "expected JSON")

    # -- routes ----------------------------------------------------------

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/healthz":
            # Unauthenticated on purpose: it says the process is up and nothing
            # else, so a container healthcheck does not need an identity.
            return self._json(200, {"ok": True})
        if path.startswith("/api/"):
            return self._api_get(path)
        return self._static(path)

    def do_HEAD(self):
        if urllib.parse.urlsplit(self.path).path.startswith("/api/"):
            return self._error(405, "HEAD is not supported on the API")
        return self._static(urllib.parse.urlsplit(self.path).path)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if not same_origin(self.headers):
            return self._error(403, "cross-site request refused")
        ident = self._identity()
        if ident is None:
            return
        try:
            body = self._body()
            if path == "/api/generate":
                return self._json(202, self.console.submit(ident, body))
            if path == "/api/generate-missing":
                # 202 whether or not everything started: the answer says what ran
                # and what did not, and a partial batch is not a failed request.
                return self._json(202, self.console.submit_missing(ident))
            if path.startswith("/api/runs/") and path.endswith("/retry"):
                return self._json(200, self.console.retry(path[len("/api/runs/"):-len("/retry")]))
            if path.startswith("/api/runs/") and path.endswith("/record"):
                return self._json(200, self.console.record(path[len("/api/runs/"):-len("/record")]))
            if path == "/api/templates":
                return self._json(201, self.console.template_save(body))
            if path == "/api/library":
                return self._json(201, self.console.library_create(body))
            if path == "/api/create-course":
                return self._json(202, self.console.create_course(ident, body))
            if path == "/api/programs":
                return self._json(201, self.console.program_create(ident, body))
            if path.startswith("/api/programs/"):
                program_id, _, action = path[len("/api/programs/"):].partition("/")
                if action == "generate":
                    return self._json(202, self.console.program_generate(ident, program_id, body))
                if action == "sync":
                    return self._json(200, self.console.program_sync(program_id))
                if action == "lessons":
                    return self._json(202, self.console.program_lessons(program_id))
                if action == "grades":
                    return self._json(200, self.console.program_grades(program_id))
                if action == "enroll":
                    return self._json(201, self.console.program_enroll(program_id, body))
                if action == "publish":
                    return self._json(202, self.console.program_publish(program_id))
                if action == "complete":
                    return self._json(200, self.console.program_complete(program_id, body))
                if action == "confer":
                    return self._json(201, self.console.program_confer(program_id, body))
                if action == "regenerate":
                    return self._json(202, self.console.program_regenerate(ident, program_id, body))
                return self._error(404, "no such program action")
            if path.startswith("/api/courses/") and "/classrooms/" in path \
                    and path.endswith("/regenerate"):
                rest = path[len("/api/courses/"):-len("/regenerate")]
                slug, _, classroom_id = rest.partition("/classrooms/")
                return self._json(202, self.console.classroom_regenerate(
                    ident, slug, classroom_id))
            if path.startswith("/api/courses/") and path.endswith("/regenerate"):
                slug = path[len("/api/courses/"):-len("/regenerate")]
                return self._json(202, self.console.course_regenerate(ident, slug))
            return self._error(404, "no such endpoint")
        except Bad as err:
            return self._error(err.status, str(err))
        except Unavailable as err:
            return self._error(502, str(err))
        except Exception as err:  # a handler answers; an uncaught bug drops the socket (a 502)
            traceback.print_exc()
            return self._error(500, f"the console failed while handling this request: {err}")

    def do_DELETE(self):
        path = urllib.parse.urlsplit(self.path).path
        if not same_origin(self.headers):
            return self._error(403, "cross-site request refused")
        if self._identity() is None:
            return
        try:
            if path.startswith("/api/runs/"):
                return self._json(200, self.console.discard(path[len("/api/runs/"):]))
            if path.startswith("/api/templates/"):
                return self._json(200, self.console.template_delete(
                    path[len("/api/templates/"):].strip("/")))
            if path.startswith("/api/programs/") and "/courses/" in path:
                rest = path[len("/api/programs/"):]
                program_id, _, code = rest.partition("/courses/")
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                force = (query.get("force") or [""])[0].lower() in ("1", "true", "yes")
                return self._json(200, self.console.program_remove_course(
                    program_id, code.strip("/"), force))
            if path.startswith("/api/programs/"):
                return self._json(200, self.console.program_delete(
                    path[len("/api/programs/"):].strip("/")))
            if path.startswith("/api/courses/") and "/classrooms/" in path:
                rest = path[len("/api/courses/"):]
                slug, _, classroom_id = rest.partition("/classrooms/")
                return self._json(200, self.console.classroom_retire(
                    slug, classroom_id.strip("/")))
            if path.startswith("/api/courses/"):
                return self._json(200, self.console.course_delete(
                    path[len("/api/courses/"):].strip("/")))
            return self._error(404, "no such endpoint")
        except Bad as err:
            return self._error(err.status, str(err))
        except Unavailable as err:
            return self._error(502, str(err))
        except Exception as err:  # a handler answers; an uncaught bug drops the socket
            # This is how a delete answered with a proxy's 502 instead of a
            # message: an AttributeError escaped here and the connection closed
            # with nothing to read. A 500 says what happened.
            traceback.print_exc()
            return self._error(500, f"the console failed while handling this request: {err}")

    def do_PUT(self):
        """Replace one catalog template."""
        path = urllib.parse.urlsplit(self.path).path
        if not same_origin(self.headers):
            return self._error(403, "cross-site request refused")
        if self._identity() is None:
            return
        try:
            body = self._body()
            if path.startswith("/api/templates/"):
                return self._json(200, self.console.template_save(
                    body, path[len("/api/templates/"):].strip("/")))
            return self._error(404, "no such endpoint")
        except Bad as err:
            return self._error(err.status, str(err))
        except Unavailable as err:
            return self._error(502, str(err))
        except Exception as err:  # a handler answers; an uncaught bug drops the socket
            traceback.print_exc()
            return self._error(500, f"the console failed while handling this request: {err}")

    def do_PATCH(self):
        """Edit metadata in place: a program's name, credential, term or GPAs."""
        path = urllib.parse.urlsplit(self.path).path
        if not same_origin(self.headers):
            return self._error(403, "cross-site request refused")
        if self._identity() is None:
            return
        try:
            body = self._body()
            if path.startswith("/api/programs/"):
                return self._json(200, self.console.program_update(
                    path[len("/api/programs/"):].strip("/"), body))
            return self._error(404, "no such endpoint")
        except Bad as err:
            return self._error(err.status, str(err))
        except Unavailable as err:
            return self._error(502, str(err))
        except Exception as err:  # a handler answers; an uncaught bug drops the socket
            traceback.print_exc()
            return self._error(500, f"the console failed while handling this request: {err}")

    def _api_get(self, path):
        ident = self._identity()
        if ident is None:
            return
        try:
            if path == "/api/me":
                view = ident.as_view(self.console.config.allowed_groups)
                view["classroomHost"] = self.console.config.classroom_host
                return self._json(200, view)
            if path == "/api/health":
                return self._json(200, self.console.health())
            if path == "/api/courses":
                return self._json(200, {
                    "courses": self.console.courses(),
                    "maxRequirement": self.console.config.max_requirement,
                })
            if path == "/api/library":
                return self._json(200, self.console.library())
            if path == "/api/programs":
                return self._json(200, self.console.programs_list())
            if path == "/api/templates":
                return self._json(200, self.console.templates_list())
            if path.startswith("/api/templates/"):
                return self._json(200, self.console.template_get(
                    path[len("/api/templates/"):].strip("/")))
            if path.startswith("/api/programs/"):
                program_id, _, action = path[len("/api/programs/"):].partition("/")
                if not action:
                    return self._json(200, self.console.program_get(program_id))
                if action == "progress":
                    query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                    student = (query.get("student") or [ident.email or ident.user])[0]
                    return self._json(200, self.console.program_progress(program_id, student))
                return self._error(404, "no such program view")
            if path == "/api/runs":
                # The page polls this while a batch runs, which makes it the
                # second driver of the queue (the sweeper is the first): a
                # classroom that did not fit starts as soon as a run ends.
                try:
                    self.console.pump()
                except Exception:  # noqa: BLE001 — a queue never breaks the list
                    pass
                return self._json(200, {"runs": self.console.runs(),
                                        "recorded": self.console.recent_recordings(),
                                        "queued": self.console.queued()})
            if path.startswith("/api/runs/"):
                return self._json(200, self.console.run(path[len("/api/runs/"):]))
            if path == "/api/create-course" or path.startswith("/api/create-course/"):
                run_id = path[len("/api/create-course/"):] or None
                if run_id:
                    return self._json(200, self.console.run(run_id))
                # Return run list or status overview
                runs = self.console.runs()
                return self._json(200, {"runs": runs, "type": "create-course"})
            return self._error(404, "no such endpoint")
        except Bad as err:
            return self._error(err.status, str(err))
        except Unavailable as err:
            return self._error(502, str(err))

    def _static(self, path):
        web_root = os.path.join(self.console.config.root, "web", "generate")
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        # Joined, normalized, then re-checked: `..` in a URL never reaches disk.
        target = os.path.normpath(os.path.join(web_root, rel))
        if os.path.commonpath([os.path.abspath(target), os.path.abspath(web_root)]) != os.path.abspath(web_root):
            return self._error(404, "not found")
        if not os.path.isfile(target):
            return self._error(404, "not found")
        with open(target, "rb") as fh:
            body = fh.read()
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        extra = {}
        if os.path.basename(target) == "index.html":
            # The page has no inline script or remote fonts: a strict policy is
            # affordable, and it keeps a future edit from adding one silently.
            extra["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                "form-action 'self'; base-uri 'none'")
        self._send(200, body, ctype, extra)


def start_recorder(console: Console, interval: int):
    """Record finished classrooms on a timer, for as long as the process lives.

    A daemon thread rather than a second process: the work is one HTTP read per
    tracked run every `interval` seconds, and the console is already the only
    thing that knows which spec each run came from. A failed tick is swallowed —
    the next one asks again — because a generator that is briefly down must not
    take the recorder with it.
    """
    if interval <= 0:
        return None

    def loop() -> None:
        while True:
            time.sleep(interval)
            try:
                console.sweep()
            except Exception:  # noqa: BLE001 — a recorder never dies of a bad tick
                continue

    thread = threading.Thread(target=loop, name="atheniq-record", daemon=True)
    thread.start()
    return thread


def make_server(config, builder=None):
    console = Console(config, builder=builder)
    handler = type("BoundHandler", (Handler,), {"console": console})
    start_recorder(console, config.autorecord_seconds)
    return ThreadingHTTPServer((config.bind, config.port), handler), console


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", help="address to listen on (GENERATION_BIND)")
    ap.add_argument("--port", type=int, help="port to listen on (GENERATION_PORT)")
    ap.add_argument("--base-url", help="OpenMAIC base URL (OPENMAIC_BASE_URL)")
    ap.add_argument("--trust-local", action="store_true",
                    help="accept requests without SSO headers (local use only)")
    args = ap.parse_args()

    config = Config.from_env()
    if args.bind:
        config.bind = args.bind
    if args.port:
        config.port = args.port
    if args.base_url:
        config.base_url = args.base_url
    if args.trust_local:
        config.trust_local = True

    server, _ = make_server(config)
    print(f"generation console on http://{config.bind}:{config.port} "
          f"-> OpenMAIC {config.base_url}", flush=True)
    if config.trust_local:
        print("  trusting local requests (no SSO headers required)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
