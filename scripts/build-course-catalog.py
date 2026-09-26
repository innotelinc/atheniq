#!/usr/bin/env python3
"""AthenIQ — generate the static course catalog page.

Reads the repository's own sources of truth and emits a single self-contained
page, `web/landing/catalog/index.html`:

  * the workforce tracks from `config/workforce-tracks.json`
  * the paid/free access from `config/course-prices.json`
  * the course titles and structure from the OLX packages under `courses/`

The page is *generated*, not hand-maintained, so the catalog can never drift
from the configuration. `make catalog` writes it; CI regenerates and fails if the
committed page is stale (see tests/test_course_catalog.py).

Usage:
    python3 scripts/build-course-catalog.py            # write the page
    python3 scripts/build-course-catalog.py --check    # fail if it is stale
    python3 scripts/build-course-catalog.py --stdout   # print, do not write
"""
import argparse
import html
import importlib.util
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(REPO, "web", "landing", "catalog", "index.html")
TRACKS_FILE = os.path.join(REPO, "config", "workforce-tracks.json")
PRICES_FILE = os.path.join(REPO, "config", "course-prices.json")
COURSES_DIR = os.path.join(REPO, "courses")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_module("check_course_olx", os.path.join(REPO, "scripts", "check-course-olx.py"))


def access_label(entry):
    if not entry:
        return "Free"
    price = entry.get("amount_cents")
    if price:
        return f"${price / 100:.2f} one-off"
    plan = entry.get("plan")
    return f"Magnate `{plan}`" if plan else "Free"


def load_model(repo=REPO):
    tracks_doc = json.load(open(os.path.join(repo, "config", "workforce-tracks.json")))
    try:
        prices = json.load(open(os.path.join(repo, "config", "course-prices.json")))
    except FileNotFoundError:
        prices = {"courses": {}}
    price_map = prices.get("courses") or {}

    course_by_key = {}
    root = os.path.join(repo, "courses")
    for olx_dir in VALIDATOR.find_courses(root):
        slug = os.path.basename(os.path.dirname(olx_dir))
        errors, _, summary = VALIDATOR.validate_course(olx_dir)
        key = summary["course_key"]
        course_by_key[key] = {
            "key": key,
            "slug": slug,
            "title": summary["title"] or key,
            "chapters": summary["chapters"],
            "units": summary["units"],
            "lessons": summary["html"],
            "problems": summary["problems"],
            "access": access_label(price_map.get(key)),
            "valid": not errors,
            "tracks": [],
        }

    tracks = []
    for track in tracks_doc.get("tracks", []):
        for key in track.get("courses", []):
            if key in course_by_key:
                course_by_key[key]["tracks"].append(track["id"])
        tracks.append(track)

    return {"tracks": tracks, "courses": sorted(course_by_key.values(), key=lambda c: c["key"])}


def _e(text):
    return html.escape(str(text))


def render(model):
    track_by_id = {t["id"]: t for t in model["tracks"]}
    course_by_key = {c["key"]: c for c in model["courses"]}

    track_cards = []
    for track in model["tracks"]:
        plan = (track.get("entitlement") or {}).get("plan")
        access = f"Magnate `{plan}`" if plan else "Free"
        course_items = "".join(
            f"<li>{_e(course_by_key[key]['title'])}</li>"
            for key in track.get("courses", []) if key in course_by_key
        ) or "<li>—</li>"
        skills = ", ".join(track.get("skills", []))
        track_cards.append(f"""        <article class="card">
          <div class="card-head"><h3>{_e(track['title'])}</h3><span class="chip { _e(track.get('status', 'draft')) }">{_e(track.get('status', 'draft'))}</span></div>
          <p class="muted">{_e(track.get('target_role', ''))} · {_e(track.get('audience', ''))} · {_e(access)}</p>
          <p>{_e(track.get('summary', ''))}</p>
          <ul class="courses">{course_items}</ul>
          <p class="skills">{_e(skills)}</p>
        </article>""")

    rows = []
    for course in model["courses"]:
        track_names = ", ".join(track_by_id.get(tid, {}).get("title", tid) for tid in course["tracks"]) or "—"
        flag = "" if course["valid"] else ' <span class="chip draft">invalid</span>'
        rows.append(f"""          <tr>
            <td><strong><a href="../courses/{_e(course['slug'])}/">{_e(course['title'])}</a></strong>{flag}<br><code>{_e(course['key'])}</code></td>
            <td>{_e(track_names)}</td>
            <td>{_e(course['access'])}</td>
            <td class="num">{course['chapters']} · {course['units']} · {course['lessons']} · {course['problems']}</td>
          </tr>""")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Course catalog — AthenIQ</title>
  <meta name="description" content="Every track and course AthenIQ delivers, generated from the repository's catalogs and OLX packages.">
  <meta property="og:image" content="https://innotelinc.github.io/atheniq/assets/atheniq-og.png">
  <link rel="icon" type="image/svg+xml" href="../assets/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="../assets/favicon-32.png">
  <link rel="apple-touch-icon" href="../assets/apple-touch-icon.png">
  <style>
    :root {{
      color-scheme: dark;
      --p-bg: #0a1118; --p-bg-elevated: #101a22; --p-border: #22323d;
      --p-text: #eef4f8; --p-text-secondary: #c2cfd9; --p-text-muted: #93a4b1;
      --p-accent: #10b981; --p-accent-hover: #34d399; --p-accent-tint: rgba(16,185,129,0.12);
      --p-success: #2dd4bf; --p-gold: #fbbf24;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--p-bg); color: var(--p-text);
      font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; line-height: 1.6; }}
    a {{ color: var(--p-accent); text-decoration: none; }}
    a:hover {{ color: var(--p-accent-hover); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .84em; color: var(--p-text-secondary); }}
    .wrap {{ max-width: 1040px; margin: 0 auto; padding: 0 24px; }}
    .topbar {{ position: sticky; top: 0; background: rgba(10,17,24,.8); backdrop-filter: blur(20px); border-bottom: 1px solid var(--p-border); }}
    .topbar .wrap {{ display: flex; align-items: center; height: 58px; gap: 18px; }}
    .brand {{ font-weight: 700; letter-spacing: .04em; color: var(--p-text); }}
    .brand .dot {{ color: var(--p-accent); }}
    .topbar nav {{ margin-left: auto; display: flex; gap: 4px; }}
    .topbar nav a {{ color: var(--p-text-secondary); padding: 6px 12px; border-radius: 6px; font-size: 14px; }}
    .topbar nav a:hover {{ color: var(--p-text); background: #1d2b36; }}
    h1 {{ font-size: clamp(1.9rem, 4vw, 2.6rem); letter-spacing: -.02em; margin: 48px 0 8px; }}
    h1 .accent {{ color: var(--p-accent); }}
    h2 {{ margin: 48px 0 16px; font-size: 1.35rem; }}
    .lede {{ color: var(--p-text-secondary); max-width: 660px; margin: 0 0 8px; }}
    .grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
    .card {{ background: var(--p-bg-elevated); border: 1px solid var(--p-border); border-radius: 14px; padding: 20px; }}
    .card-head {{ display: flex; align-items: center; gap: 10px; }}
    .card h3 {{ margin: 0; font-size: 1.05rem; }}
    .muted {{ color: var(--p-text-muted); font-size: 13px; margin: 4px 0 10px; }}
    .courses {{ margin: 10px 0; padding-left: 18px; }}
    .skills {{ color: var(--p-text-muted); font-size: 12.5px; margin: 10px 0 0; }}
    .chip {{ margin-left: auto; font-size: 11px; letter-spacing: .05em; text-transform: uppercase; border-radius: 999px; padding: 1px 9px; }}
    .chip.active {{ color: var(--p-success); border: 1px solid rgba(45,212,191,.3); }}
    .chip.draft {{ color: var(--p-gold); border: 1px solid rgba(251,191,36,.3); }}
    .chip.retired {{ color: var(--p-text-muted); border: 1px solid var(--p-border); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ text-align: left; padding: 12px 10px; border-bottom: 1px solid var(--p-border); vertical-align: top; }}
    th {{ color: var(--p-text-secondary); font-size: 12.5px; text-transform: uppercase; letter-spacing: .05em; }}
    td.num {{ white-space: nowrap; color: var(--p-text-secondary); }}
    footer {{ border-top: 1px solid var(--p-border); margin-top: 56px; padding: 28px 0 44px; color: var(--p-text-muted); font-size: 13px; }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="wrap">
      <a class="brand" href="../">AthenIQ<span class="dot">.</span></a>
      <nav aria-label="Main">
        <a href="../">Home</a>
        <a href="../#courses">Overview</a>
        <a href="https://github.com/innotelinc/atheniq">GitHub</a>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <h1>Course catalog<span class="accent">.</span></h1>
    <p class="lede">Every track and course AthenIQ delivers, generated from
      <code>config/workforce-tracks.json</code>, <code>config/course-prices.json</code>
      and the OLX packages under <code>courses/</code>.</p>

    <h2>Tracks</h2>
    <div class="grid">
{chr(10).join(track_cards)}
    </div>

    <h2>Courses</h2>
    <p class="lede">Structure column: chapters · units · lessons · problems.</p>
    <table>
      <thead><tr><th>Course</th><th>Track</th><th>Access</th><th>Structure</th></tr></thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </main>
  <footer>
    <div class="wrap">AthenIQ — Open Learning Platform · © 2026 Innotel Labs</div>
  </footer>
</body>
</html>
"""


def build(repo=REPO):
    return render(load_model(repo))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT, help="output path")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    ap.add_argument("--check", action="store_true", help="fail if the output is stale")
    args = ap.parse_args()

    page = build()
    if args.stdout:
        print(page, end="")
        return
    if args.check:
        try:
            current = open(args.out).read()
        except FileNotFoundError:
            raise SystemExit(f"catalog page missing: {args.out} (run make catalog)")
        if current != page:
            raise SystemExit(f"catalog page is stale: {args.out} (run make catalog)")
        print("catalog page is up to date.")
        return

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write(page)
    print(f"wrote {os.path.relpath(args.out, REPO)}")


if __name__ == "__main__":
    main()
