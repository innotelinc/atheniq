#!/usr/bin/env python3
"""AthenIQ — generate the OpenMAIC classrooms a course spec describes.

Every course ships `courses/<slug>/openmaic/classrooms.json`: one entry per
chapter, holding the brief OpenMAIC should turn into a live, multi-agent
classroom (prompt, objectives, agent roles, activities) and the OLX units it
links back to. This tool submits those briefs to the deployed OpenMAIC and
records the classroom it created, so the courseware can point at a real
classroom instead of a promise.

It is deliberately two-phase, like `import-courses.py`:

  * the default (plan) prints what it would submit and touches nothing;
  * `--execute` submits the missing classrooms, polls each run to completion,
    and writes the resulting `classroom_id` back into the spec;
  * `--inject` rewrites the lesson HTML between that classroom's
    `<!-- openmaic:begin <id> -->` / `<!-- openmaic:end <id> -->` markers so the
    unit embeds the live classroom (an iframe plus a fallback link).

OpenMAIC runs beside the LMS on the same host, and its published address is
loopback-only (see `docs/Deployment.md`), so the default base URL is
`http://127.0.0.1:3000`. Run the tool from the host that serves the classroom.

Usage:
    python3 scripts/build-classrooms.py                      # plan (default)
    python3 scripts/build-classrooms.py --execute            # generate
    python3 scripts/build-classrooms.py --execute --jobs 2
    python3 scripts/build-classrooms.py --course FAI101
    python3 scripts/build-classrooms.py --execute --models codex/gpt-5.6-luna-medium,auto/best-chat
    python3 scripts/build-classrooms.py --inject             # write the embeds
    python3 scripts/build-classrooms.py --json

The generation run is the server's own: an outline is planned and confirmed
automatically, then scenes (with narration, images and quizzes) are produced.

A run that pauses has hit a model the gateway cannot serve — most often a quota
or rate limit on the route the classroom is configured with. The tool does not
wait such a run out: it stops there (or resumes it `--max-resumes` times, 0 by
default) and reports the step and the gateway's own words, so the failure is
visible instead of hidden behind hours of retries. Pass `--models` to give it a
chain of gateway models to fall back on: a classroom that pauses is re-submitted
on the next model after pointing the classroom's chat slots at it through
OpenMAIC's model settings, and a model that works is then reused for the rest of
the batch. Switching models is workspace-wide, so `--models` runs one classroom
at a time.

Exit codes: 0 ok, 1 a submission or run failed, 2 a spec is invalid.
"""
import argparse
import concurrent.futures
import html
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSES_DIR = os.path.join(REPO, "courses")
DEFAULT_BASE_URL = "http://127.0.0.1:3000"
CLASSROOM_HOST = "https://classroom.innotel.us"

# The gateway is the deployment's only model provider, and these are the slots
# a generation run reads its models from.
PROVIDER_ID = "omniroute"
MODEL_SLOTS = ("llm", "course.content.slide", "course.content.interactive", "agent")

# Phrases a gateway uses when it is out of capacity rather than out of patience
# with the request. They are what separates "this route is spent, try another"
# from "this classroom is malformed", and only the first is worth retrying.
CAPACITY_MARKERS = (
    "quota", "rate limit", "rate_limit", "out of credits", "credit", "circuit open",
    "circuit breaker", "no active credentials", "queue budget", "pre-dispatch",
    "cooldown", "cooling down", "429", "402", "temporarily unavailable",
    "insufficient", "concurrency",
)

_LOCK = threading.Lock()


class RunPaused(RuntimeError):
    """A run stopped on a step it could not finish — a model-supply failure."""

    def __init__(self, step, error, run_id=None):
        self.step = step
        self.error = str(error or "")
        self.run_id = run_id
        super().__init__(f"paused on {step or 'a step'}: {self.error or 'no error reported'}")

    @property
    def capacity(self):
        """True when the message names a gateway limit rather than bad input."""
        return looks_like_capacity_failure(self.error)


def looks_like_capacity_failure(text):
    """Whether a gateway error message is about supply, not about the request."""
    low = (text or "").lower()
    return any(marker in low for marker in CAPACITY_MARKERS)


def model_candidates(raw):
    """The gateway models from `--models`, in the order given, deduplicated."""
    seen, out = set(), []
    for part in (raw or "").replace(";", ",").split(","):
        name = part.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def build_plan(specs, olx_index, wanted, skipped, validator=None):
    """The classrooms in scope, each with where it sits in its own spec.

    Returns (plan, invalid). `index` in a plan entry is the classroom's position
    in `classrooms[]` — what a finished run writes back to. Numbering the ones
    that still need a classroom instead would file each result under a chapter
    that already had one, as soon as a spec had a gap in it.
    """
    plan, invalid = [], []
    for slug, path in specs:
        doc = read_spec(path)
        # A spec may be authored before its OLX package (the courseware is the
        # slower half). Validate its structure against the outline only once the
        # outline exists; `make check-classrooms` is the gate before import.
        if validator and doc.get("source_course") in olx_index:
            errors, _, _ = validator.validate_spec(path, olx_index)
        else:
            errors = []
        code = str(doc.get("source_course") or "").split("+")[1]
        if not course_selected(slug, code, wanted, skipped):
            continue
        for index, classroom in enumerate(doc.get("classrooms", [])):
            plan.append({
                "slug": slug,
                "spec": path,
                "doc": doc,
                "index": index,
                "classroom": classroom,
                "chapter": classroom.get("chapter"),
                "title": classroom.get("title"),
                "generated": bool(classroom.get("classroom_id")),
            })
        invalid.extend(f"{slug}: {e}" for e in errors)
    return plan, invalid


def model_ref(model):
    """An OpenMAIC model reference: the deployment provider plus the model id."""
    name = model[len(PROVIDER_ID) + 1:] if model.startswith(PROVIDER_ID + ":") else model
    return f"{PROVIDER_ID}:{name}"


def split_arg(raw):
    """A comma-separated flag value as a list, with the blanks dropped."""
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def course_selected(slug, code, wanted, skipped):
    """Whether the plan covers this course: `--course` picks, `--skip` refuses."""
    if slug in skipped or (code and code in skipped):
        return False
    return not wanted or slug in wanted or (code and code in wanted)


def _load_classroom_validator():
    path = os.path.join(REPO, "scripts", "check-classrooms.py")
    spec = importlib.util.spec_from_file_location("check_classrooms", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spec_paths(root=None):
    """Every course's classroom spec, in a stable order."""
    courses = root or COURSES_DIR
    found = []
    if not os.path.isdir(courses):
        return found
    for slug in sorted(os.listdir(courses)):
        path = os.path.join(courses, slug, "openmaic", "classrooms.json")
        if os.path.isfile(path):
            found.append((slug, path))
    return found


def plan_entries(root=None, wanted=None, skipped=None, validator=None):
    """The plan over every spec under root, and the invalid specs in it."""
    courses = root or COURSES_DIR
    validator = validator or _load_classroom_validator()
    return build_plan(spec_paths(courses), validator.olx_index(courses),
                      wanted or [], skipped or [], validator)


def read_spec(path):
    with open(path) as fh:
        return json.load(fh)


def write_spec(path, doc):
    """Write the spec back without reordering what a person wrote."""
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def requirement_text(doc, classroom):
    """The brief submitted for one classroom.

    OpenMAIC's headless API takes a single `requirement` string; the spec's
    agent roles, interaction and assessment shape are folded into it so the
    generated classroom keeps the design the spec describes.
    """
    defaults = doc.get("defaults") or {}
    lines = [classroom.get("prompt", "").strip()]
    if defaults.get("teacher_persona"):
        lines.append("The AI teacher: " + defaults["teacher_persona"].strip())
    classmates = defaults.get("classmates") or []
    if classmates:
        lines.append("The AI classmates (cast one per description): "
                     + "; ".join(c.strip() for c in classmates) + ".")
    if defaults.get("interaction"):
        lines.append("Interaction: " + defaults["interaction"].strip())
    if defaults.get("assessment"):
        lines.append("Assessment: " + defaults["assessment"].strip())
    objectives = classroom.get("objectives") or []
    if objectives:
        lines.append("By the end, learners can: "
                     + "; ".join(o.strip() for o in objectives) + ".")
    activities = classroom.get("activities") or []
    if activities:
        kinds = ", ".join(f"{a.get('type')} ({a.get('title')})" for a in activities)
        lines.append("The classroom should include: " + kinds + ".")
    if doc.get("locale"):
        lines.append("Language: " + doc["locale"] + ".")
    return "\n\n".join(line for line in lines if line)


class OpenMAIC:
    """The parts of OpenMAIC's HTTP API this tool needs."""

    def __init__(self, base_url, timeout=60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, method, path, body=None):
        data = None
        headers = {"accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["content-type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as err:
            try:
                payload = json.load(err)
            except Exception:
                payload = {"error": err.read().decode("utf-8", "replace")}
            return err.code, payload
        except urllib.error.URLError as err:
            raise SystemExit(f"cannot reach OpenMAIC at {self.base_url}: {err.reason}")

    def health(self):
        return self._call("GET", "/api/health")

    def submit(self, requirement):
        return self._call("POST", "/api/generate-classroom",
                          {"requirement": requirement})

    def run(self, run_id):
        return self._call("GET", f"/api/generation-runs/{run_id}")

    def retry(self, run_id):
        return self._call("POST", f"/api/generation-runs/{run_id}/retry",
                          {"commandId": f"cmd-{int(time.time() * 1000)}"})

    def model_config(self):
        return self._call("GET", "/api/model-config")

    def discard(self, run_id):
        """Throw away a run that has no classroom, freeing the owner's slot.

        A paused run still counts as one the owner has in progress, so a batch
        that moved on to another model would otherwise collect paused runs until
        the server refused to start anything. A run whose classroom exists
        answers 409 and is kept.
        """
        return self._call("DELETE", f"/api/generation-runs/{run_id}")

    def set_models(self, model):
        """Point the classroom's chat slots at one gateway model.

        A run resolves its models as it starts, so a switch here is what the
        next classroom generates with — no container restart, no rebuild.
        """
        status, view = self.model_config()
        if status != 200:
            raise RuntimeError(f"cannot read the classroom's model settings: {status} {view}")
        ref = model_ref(model)
        change = {"kind": "slots", "set": {slot: ref for slot in MODEL_SLOTS}}
        status, answer = self._call("PUT", "/api/model-config",
                                    {"revision": view.get("revision"), "change": change})
        if status != 200:
            raise RuntimeError(f"cannot set the classroom model to {ref}: {status} {answer}")
        return ref


def submit_once(client, requirement, attempts=6, pause=30):
    """Submit a classroom, waiting out the owner's active-run limit."""
    for attempt in range(1, attempts + 1):
        status, body = client.submit(requirement)
        if status in (200, 202):
            run_id = body.get("jobId") or body.get("runId")
            if not run_id:
                raise RuntimeError(f"no run id in response: {body}")
            return run_id
        if status == 429:
            if attempt == attempts:
                raise RuntimeError("owner is at its active-run limit")
            time.sleep(pause)
            continue
        message = (body.get("error") or {}).get("message") if isinstance(body, dict) else body
        code = (body.get("error") or {}).get("code") if isinstance(body, dict) else None
        raise RuntimeError(f"refused ({status} {code}): {message or body}")
    raise RuntimeError("gave up submitting")


def wait_for_run(client, run_id, timeout_s=5400, poll_s=15, max_resumes=0):
    """Poll a generation run to completion.

    A pause is a model-supply failure, not a slow step, so it is raised (after
    `max_resumes` retries, none by default) rather than waited out: the caller
    can move the classroom to another model instead of paying for the same
    broken route until the timeout.
    """
    deadline = time.time() + timeout_s
    resumes = 0
    backoff = 30
    while time.time() < deadline:
        status, body = client.run(run_id)
        if status != 200:
            raise RuntimeError(f"cannot read run {run_id}: {status} {body}")
        run = body.get("run") or body
        state = run.get("state")
        if state == "completed":
            stage_id = run.get("stageId")
            if not stage_id:
                raise RuntimeError("run completed without a stage id")
            return stage_id
        if state in ("ended",):
            raise RuntimeError(f"run {run_id} ended: {run.get('error')}")
        if state == "paused":
            if resumes >= max_resumes:
                raise RunPaused(run.get("step"), run.get("error"), run_id)
            resumes += 1
            time.sleep(backoff)
            backoff = min(backoff * 2, 240)
            client.retry(run_id)
            continue
        time.sleep(poll_s)
    raise RuntimeError(f"run {run_id} did not finish within {timeout_s}s")


def generate_one(item, model=None, max_resumes=0, run_timeout=5400):
    """Generate one classroom.

    Returns (spec_path, classroom_index, stage_id, error, paused): the caller
    needs to know a pause apart from any other failure to decide whether another
    model is worth trying.
    """
    slug, path, index, classroom, doc, base_url = item
    client = OpenMAIC(base_url)
    requirement = requirement_text(doc, classroom)
    label = f"{slug}/{classroom.get('chapter')}"
    try:
        run_id = submit_once(client, requirement)
        stage_id = wait_for_run(client, run_id, timeout_s=run_timeout,
                                max_resumes=max_resumes)
    except RunPaused as exc:
        # Free the owner's run slot: the next model submits a fresh run, and a
        # batch that leaves its paused runs behind is refused for concurrency.
        if exc.run_id:
            status, _ = client.discard(exc.run_id)
            if status not in (200, 202, 204, 404, 409):
                print(f"  could not discard {exc.run_id}: {status}", file=sys.stderr)
        return path, index, None, f"{label}: {exc}", True
    except Exception as exc:  # report and keep the batch going
        return path, index, None, f"{label}: {exc}", False
    # Persist immediately: a long batch must survive an interruption without
    # losing classrooms it already paid for.
    with _LOCK:
        doc = read_spec(path)
        doc["classrooms"][index]["classroom_id"] = stage_id
        if model:
            doc["classrooms"][index]["model"] = model_ref(model)
        write_spec(path, doc)
        print(f"  generated {label} -> {stage_id}", flush=True)
    return path, index, stage_id, None, False


def inject_block(doc, classroom, stage_id):
    """The HTML that embeds one classroom in its lesson unit."""
    title = html.escape(classroom.get("title") or classroom.get("id") or "classroom")
    url = f"{CLASSROOM_HOST}/classroom/{stage_id}"
    return (
        f'<div class="openmaic-classroom">\n'
        f'  <h4>Live classroom: {title}</h4>\n'
        f'  <p>Run this chapter as a multi-agent classroom on OpenMAIC: an AI teacher,\n'
        f'  AI classmates, and the scenario from the lesson — with you in the room.</p>\n'
        f'  <p><a href="{url}" target="_blank" rel="noopener">Open “{title}” at\n'
        f'  classroom.innotel.us</a></p>\n'
        f'  <iframe src="{url}" title="{title} — OpenMAIC classroom" width="100%"\n'
        f'    height="680" loading="lazy" allow="microphone; camera; fullscreen"\n'
        f'    allowfullscreen\n'
        f'    style="border:1px solid #22323d;border-radius:12px;background:#0a1118"></iframe>\n'
        f'  <p><small>If the classroom does not load in the page, open it in a new tab and\n'
        f'  sign in with your AthenIQ account.</small></p>\n'
        f'</div>'
    )


def unit_html_path(slug, unit):
    """The `.html` file behind a linked unit, or None when it has no html component."""
    olx = os.path.join(COURSES_DIR, slug, "olx")
    vertical = os.path.join(olx, "vertical", f"{unit}.xml")
    if not os.path.isfile(vertical):
        return None
    with open(vertical) as fh:
        body = fh.read()
    marker = '<html url_name="'
    start = body.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = body.find('"', start)
    if end < 0:
        return None
    name = body[start:end]
    path = os.path.join(olx, "html", f"{name}.html")
    return path if os.path.isfile(path) else None


def import_course(course_key):
    """Import one course's OLX into the running CMS (the operator action, run for you)."""
    result = subprocess.run(
        [sys.executable, os.path.join(REPO, "scripts", "import-courses.py"),
         "--execute", "--course", course_key],
        cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise RuntimeError("import failed: " + " / ".join(tail))
    return result.stdout


def publish_one(path, args):
    """Embed one finished classroom and put its course back in the LMS."""
    if not args.publish:
        return None
    slug = os.path.basename(os.path.dirname(os.path.dirname(path)))
    key = read_spec(path).get("source_course")
    try:
        inject_links({slug})
        import_course(key)
        print(f"  published {slug} -> {key}", flush=True)
        return None
    except Exception as exc:  # keep the batch generating the rest
        print(f"  FAILED to publish {slug}: {exc}", file=sys.stderr)
        return f"{slug}: {exc}"


def run_campaign(items, candidates, args):
    """Generate the classrooms, moving to the next model when a run pauses.

    A classroom that pauses is re-submitted on the next model of the chain, and
    a model that finishes a classroom is the one every later classroom starts
    on. When the chain runs out, the batch stops: the point of failing fast is
    to leave the remaining classrooms for a gateway that can serve them.
    """
    client = OpenMAIC(args.base_url)
    chain = list(candidates)
    applied = None
    failures = []
    queue = list(items)
    while queue:
        item = queue.pop(0)
        model = chain[0]
        if model != applied:
            try:
                print(f"  classroom model -> {client.set_models(model)}", flush=True)
                applied = model
            except Exception as exc:
                print(f"  FAILED to use {model}: {exc}", file=sys.stderr)
                if len(chain) > 1:
                    chain.pop(0)
                    queue.insert(0, item)
                    continue
                failures.append(f"model {model}: {exc}")
                break
        path, index, stage_id, error, paused = generate_one(
            item, model=model, max_resumes=args.max_resumes,
            run_timeout=args.run_timeout)
        if not error:
            problem = publish_one(path, args)
            if problem:
                failures.append(problem)
            continue
        if paused and len(chain) > 1:
            print(f"  paused on {model}; retrying on {chain[1]}", file=sys.stderr)
            chain.pop(0)
            queue.insert(0, item)
            continue
        failures.append(error)
        print(f"  FAILED {error}", file=sys.stderr)
        if paused:
            if queue:
                failures.append(f"{len(queue)} classroom(s) not attempted: no model "
                                f"left in the chain")
            break
    return failures


def run_batch(items, jobs, args):
    """Generate the classrooms on whatever model the classroom is configured with."""
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(generate_one, item, None, args.max_resumes,
                               args.run_timeout): item for item in items}
        for future in concurrent.futures.as_completed(futures):
            path, index, stage_id, error, paused = future.result()
            if error:
                failures.append(error)
                print(f"  FAILED {error}", file=sys.stderr)
                continue
            problem = publish_one(path, args)
            if problem:
                failures.append(problem)
    return failures


def inject_links(only_slugs=None):
    """Embed every generated classroom in the first html unit that links to it."""
    changed, missing = [], []
    for slug, path in spec_paths():
        if only_slugs and slug not in only_slugs:
            continue
        doc = read_spec(path)
        for classroom in doc.get("classrooms", []):
            stage_id = classroom.get("classroom_id")
            if not stage_id:
                missing.append(f"{slug}/{classroom.get('id')}")
                continue
            target = None
            for unit in classroom.get("linked_units", []):
                target = unit_html_path(slug, unit)
                if target:
                    break
            if not target:
                missing.append(f"{slug}/{classroom.get('id')} (no html unit)")
                continue
            with open(target) as fh:
                page = fh.read()
            begin = f"<!-- openmaic:begin {classroom['id']} -->"
            end = f"<!-- openmaic:end {classroom['id']} -->"
            block = f"{begin}\n{inject_block(doc, classroom, stage_id)}\n{end}"
            if begin in page and end in page:
                head = page[:page.index(begin)]
                tail = page[page.index(end) + len(end):]
                updated = head + block + tail
            else:
                updated = page.rstrip("\n") + "\n\n" + block + "\n"
            if updated != page:
                with open(target, "w") as fh:
                    fh.write(updated)
                changed.append(os.path.relpath(target, REPO))
    for rel in changed:
        print(f"embedded -> {rel}")
    if missing:
        print(f"not embedded ({len(missing)}): " + ", ".join(missing))
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course",
                    help="only these courses (slug or course code, comma-separated)")
    ap.add_argument("--skip",
                    help="leave these courses alone (slug or course code, "
                         "comma-separated) — the demo course, say")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help=f"OpenMAIC base URL (default {DEFAULT_BASE_URL})")
    ap.add_argument("--execute", action="store_true", help="submit and poll the runs")
    ap.add_argument("--force", action="store_true",
                    help="regenerate classrooms that already have an id")
    ap.add_argument("--jobs", type=int, default=1,
                    help="classrooms generated at once (default 1: the gateway "
                         "rate-limits concurrent runs)")
    ap.add_argument("--models",
                    help="gateway models to fall back through, best first "
                         "(comma-separated); a paused run moves to the next one")
    ap.add_argument("--max-resumes", type=int, default=0,
                    help="times to resume a paused run before moving on (default 0: "
                         "stop at the first pause)")
    ap.add_argument("--run-timeout", type=int, default=5400,
                    help="seconds one generation run may take (default 5400)")
    ap.add_argument("--inject", action="store_true",
                    help="write the generated classrooms into the lesson HTML")
    ap.add_argument("--publish", action="store_true",
                    help="after each classroom, inject it and re-import that course")
    ap.add_argument("--json", action="store_true", help="machine-readable plan")
    args = ap.parse_args()

    validator = _load_classroom_validator()
    plan, invalid = plan_entries(None, split_arg(args.course), split_arg(args.skip),
                                 validator)

    if args.json:
        print(json.dumps({"classrooms": [
            {k: p[k] for k in ("slug", "chapter", "title", "generated")} for p in plan
        ], "invalid": invalid}, indent=2))
        return 0

    pending = [p for p in plan if args.force or not p["generated"]]
    print(f"classrooms: {len(plan)} in scope, {len(plan) - len(pending)} already generated, "
          f"{len(pending)} to generate")
    for p in plan:
        mark = "has id" if p["generated"] else "pending"
        print(f"  {p['slug']:<34} {p['chapter']:<22} {p['title']}  [{mark}]")
    if invalid:
        print("invalid specs:\n  " + "\n  ".join(invalid), file=sys.stderr)
        return 2
    if args.inject and not args.execute:
        inject_links({p["slug"] for p in plan})
        return 0
    if not args.execute:
        if pending:
            print("\nplan only — pass --execute to generate, --inject to write the embeds")
        return 0
    if not pending:
        print("nothing to generate")
        return 0

    status, body = OpenMAIC(args.base_url).health()
    if status != 200:
        print(f"OpenMAIC health check failed: {status} {body}", file=sys.stderr)
        return 1

    jobs = max(1, args.jobs)
    candidates = model_candidates(args.models)
    # The classroom's model settings are one workspace-wide value, so a model
    # switch mid-batch would move classrooms that are already generating.
    if candidates and jobs > 1:
        print("note: --models switches the whole classroom, so this run uses --jobs 1",
              file=sys.stderr)
        jobs = 1
    items = [(p["slug"], p["spec"], p["index"], p["classroom"], p["doc"], args.base_url)
             for p in pending]
    if candidates:
        print(f"models: {', '.join(candidates)}")
        failures = run_campaign(items, candidates, args)
    else:
        failures = run_batch(items, jobs, args)

    if args.inject:
        inject_links()
    if failures:
        print(f"{len(failures)} classroom(s) failed; re-run --execute to resume them",
              file=sys.stderr)
        return 1
    print("all requested classrooms generated; run --inject to embed them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
