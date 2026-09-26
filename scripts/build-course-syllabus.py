#!/usr/bin/env python3
"""AthenIQ — generate learner-facing syllabus pages from the OLX outlines.

For every course under `courses/<slug>/olx/`, walk the outline the way the LMS
does — course → chapter → sequential (subsection) → vertical (unit) → component —
and emit a readable syllabus at `web/landing/courses/<slug>/index.html`, with the
grading policy from the course's OLX policies.

The pages are *generated* so they can never drift from the courseware. `make
syllabus` writes them; CI regenerates and fails if a committed page is stale.

Usage:
    python3 scripts/build-course-syllabus.py           # write every page
    python3 scripts/build-course-syllabus.py --check   # fail if any page is stale
    python3 scripts/build-course-syllabus.py --stdout SLUG
"""
import argparse
import html
import importlib.util
import json
import os
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "web", "landing", "courses")
COURSES_DIR = os.path.join(REPO, "courses")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_module("check_course_olx", os.path.join(REPO, "scripts", "check-course-olx.py"))


def _text(node, attr="display_name"):
    return node.get(attr) or "(untitled)"


def load_outline(olx_dir):
    """Build the nested course outline for one OLX package."""
    index = ET.parse(os.path.join(olx_dir, "course.xml")).getroot()
    org, course, run = index.get("org"), index.get("course"), index.get("url_name")
    block = ET.parse(os.path.join(olx_dir, "course", f"{run}.xml")).getroot()

    chapters = []
    for chapter_ref in [c for c in block if c.tag == "chapter"]:
        cref = chapter_ref.get("url_name")
        chapter = ET.parse(os.path.join(olx_dir, "chapter", f"{cref}.xml")).getroot()
        subsections = []
        for seq_ref in [s for s in chapter if s.tag == "sequential"]:
            sref = seq_ref.get("url_name")
            seq = ET.parse(os.path.join(olx_dir, "sequential", f"{sref}.xml")).getroot()
            units = []
            for unit_ref in [u for u in seq if u.tag == "vertical"]:
                uref = unit_ref.get("url_name")
                unit = ET.parse(os.path.join(olx_dir, "vertical", f"{uref}.xml")).getroot()
                units.append({
                    "title": _text(unit),
                    "components": [child.tag for child in unit],
                })
            subsections.append({
                "title": _text(seq),
                "graded": seq.get("graded") == "true",
                "format": seq.get("format"),
                "units": units,
            })
        chapters.append({"title": _text(chapter), "subsections": subsections})

    description = ""
    desc_path = os.path.join(olx_dir, "about", "short_description.html")
    if os.path.isfile(desc_path):
        description = open(desc_path).read().strip()

    grading, pass_threshold = [], None
    grading_path = os.path.join(olx_dir, "policies", run, "grading_policy.json")
    if os.path.isfile(grading_path):
        policy = json.load(open(grading_path))
        grading = [{"type": g.get("type"), "weight": g.get("weight")}
                   for g in policy.get("GRADER", [])]
        cutoffs = policy.get("GRADE_CUTOFFS") or {}
        if "Pass" in cutoffs:
            pass_threshold = cutoffs["Pass"]

    return {
        "slug": os.path.basename(os.path.dirname(olx_dir)),
        "key": f"course-v1:{org}+{course}+{run}",
        "title": block.get("display_name") or course,
        "description": description,
        "grading": grading,
        "pass": pass_threshold,
        "chapters": chapters,
    }


def _e(text):
    return html.escape(str(text))


def render(model):
    chapters = []
    for i, chapter in enumerate(model["chapters"], start=1):
        subsections = []
        for sub in chapter["subsections"]:
            kind = f'{_e(sub["format"])}' if sub["graded"] and sub["format"] else (
                "graded" if sub["graded"] else "practice")
            chip = f'<span class="chip { "graded" if sub["graded"] else "practice" }">{kind}</span>'
            units = "".join(
                f'<li>{_e(u["title"])} <span class="tag">{_e(", ".join(u["components"]))}</span></li>'
                for u in sub["units"]
            )
            subsections.append(f"""          <div class="sub">
            <div class="sub-head"><h4>{_e(sub['title'])}</h4>{chip}</div>
            <ul class="units">{units}</ul>
          </div>""")
        chapters.append(f"""        <section class="chapter">
          <h3><span class="num">{i:02d}</span> {_e(chapter['title'])}</h3>
{chr(10).join(subsections)}
        </section>""")

    grading_rows = "".join(
        f"<tr><td>{_e(g['type'])}</td><td class=\"num\">{round(g['weight'] * 100)}%</td></tr>"
        for g in model["grading"]
    )
    pass_line = (f"Pass at {round(model['pass'] * 100)}%"
                 if isinstance(model["pass"], (int, float)) else "Pass threshold set in the LMS")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(model['title'])} — Syllabus — AthenIQ</title>
  <meta name="description" content="Syllabus for {_e(model['title'])}.">
  <meta property="og:image" content="https://innotelinc.github.io/atheniq/assets/atheniq-og.png">
  <link rel="icon" type="image/svg+xml" href="../../assets/favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="../../assets/favicon-32.png">
  <link rel="apple-touch-icon" href="../../assets/apple-touch-icon.png">
  <style>
    :root {{ color-scheme: dark; --bg:#0a1118; --elev:#101a22; --border:#22323d;
      --text:#eef4f8; --sec:#c2cfd9; --muted:#93a4b1; --accent:#10b981; --teal:#2dd4bf; --gold:#fbbf24; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text);
      font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; line-height:1.6; }}
    a {{ color:var(--accent); text-decoration:none; }}
    a:hover {{ color:#34d399; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:.84em; color:var(--sec); }}
    .wrap {{ max-width: 860px; margin: 0 auto; padding: 0 24px; }}
    .topbar {{ border-bottom:1px solid var(--border); background:rgba(10,17,24,.8); backdrop-filter: blur(20px); position: sticky; top:0; }}
    .topbar .wrap {{ display:flex; align-items:center; height:56px; gap:16px; }}
    .brand {{ font-weight:700; color:var(--text); letter-spacing:.04em; }}
    .brand .dot {{ color:var(--accent); }}
    .topbar nav {{ margin-left:auto; display:flex; gap:4px; }}
    .topbar nav a {{ color:var(--sec); padding:6px 12px; border-radius:6px; font-size:14px; }}
    .topbar nav a:hover {{ background:#1d2b36; color:var(--text); }}
    h1 {{ font-size: clamp(1.7rem, 4vw, 2.3rem); margin: 40px 0 6px; letter-spacing:-.02em; }}
    h2 {{ margin: 44px 0 12px; font-size: 1.25rem; }}
    .key {{ color:var(--muted); font-size:13px; }}
    .lede {{ color:var(--sec); }}
    .meta {{ display:flex; flex-wrap:wrap; gap:10px; margin:18px 0 0; }}
    .meta .pill {{ border:1px solid var(--border); border-radius:999px; padding:4px 12px; font-size:13px; color:var(--sec); }}
    .chapter {{ border:1px solid var(--border); background:var(--elev); border-radius:14px; padding:20px 22px; margin:14px 0; }}
    .chapter h3 {{ margin:0 0 12px; font-size:1.08rem; display:flex; gap:10px; align-items:baseline; }}
    .chapter .num {{ color:var(--accent); font-variant-numeric: tabular-nums; }}
    .sub {{ border-top:1px solid var(--border); padding:12px 0 6px; }}
    .sub:first-of-type {{ border-top:0; }}
    .sub-head {{ display:flex; align-items:center; gap:10px; }}
    .sub-head h4 {{ margin:0; font-size:.98rem; font-weight:600; }}
    .units {{ margin:8px 0 0; padding-left:18px; color:var(--sec); font-size:14px; }}
    .units li {{ margin:3px 0; }}
    .tag {{ color:var(--muted); font-size:11.5px; text-transform:uppercase; letter-spacing:.05em; margin-left:6px; }}
    .chip {{ margin-left:auto; font-size:11px; text-transform:uppercase; letter-spacing:.05em; border-radius:999px; padding:1px 9px; }}
    .chip.graded {{ color:var(--gold); border:1px solid rgba(251,191,36,.3); }}
    .chip.practice {{ color:var(--teal); border:1px solid rgba(45,212,191,.3); }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th, td {{ text-align:left; padding:10px; border-bottom:1px solid var(--border); }}
    td.num {{ white-space:nowrap; color:var(--sec); }}
    footer {{ border-top:1px solid var(--border); margin-top:52px; padding:26px 0 44px; color:var(--muted); font-size:13px; }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="wrap">
      <a class="brand" href="../../">AthenIQ<span class="dot">.</span></a>
      <nav aria-label="Main">
        <a href="../../catalog/">Catalog</a>
        <a href="../../">Home</a>
        <a href="https://github.com/innotelinc/atheniq">GitHub</a>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <h1>{_e(model['title'])}</h1>
    <p class="key"><code>{_e(model['key'])}</code></p>
    <p class="lede">{model['description']}</p>
    <div class="meta">
      <span class="pill">{len(model['chapters'])} chapters</span>
      <span class="pill">{pass_line}</span>
      <span class="pill">Certificate signed through Signara</span>
    </div>

    <h2>Outline</h2>
{chr(10).join(chapters)}

    <h2>Grading</h2>
    <table>
      <thead><tr><th>Assignment type</th><th>Weight</th></tr></thead>
      <tbody>
{grading_rows}
      </tbody>
    </table>
  </main>
  <footer>
    <div class="wrap">AthenIQ — Open Learning Platform · © 2026 Innotel Labs</div>
  </footer>
</body>
</html>
"""


def build_all(repo=REPO):
    """Return {slug: html} for every shipped course."""
    pages = {}
    for olx_dir in VALIDATOR.find_courses(os.path.join(repo, "courses")):
        model = load_outline(olx_dir)
        pages[model["slug"]] = render(model)
    return pages


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--stdout", metavar="SLUG", help="print one page instead of writing")
    ap.add_argument("--check", action="store_true", help="fail if a committed page is stale")
    args = ap.parse_args()

    pages = build_all()

    if args.stdout:
        if args.stdout not in pages:
            raise SystemExit(f"unknown course: {args.stdout}")
        print(pages[args.stdout], end="")
        return

    if args.check:
        stale = []
        for slug, page in pages.items():
            path = os.path.join(args.out_dir, slug, "index.html")
            if not os.path.isfile(path) or open(path).read() != page:
                stale.append(slug)
        if stale:
            raise SystemExit("stale syllabus page(s): " + ", ".join(sorted(stale))
                             + " (run make syllabus)")
        print(f"syllabus pages are up to date ({len(pages)}).")
        return

    for slug, page in pages.items():
        path = os.path.join(args.out_dir, slug, "index.html")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(page)
    print(f"wrote {len(pages)} syllabus page(s) to {os.path.relpath(args.out_dir, REPO)}")


if __name__ == "__main__":
    main()
