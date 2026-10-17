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
    python3 scripts/build-classrooms.py --inject             # write the embeds
    python3 scripts/build-classrooms.py --json

The generation run is the server's own: an outline is planned and confirmed
automatically, then scenes (with narration, images and quizzes) are produced.
A run that pauses on a retryable step is resumed once with a fresh command id,
which is the same recovery an operator would perform in the UI.

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

_LOCK = threading.Lock()


def _load_classroom_validator():
    path = os.path.join(REPO, "scripts", "check-classrooms.py")
    spec = importlib.util.spec_from_file_location("check_classrooms", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spec_paths():
    """Every course's classroom spec, in a stable order."""
    found = []
    if not os.path.isdir(COURSES_DIR):
        return found
    for slug in sorted(os.listdir(COURSES_DIR)):
        path = os.path.join(COURSES_DIR, slug, "openmaic", "classrooms.json")
        if os.path.isfile(path):
            found.append((slug, path))
    return found


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


def wait_for_run(client, run_id, timeout_s=3600, poll_s=15):
    """Poll a generation run; resume it once if a retryable step pauses it."""
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
            # A paused step is retryable. Rate limits on the model gateway are the
            # common cause, so back off further each time rather than hammering it.
            resumes += 1
            if resumes > 8:
                raise RuntimeError(f"run paused {resumes} times: {run.get('error')}")
            time.sleep(backoff)
            backoff = min(backoff * 2, 240)
            client.retry(run_id)
            continue
        time.sleep(poll_s)
    raise RuntimeError(f"run {run_id} did not finish within {timeout_s}s")


def generate_one(item):
    """Generate one classroom; return (spec_path, classroom_id, error)."""
    slug, path, index, classroom, doc, base_url = item
    client = OpenMAIC(base_url)
    requirement = requirement_text(doc, classroom)
    label = f"{slug}/{classroom.get('chapter')}"
    try:
        run_id = submit_once(client, requirement)
        stage_id = wait_for_run(client, run_id)
    except Exception as exc:  # report and keep the batch going
        return path, index, None, f"{label}: {exc}"
    # Persist immediately: a long batch must survive an interruption without
    # losing classrooms it already paid for.
    with _LOCK:
        doc = read_spec(path)
        doc["classrooms"][index]["classroom_id"] = stage_id
        write_spec(path, doc)
        print(f"  generated {label} -> {stage_id}", flush=True)
    return path, index, stage_id, None


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
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL,
                    help=f"OpenMAIC base URL (default {DEFAULT_BASE_URL})")
    ap.add_argument("--execute", action="store_true", help="submit and poll the runs")
    ap.add_argument("--force", action="store_true",
                    help="regenerate classrooms that already have an id")
    ap.add_argument("--jobs", type=int, default=1,
                    help="classrooms generated at once (default 1: the gateway "
                         "rate-limits concurrent runs)")
    ap.add_argument("--inject", action="store_true",
                    help="write the generated classrooms into the lesson HTML")
    ap.add_argument("--publish", action="store_true",
                    help="after each classroom, inject it and re-import that course")
    ap.add_argument("--json", action="store_true", help="machine-readable plan")
    args = ap.parse_args()

    validator = _load_classroom_validator()
    index = validator.olx_index(COURSES_DIR)

    plan, invalid = [], []
    for slug, path in spec_paths():
        doc = read_spec(path)
        # A spec may be authored before its OLX package (the courseware is the
        # slower half). Validate its structure against the outline only once the
        # outline exists; `make check-classrooms` is the gate before import.
        if doc.get("source_course") in index:
            errors, warnings, summary = validator.validate_spec(path, index)
        else:
            errors, warnings, summary = [], [], {}
        code = str(doc.get("source_course") or "").split("+")[1]
        wanted = [w.strip() for w in (args.course or "").split(",") if w.strip()]
        if wanted and slug not in wanted and code not in wanted:
            continue
        for classroom in doc.get("classrooms", []):
            plan.append({
                "slug": slug,
                "spec": path,
                "doc": doc,
                "classroom": classroom,
                "chapter": classroom.get("chapter"),
                "title": classroom.get("title"),
                "generated": bool(classroom.get("classroom_id")),
            })
        invalid.extend(f"{slug}: {e}" for e in errors)

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
    items = [(p["slug"], p["spec"], i, p["classroom"], p["doc"], args.base_url)
             for i, p in enumerate(pending)]
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(generate_one, item): item for item in items}
        for future in concurrent.futures.as_completed(futures):
            path, index, stage_id, error = future.result()
            if error:
                failures.append(error)
                print(f"  FAILED {error}", file=sys.stderr)
                continue
            if args.publish:
                slug = os.path.basename(os.path.dirname(os.path.dirname(path)))
                key = read_spec(path).get("source_course")
                try:
                    inject_links({slug})
                    import_course(key)
                    print(f"  published {slug} -> {key}", flush=True)
                except Exception as exc:  # keep the batch generating the rest
                    failures.append(f"{slug}: {exc}")
                    print(f"  FAILED to publish {slug}: {exc}", file=sys.stderr)

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
