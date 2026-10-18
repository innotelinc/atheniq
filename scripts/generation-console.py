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
    GET    /api/runs               the runs OpenMAIC still holds (paused or generating)
    GET    /api/runs/<id>          one run, with its step, error and progress
    POST   /api/generate           submit a classroom — from a spec, or a free-form brief
    POST   /api/runs/<id>/retry    resume a paused run
    POST   /api/runs/<id>/record   write a finished classroom's id back into its spec
    DELETE /api/runs/<id>          discard a paused run that has no classroom

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
    GENERATION_SUBMITS_PER_HOUR submissions one person may start per hour (default 10)
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
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILDER_PATH = os.path.join(REPO, "scripts", "build-classrooms.py")

#: A brief longer than this is refused by the gateway ("Prompt too long (max
#: 6000 characters)"), so the console refuses it first with a message that says
#: what to cut instead of a 502 an hour later.
DEFAULT_MAX_REQUIREMENT = 6000

#: The headers oauth2-proxy sets when `--set-xauthrequest` and
#: `--pass-user-headers` are on. Anything else is treated as unauthenticated.
USER_HEADERS = ("X-Auth-Request-User", "X-Auth-Request-Email")
GROUPS_HEADER = "X-Auth-Request-Groups"

#: A mutating request must carry this header. A browser form cannot set it
#: cross-origin without a CORS preflight (which this server never grants), so it
#: is the CSRF guard: the console's own JS always sends it, a hostile page cannot.
CONSOLE_HEADER = "X-Atheniq-Console"

MAX_BODY = 64 * 1024


def _load_builder():
    """The batch tool, imported for its brief-building and API client.

    One source of truth for what a spec's brief says and how OpenMAIC is
    called: if `build-classrooms.py` learns a new field, the console submits it
    too. The module is standalone (its `main()` is behind a guard).
    """
    spec = importlib.util.spec_from_file_location("atheniq_build_classrooms", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    """The console's behaviour, separated from HTTP so tests can drive it.

    Every method returns plain data and raises `Bad` for a request the operator
    should fix (400/403/409) or `Unavailable` for anything OpenMAIC's side did
    (502), so the HTTP layer is only about status codes and shapes.
    """

    def __init__(self, config, builder=None, clock=time.time):
        self.config = config
        self.builder = builder or _load_builder()
        self.clock = clock
        self._submissions = collections.defaultdict(collections.deque)
        #: run id -> where it came from (`course`/`classroom`/spec path, or free).
        #: The console is where the run was started, so it is the only place
        #: that can write the result back to the right line of the right spec.
        self._started = collections.OrderedDict()
        #: runs that left the active list, kept so the page can still show how
        #: they ended (a completed run is not "active" and would vanish).
        self._finished = {}
        self._lock = threading.Lock()

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
        return runs

    def run(self, run_id: str) -> dict:
        status, body = self._call(self._client().run, run_id)
        if status != 200:
            raise Bad(404, f"no run {run_id!r}")
        return self._run_view(body.get("run", body))

    def _run_view(self, run: dict) -> dict:
        error = run.get("error") or {}
        progress = run.get("progress") or {}
        return {
            "id": run.get("id"),
            "state": run.get("state"),
            "step": run.get("step"),
            "progress": {"done": progress.get("completed"), "total": progress.get("total")},
            "error": {"code": error.get("errorCode"), "status": error.get("statusCode"),
                      "message": error.get("message")} if error else None,
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
        return {"runId": run_id, "source": source, "characters": len(requirement)}

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

    def _check_length(self, requirement: str) -> str:
        limit = self.config.max_requirement
        if len(requirement) > limit:
            raise Bad(400, f"the brief is {len(requirement)} characters; the gateway "
                           f"refuses anything over {limit}")
        return requirement

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
            return {"ok": True, "course": started["course"],
                    "classroom": started["classroom"], "classroomId": stage, "spec": path}
        raise Bad(404, f"{started['classroom']} is no longer in that spec")

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


class Bad(Exception):
    """A request the caller can fix: status is the answer's status code."""

    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def identity_from_headers(headers, config) -> Identity | None:
    """The caller as the SSO proxy described them, or None."""
    user = (headers.get(USER_HEADERS[0]) or "").strip()
    email = (headers.get(USER_HEADERS[1]) or "").strip()
    groups = tuple(g.strip() for g in (headers.get(GROUPS_HEADER) or "").split(",") if g.strip())
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
            if path.startswith("/api/runs/") and path.endswith("/retry"):
                return self._json(200, self.console.retry(path[len("/api/runs/"):-len("/retry")]))
            if path.startswith("/api/runs/") and path.endswith("/record"):
                return self._json(200, self.console.record(path[len("/api/runs/"):-len("/record")]))
            return self._error(404, "no such endpoint")
        except Bad as err:
            return self._error(err.status, str(err))
        except Unavailable as err:
            return self._error(502, str(err))

    def do_DELETE(self):
        path = urllib.parse.urlsplit(self.path).path
        if not same_origin(self.headers):
            return self._error(403, "cross-site request refused")
        if self._identity() is None:
            return
        try:
            if path.startswith("/api/runs/"):
                return self._json(200, self.console.discard(path[len("/api/runs/"):]))
            return self._error(404, "no such endpoint")
        except Bad as err:
            return self._error(err.status, str(err))
        except Unavailable as err:
            return self._error(502, str(err))

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
            if path == "/api/runs":
                return self._json(200, {"runs": self.console.runs()})
            if path.startswith("/api/runs/"):
                return self._json(200, self.console.run(path[len("/api/runs/"):]))
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
        # Joined, normalised, then re-checked: `..` in a URL never reaches disk.
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


def make_server(config, builder=None):
    console = Console(config, builder=builder)
    handler = type("BoundHandler", (Handler,), {"console": console})
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
