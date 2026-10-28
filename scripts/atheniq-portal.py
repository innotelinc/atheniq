#!/usr/bin/env python3
"""AthenIQ — one app, two views: what a learner sees, and what staff run.

WHY THIS EXISTS
---------------
The catalog was two applications that disagreed. The staff console
(`ai.lms.innotel.us`) listed the four programs correctly but only the fourteen
built course specs under Courses, so the 79 courses that exist inside the
Business, Criminal Justice and Nursing plans looked like they did not exist. The
learner portal (`lms.innotel.us`) listed every program *and* the plan-only
courses, but on a second design of its own (`web/student/`), so the same catalog
looked like two different products — and staff had to keep two pages in their
head to answer "does this course exist yet?".

This is the app that replaces both front ends with one: one page, one design,
two views.

    learner   public and read-only: every program, every course the catalog
              carries (built, or planned inside a program and not built yet),
              and the way into the LMS. No identities, no grades, no actions.
    admin     the same catalog, behind the estate's SSO, with the generation
              queue: what has no classroom yet, what is running, what is
              paused and why, and the retry that resumes it.

One process serves either view (or both) and the view is decided per request:
a request that carries an allowed SSO identity sees the admin view, everyone
else sees the learner view. So the same deployment answers both names —
`lms.innotel.us` for learners, `ai.lms.innotel.us` for staff — and there is no
second copy of the page to drift.

WHAT IT DOES NOT OWN
--------------------
Generation itself. The console process is the single owner of the run queue, the
recorder and the LMS publisher; this app reads its API and forwards the two
actions it exposes (`submit every missing classroom`, `retry this run`) with the
caller's own identity. Serving the queue from here too would mean two processes
each believing they own it, which is how a classroom gets generated twice.

    PORTAL_ROOT=/home/tutor/atheniq-generation \
    python3 scripts/atheniq-portal.py --bind 192.168.1.59 --port 8092

Exit codes: 0 = stopped by a signal, 2 = it could not start (bad config/port).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The console, whose API is the one source of the catalog and of the run queue.
CONSOLE = os.path.join(REPO, "scripts", "generation-console.py")

#: The identity headers oauth2-proxy sets upstream (`--pass-user-headers`) and the
#: `X-Auth-Request-*` names an nginx `auth_request` sets. Both are accepted, the
#: explicit ones first; the console reads them the same way, so one rule.
USER_HEADERS = (("X-Auth-Request-User", "X-Forwarded-User"),
                ("X-Auth-Request-Email", "X-Forwarded-Email"))
GROUPS_HEADERS = ("X-Auth-Request-Groups", "X-Forwarded-Groups")

#: A mutating request must carry this, exactly as the console requires: a
#: browser form cannot set it cross-origin without a preflight this server never
#: grants.
PORTAL_HEADER = "X-Atheniq-Portal"

#: Reads the app is allowed to make on the console, and the actions it may pass on.
READ_PATHS = ("/api/programs", "/api/courses", "/api/runs", "/api/health", "/api/me")
ACTION_PATHS = ("/api/generate-missing",)

MAX_BODY = 16 * 1024


def _module():
    """The console module, imported for its identity reader and its word types."""
    name = "atheniq_generation_console"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, CONSOLE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:  # pragma: no cover — a broken import must not be cached
        sys.modules.pop(name, None)
        raise
    return module


class Config:
    """Where the app listens, what it reads, and who counts as staff."""

    def __init__(self, root: str, bind: str, port: int, view: str,
                 console_url: str, admin_groups: tuple[str, ...],
                 lms_url: str, classroom_url: str) -> None:
        self.root = root
        self.bind = bind
        self.port = port
        self.view = view
        self.console_url = console_url.rstrip("/")
        self.admin_groups = admin_groups
        self.lms_url = lms_url.rstrip("/")
        self.classroom_url = classroom_url.rstrip("/")

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env
        root = env.get("PORTAL_ROOT") or REPO
        groups = tuple(name.strip() for name in
                       (env.get("PORTAL_ADMIN_GROUPS") or "atheniq-admins").split(",")
                       if name.strip())
        return cls(
            root=root,
            bind=env.get("PORTAL_BIND") or "127.0.0.1",
            port=int(env.get("PORTAL_PORT") or 8092),
            view=(env.get("PORTAL_VIEW") or "learner").strip().lower(),
            console_url=env.get("PORTAL_CONSOLE") or "http://127.0.0.1:8090",
            admin_groups=groups,
            lms_url=env.get("PORTAL_LMS") or "https://atheniq.courses",
            classroom_url=env.get("PORTAL_CLASSROOM") or "https://classroom.innotel.us",
        )


# -- reading the console ------------------------------------------------------

class ConsoleError(RuntimeError):
    """The console did not answer the question, and why."""


def console_get(config: Config, path: str, identity: tuple[dict[str, str]] | None = None):
    """One read of the console's API, as a trusted local caller.

    The console answers only a signed-in caller, and the learner view is public,
    so this app reads on its own behalf from loopback: it asks for the catalog
    and nothing else, and only ever returns the learner-safe projection of it.
    """
    headers = {"Accept": "application/json"}
    if identity:
        for key, value in identity:
            headers[key] = value
    else:
        headers["X-Auth-Request-User"] = "atheniq-portal"
        headers["X-Auth-Request-Email"] = "portal@innotel.us"
        headers["X-Auth-Request-Groups"] = ",".join(config.admin_groups)
    request = urllib.request.Request(config.console_url + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise ConsoleError(f"the console answered {error.code} for {path}: "
                           f"{(error.read() or b'').decode('utf-8', 'replace')[:200]}") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ConsoleError(f"cannot reach the console at {config.console_url}: {error}") from error


def console_post(config: Config, path: str, identity: tuple[dict[str, str]], body=None):
    """One action handed to the console, carrying the caller's own identity."""
    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "X-Atheniq-Console": "1", "Origin": config.console_url}
    for key, value in identity:
        headers[key] = value
    data = json.dumps(body if body is not None else {}).encode()
    request = urllib.request.Request(config.console_url + path, data=data, headers=headers,
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        detail = (error.read() or b"").decode("utf-8", "replace")
        try:
            message = json.loads(detail).get("error") or detail
        except ValueError:
            message = detail
        raise ConsoleError(str(message)[:300]) from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ConsoleError(f"cannot reach the console at {config.console_url}: {error}") from error


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _catalog_names(config: Config) -> dict[str, str]:
    """Code -> the name the catalog sells it under (`config/course-prices.json`).

    A course spec does not carry a title — it carries the brief the generator
    read — so the built courses would read as their own code on a learner's
    page. The price sheet is the catalog's own list of names, and it is the same
    file the card renderer prints them from.
    """
    names = {}
    for key, row in (_read_json(os.path.join(config.root, "config", "course-prices.json"))
                     .get("courses") or {}).items():
        parts = str(key).split("+")
        if len(parts) != 3:
            continue
        code = parts[1].strip().upper()
        name = str((row or {}).get("name") or "").strip()
        if code and name:
            names[code] = name
    return names


def _track_of(config: Config) -> dict[str, str]:
    """Code -> the workforce track that sells it, for courses no plan carries."""
    out = {}
    for track in (_read_json(os.path.join(config.root, "config", "workforce-tracks.json"))
                  .get("tracks") or []):
        title = str(track.get("title") or "")
        for key in track.get("courses") or []:
            parts = str(key).split("+")
            if len(parts) == 3 and title:
                out.setdefault(parts[1].strip().upper(), title)
    return out


def _headline(name: str, code: str) -> str:
    """`CODE — Title` reads as `Title`: the code is its own column."""
    text = str(name or "").strip()
    if code and text.upper().startswith(code.upper()):
        text = text[len(code):].lstrip(" -\u2013\u2014:")
    return text or code


def catalog(config: Config) -> dict:
    """The one catalog both views show: programs, then every course they carry.

    A course is `built` when a spec exists (so it has classrooms and an LMS
    run); `planned` when only a program plan names it. Both are courses, and the
    view says which — that difference is the whole reason a program page and a
    course list used to disagree.
    """
    programs = console_get(config, "/api/programs")
    courses = console_get(config, "/api/courses")
    names = _catalog_names(config)
    tracks = _track_of(config)
    owners: dict[str, str] = {}
    cards = []
    for card in programs.get("programs") or []:
        identifier = card.get("id")
        detail = {}
        if identifier:
            try:
                detail = console_get(config, "/api/programs/" + urllib.parse.quote(identifier))
            except ConsoleError:
                detail = {}  # one unreadable program must not empty the catalog
        semesters = (detail.get("plan") or {}).get("semesters") \
            or detail.get("semesters") or []
        for semester in semesters:
            for course in semester.get("courses") or []:
                code = str(course.get("code") or "").strip().upper()
                if code:
                    owners.setdefault(code, card.get("name") or "")
        cards.append({
            "id": identifier,
            "name": card.get("name"),
            "credential": card.get("credential"),
            "credentialKind": card.get("credentialKind"),
            "level": card.get("level"),
            "totalCredits": card.get("totalCredits"),
            "description": card.get("description"),
            "startTerm": detail.get("startTerm") or card.get("startTerm"),
            "semesters": card.get("semesters") or 0,
            "courses": card.get("courses") or 0,
            "generated": card.get("generated") or 0,
            "lessons": card.get("built") or card.get("lessons") or 0,
            "enrolled": card.get("enrolled") or 0,
        })

    rows = []
    for course in courses.get("courses") or []:
        code = str(course.get("code") or "").upper()
        key = course.get("course") or ""
        planned = bool(course.get("planned"))
        title = str(course.get("title") or "").strip()
        if not title or title.upper() == code:
            title = _headline(names.get(code, ""), code)
        if isinstance(course.get("program"), dict):
            owner = course["program"].get("name") or ""
        else:
            owner = owners.get(code) or course.get("program") or tracks.get(code, "")
        rows.append({
            "code": code,
            "title": title,
            "program": owner,
            "slug": course.get("slug"),
            "key": key if key.startswith("course-v1:") else "",
            "planned": planned,
            "generated": course.get("generated") or 0,
            "total": course.get("total") or 0,
            "url": (f"{config.lms_url}/courses/{key}/about"
                    if key.startswith("course-v1:") else ""),
        })
    rows.sort(key=lambda row: (row["planned"], row["code"]))
    return {"programs": cards, "courses": rows,
            "lms": config.lms_url, "classroom": config.classroom_url}


def runs(config: Config, identity) -> dict:
    """The queue as the console sees it, with the parts a staff page needs."""
    payload = console_get(config, "/api/runs", identity)
    rows = []
    for run in payload.get("runs") or []:
        error = run.get("error") or {}
        rows.append({
            "id": run.get("id"),
            "state": run.get("state"),
            "step": run.get("step") or "",
            "course": run.get("course") or "",
            "classroom": run.get("classroom") or "",
            "title": run.get("title") or "",
            "error": error.get("message") if isinstance(error, dict) else str(error or ""),
        })
    return {"runs": rows, "queued": payload.get("queued") or [],
            "recorded": len(payload.get("recorded") or [])}


# -- identity -----------------------------------------------------------------

def identity_of(config: Config, headers) -> tuple[dict[str, str], object] | tuple[None, None]:
    """(headers to forward, the console's identity view) or (None, None).

    Gating is the console's own rule rather than a second copy of it: the same
    header names, the same group match, case-insensitive (the IdP's group names
    are typed by hand).
    """
    console = _module()
    found = console.identity_from_headers(headers, console.Config(root=config.root))
    if found is None:
        return None, None
    forward = [("X-Auth-Request-User", found.user),
               ("X-Auth-Request-Email", found.email or "")]
    if found.groups:
        forward.append(("X-Auth-Request-Groups", ",".join(found.groups)))
    return forward, found


def is_admin(config: Config, identity) -> bool:
    if identity is None:
        return False
    mine = {group.strip().lower() for group in (identity.groups or ())}
    return bool(mine & {group.lower() for group in config.admin_groups})


class Handler(BaseHTTPRequestHandler):
    server_version = "AthenIQPortal/1"
    config: Config

    # -- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):  # the portal is public; keep the log quiet
        return

    def _send(self, status, body=b"", content_type="application/json; charset=utf-8",
              extra=None, cache="no-store"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", cache)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, payload, cache="no-store"):
        self._send(status, json.dumps(payload, default=str), cache=cache)

    def _error(self, status, message):
        self._json(status, {"error": message})

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("that request is too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            raise ValueError("expected JSON")

    #: Assets owned by another page in this repo but part of the one design. They
    #: are served from where they live rather than copied here, because a copy is
    #: the drift this app exists to stop.
    SHARED = {
        "unity-theme.css": os.path.join("web", "generate", "unity-theme.css"),
        "unity-theme.js": os.path.join("web", "generate", "unity-theme.js"),
    }

    def _proxy_console(self, path: str, forward):
        headers = {key: value for key, value in forward}
        request = urllib.request.Request(self.config.console_url + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                body = response.read()
                ctype = response.headers.get("Content-Type") or "application/octet-stream"
                return self._send(200, body, ctype)
        except urllib.error.HTTPError as error:
            return self._error(error.code, "the console refused that page")
        except (urllib.error.URLError, OSError) as error:
            return self._error(502, f"cannot reach the console: {error}")

    def _static(self, path):
        web_root = os.path.join(self.config.root, "web", "portal")
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        if rel in self.SHARED:
            shared = os.path.join(self.config.root, self.SHARED[rel])
            if os.path.isfile(shared):
                with open(shared, "rb") as fh:
                    body = fh.read()
                return self._send(200, body,
                                  "text/css; charset=utf-8" if rel.endswith(".css")
                                  else "application/javascript; charset=utf-8",
                                  cache="public, max-age=3600")
        target = os.path.normpath(os.path.join(web_root, rel))
        if os.path.commonpath([os.path.abspath(target), os.path.abspath(web_root)]) \
                != os.path.abspath(web_root) or not os.path.isfile(target):
            # One page, two views: an unknown path is the app, not a 404 page.
            target = os.path.join(web_root, "index.html")
            if not os.path.isfile(target):
                return self._error(404, "not found")
        with open(target, "rb") as fh:
            body = fh.read()
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        extra = {}
        if os.path.basename(target) == "index.html":
            extra["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                "form-action 'self'; base-uri 'none'")
        cache = "public, max-age=300" if self.config.view == "learner" else "no-store"
        self._send(200, body, ctype, extra, cache=cache)

    # -- routes -----------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        forward, person = identity_of(self.config, self.headers)
        staff = is_admin(self.config, person)

        if path == "/healthz":
            return self._json(200, {"ok": True, "service": "atheniq-portal",
                                    "view": self.config.view})
        if path == "/api/me":
            return self._json(200, {
                "user": getattr(person, "user", None),
                "email": getattr(person, "email", ""),
                "groups": list(getattr(person, "groups", ()) or ()),
                "admin": staff,
                "view": self.config.view,
            })
        if path in ("/api/catalog", "/admin/api/catalog"):
            try:
                payload = catalog(self.config)
            except ConsoleError as error:
                return self._error(502, str(error))
            payload["admin"] = bool(staff and path.startswith("/admin"))
            return self._json(200, payload, cache="public, max-age=60")
        if path == "/api/admin/runs":
            if not staff:
                return self._error(403, "staff only")
            try:
                return self._json(200, runs(self.config, forward))
            except ConsoleError as error:
                return self._error(502, str(error))
        if path.startswith("/console/") and staff:
            # The console's deep tools (templates, the library, a single program's
            # editor) are not rebuilt here: they are one click away, signed in as
            # the same person, rather than lost with the old front page.
            return self._proxy_console(path[len("/console"):], forward)
        if path == "/console":
            return self._send(302, "", extra={"Location": "/console/index.html"})
        if path in ("/admin", "/admin/") and not staff:
            # Not an error page: the console's own sign-in is what takes a person
            # from here to the IdP, so send them through it.
            return self._send(302, "", extra={"Location": "/"})
        if path.startswith("/api/"):
            return self._error(404, "no such endpoint")
        return self._static(path)

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        forward, person = identity_of(self.config, self.headers)
        if not is_admin(self.config, person):
            return self._error(403, "staff only")
        if self.headers.get(PORTAL_HEADER) is None:
            return self._error(403, "that request did not come from this page")
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlsplit(origin).netloc != \
                self.headers.get("Host", ""):
            return self._error(403, "cross-site request refused")
        try:
            body = self._body()
        except ValueError as error:
            return self._error(400, str(error))

        if path == "/api/admin/generate-missing":
            try:
                return self._json(202, console_post(self.config, "/api/generate-missing", forward))
            except ConsoleError as error:
                return self._error(502, str(error))
        if path.startswith("/api/admin/runs/") and path.endswith("/retry"):
            run_id = urllib.parse.unquote(path[len("/api/admin/runs/"):-len("/retry")])
            if not run_id or "/" in run_id:
                return self._error(400, "no such run")
            try:
                return self._json(200, console_post(
                    self.config, f"/api/runs/{urllib.parse.quote(run_id)}/retry", forward))
            except ConsoleError as error:
                return self._error(502, str(error))
        if path.startswith("/api/admin/runs/") and path.endswith("/record"):
            run_id = urllib.parse.unquote(path[len("/api/admin/runs/"):-len("/record")])
            try:
                return self._json(200, console_post(
                    self.config, f"/api/runs/{urllib.parse.quote(run_id)}/record", forward, body))
            except ConsoleError as error:
                return self._error(502, str(error))
        return self._error(404, "no such action")


def make_server(config: Config):
    handler = type("BoundHandler", (Handler,), {"config": config})
    return ThreadingHTTPServer((config.bind, config.port), handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", help="address to listen on (PORTAL_BIND)")
    ap.add_argument("--port", type=int, help="port to listen on (PORTAL_PORT)")
    ap.add_argument("--view", choices=("learner", "admin", "both"),
                    help="which views this listener offers (PORTAL_VIEW; default learner)")
    args = ap.parse_args(argv)

    config = Config.from_env()
    if args.bind:
        config.bind = args.bind
    if args.port:
        config.port = args.port
    if args.view:
        config.view = args.view
    if config.view not in ("learner", "admin", "both"):
        print(f"portal: unknown view {config.view!r}", file=sys.stderr)
        return 2
    try:
        server = make_server(config)
    except OSError as error:
        print(f"portal: cannot listen on {config.bind}:{config.port} ({error})", file=sys.stderr)
        return 2
    print(f"atheniq portal ({config.view}) on http://{config.bind}:{config.port} "
          f"-> console {config.console_url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
