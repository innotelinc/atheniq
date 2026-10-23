#!/usr/bin/env python3
"""AthenIQ Workforce — generate the workforce division's site.

`workforce.atheniq.online` is not the university's catalogue with a different
title. It is where an employer meets a *funded program*: what it is, who pays
for it, which courses it contains, how they run, and what a worker can do at the
end. Those facts live in two places — the workforce program definitions in
`config/workforce-programs.json` and the courseware itself under `courses/` — and
this page is generated from both, so a course renamed in its OLX package cannot
stay renamed on the site.

The funding terms are quoted from the program they belong to (Commonwealth
Corporation's Focused AI Skills Training RFQ), not invented here: what this page
prints is the administrator's rule, the employer's cost, and the enrolment and
reporting obligations a provider carries.

Usage:
    python3 scripts/build-workforce-site.py           # write the site
    python3 scripts/build-workforce-site.py --check   # fail if it is stale
    python3 scripts/build-workforce-site.py --stdout  # print, do not write
"""
import argparse
import html
import importlib.util
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "web", "workforce")
OUT_FILE = os.path.join(OUT_DIR, "index.html")
PROGRAMS_FILE = os.path.join(REPO, "config", "workforce-programs.json")
TRACKS_FILE = os.path.join(REPO, "config", "workforce-tracks.json")
COURSES_DIR = os.path.join(REPO, "courses")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYLLABUS = _load_module("build_course_syllabus",
                        os.path.join(REPO, "scripts", "build-course-syllabus.py"))


def _e(text):
    return html.escape(str(text if text is not None else ""))


def courses_by_key(courses_dir=COURSES_DIR):
    """Every OLX package under `courses/`, indexed by its LMS key."""
    out = {}
    if not os.path.isdir(courses_dir):
        return out
    for name in sorted(os.listdir(courses_dir)):
        olx = os.path.join(courses_dir, name, "olx")
        if not os.path.isfile(os.path.join(olx, "course.xml")):
            continue
        model = SYLLABUS.load_outline(olx)
        out[model["key"]] = model
    return out


def load_model(repo=REPO, config=None):
    if config is None:
        config = json.load(open(os.path.join(repo, "config", "workforce-programs.json")))
    try:
        tracks = json.load(open(os.path.join(repo, "config", "workforce-tracks.json")))
    except FileNotFoundError:
        tracks = {"tracks": []}
    by_id = {track.get("id"): track for track in tracks.get("tracks") or []}
    library = courses_by_key(os.path.join(repo, "courses"))
    for program in config.get("programs") or []:
        track = by_id.get(program.get("track")) or {}
        program["_skills"] = list(track.get("skills") or [])
        program["_courses"] = []
        notes = dict(program.get("courseDescriptions") or {})
        for key in program.get("courses") or []:
            course = library.get(key)
            if course is None:
                raise SystemExit(
                    f"workforce site: {program['id']} names {key}, "
                    "which is not a course under courses/")
            code = key.split("+")[1] if key.count("+") >= 2 else key
            # The catalogue blurb is written for this page; the OLX description
            # is the fallback so a new course still renders something true.
            course = dict(course, blurb=notes.pop(code, "") or course["description"])
            program["_courses"].append(course)
        if notes:
            raise SystemExit(
                f"workforce site: {program['id']} describes courses it does not "
                f"list: {', '.join(sorted(notes))}")
    return config


def _courses_html(program):
    cards = []
    for number, course in enumerate(program["_courses"], 1):
        chapters = [chapter["title"] for chapter in course.get("chapters") or []]
        lessons = "<ul class=\"modules\">" + "".join(
            f"<li>{_e(title)}</li>" for title in chapters) + "</ul>" if chapters else ""
        cards.append("".join([
            '<article class="course card">\n',
            f'  <p class="kicker">Course {number} of {len(program["_courses"])}</p>\n',
            f'  <h3>{_e(course["title"])}</h3>\n',
            f'  <p>{_e(course.get("blurb") or course["description"])}</p>\n',
            f"  {lessons}\n",
            f'  <p class="meta">{len(chapters)} module{"s" if len(chapters) != 1 else ""}'
            ' · live AI classroom in every module</p>\n',
            "</article>",
        ]))
    return "\n".join(cards)


def _program_html(program, site):
    funding = program.get("funding") or {}
    terms = "".join(f"<li>{_e(term)}</li>" for term in funding.get("terms") or [])
    timeline = "".join(f"<li>{_e(item)}</li>" for item in program.get("timeline") or [])
    delivery = "".join(f"<li>{_e(item)}</li>" for item in program.get("delivery") or [])
    outcomes = "".join(f"<li>{_e(item)}</li>" for item in program.get("outcomes") or [])
    skills = "".join(f'<span class="chip">{_e(skill)}</span>'
                     for skill in program.get("_skills") or [])
    contact = site.get("contact") or ""
    return f"""
<section class="band" id="program">
  <div class="wrap">
    <p class="kicker">Workforce development · {_e(site["institute"])}</p>
    <h2>{_e(program["name"])}</h2>
    <p class="lede">{_e(program["summary"])}</p>
    <p class="meta">Credential: <strong>{_e(program["credential"])}</strong>
      · Audience: {_e(program["audience"])}</p>
    <div class="skills">{skills}</div>
  </div>
</section>

<section class="band alt" id="funding">
  <div class="wrap two-up">
    <div>
      <h2>What it costs an employer</h2>
      <p>{_e(funding.get("cost"))}</p>
      <p class="meta">Administered by {_e(funding.get("administrator"))},
        funded by the {_e(funding.get("source"))}.</p>
      <h3>Program terms</h3>
      <ul class="tight">{terms}</ul>
    </div>
    <div>
      <h2>How the training runs</h2>
      <ul class="tight">{delivery}</ul>
      <h3>Timeline</h3>
      <ul class="tight">{timeline}</ul>
    </div>
  </div>
</section>

<section class="band" id="courses">
  <div class="wrap">
    <h2>The six courses</h2>
    <p class="lede">Taken as a ladder they form the {_e(program["credential"])}
      certificate; taken individually, each stands on its own against an
      employer's training plan.</p>
    <div class="grid">
{_courses_html(program)}
    </div>
  </div>
</section>

<section class="band alt" id="outcomes">
  <div class="wrap">
    <h2>What a worker can do afterwards</h2>
    <ul class="tight outcomes">{outcomes}</ul>
    <p class="cta">
      <a class="button primary" href="{_e(site["catalog"])}">See the course catalog</a>
      <a class="button" href="{_e(site["login"])}">Sign in to the classroom</a>
      <a class="button" href="mailto:{_e(contact)}">Talk to workforce development</a>
    </p>
  </div>
</section>
"""


def render(model):
    site = model["site"]
    programs = model["programs"]
    nav = "".join(
        f'<a href="#program">{_e(program["name"])}</a>'
        for program in programs)
    bodies = "".join(_program_html(program, site) for program in programs)
    return f"""<!doctype html>
<html lang="en" data-scheme="desk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(site["title"])} — {_e(site["tagline"])}</title>
  <meta name="description" content="{_e(site["description"])}">
  <meta property="og:title" content="{_e(site["title"])} — {_e(site["tagline"])}">
  <meta property="og:description" content="{_e(site["description"])}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://{_e(site["host"])}/">
  <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/assets/unity-theme.css">
  <meta name="color-scheme" content="light dark">
  <style>
    /* AthenIQ Workforce — layout on the Unity theme's tokens. */
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: var(--canvas); color: var(--ink);
      font-family: var(--font-sans); line-height: 1.6;
      -webkit-font-smoothing: antialiased; }}
    a {{ color: var(--brand); }}
    h1, h2, h3 {{ line-height: 1.15; letter-spacing: -0.02em; margin: 0; }}
    h1 {{ font-size: clamp(2.3rem, 5.4vw, 3.7rem); font-weight: 760; }}
    h2 {{ font-size: clamp(1.6rem, 3.2vw, 2.3rem); font-weight: 720; }}
    h3 {{ font-size: 1.1rem; font-weight: 680; }}
    p {{ margin: 0; }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 0 24px; }}
    .skip {{ position: absolute; left: -999px; }}
    header.site {{ border-bottom: 1px solid var(--line, rgba(0,0,0,.1));
      background: var(--surface, #fff); }}
    header.site .wrap {{ display: flex; align-items: center;
      justify-content: space-between; gap: 16px; padding-block: 14px; }}
    .brand {{ display: flex; align-items: center; gap: 10px;
      font-weight: 720; text-decoration: none; color: var(--ink); }}
    .brand img {{ width: 30px; height: 30px; }}
    nav a {{ margin-left: 18px; font-size: .92rem; text-decoration: none; }}
    .hero {{ padding: clamp(48px, 8vw, 96px) 0 40px; }}
    .hero p.lede {{ margin-top: 18px; font-size: 1.12rem; max-width: 62ch;
      color: var(--ink-soft, #4a4557); }}
    .band {{ padding: 56px 0; }}
    .band.alt {{ background: var(--surface, #fff); }}
    .kicker {{ text-transform: uppercase; letter-spacing: .12em;
      font-size: .76rem; font-weight: 700; color: var(--brand); }}
    .lede {{ margin-top: 12px; max-width: 68ch; }}
    .meta {{ margin-top: 14px; font-size: .92rem; color: var(--ink-soft, #4a4557); }}
    .two-up {{ display: grid; gap: 40px; grid-template-columns: 1fr; }}
    @media (min-width: 860px) {{ .two-up {{ grid-template-columns: 1fr 1fr; }} }}
    ul.tight {{ margin: 12px 0 0; padding-left: 20px; }}
    ul.tight li {{ margin-bottom: 8px; }}
    ul.outcomes {{ columns: 2; column-gap: 32px; }}
    @media (max-width: 720px) {{ ul.outcomes {{ columns: 1; }} }}
    .grid {{ display: grid; gap: 20px; margin-top: 28px;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
    .card {{ background: var(--surface, #fff); border-radius: 16px;
      padding: 22px; border: 1px solid var(--line, rgba(0,0,0,.12)); }}
    .card h3 {{ margin: 6px 0 10px; }}
    ul.modules {{ margin: 12px 0 0; padding-left: 18px; font-size: .92rem; }}
    ul.modules li {{ margin-bottom: 4px; }}
    .skills {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }}
    .chip {{ font-size: .8rem; padding: 4px 10px; border-radius: 999px;
      background: var(--brand-soft, #ece8ff); color: var(--brand);
      font-weight: 600; }}
    .cta {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 28px; }}
    .button {{ display: inline-block; padding: 11px 18px; border-radius: 10px;
      border: 1px solid var(--brand); color: var(--brand);
      text-decoration: none; font-weight: 650; }}
    .button.primary {{ background: var(--brand); color: var(--brand-ink, #fff); }}
    footer.site {{ padding: 36px 0 56px; font-size: .9rem;
      color: var(--ink-soft, #4a4557); }}
    footer.site p + p {{ margin-top: 8px; }}
  </style>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site">
    <div class="wrap">
      <a class="brand" href="/"><img src="/assets/atheniq-mark.svg" alt="">{_e(site["title"])}</a>
      <nav>{nav}<a href="#funding">Funding</a><a href="#courses">Courses</a></nav>
    </div>
  </header>
  <main id="main">
    <section class="hero">
      <div class="wrap">
        <p class="kicker">Workforce development · {_e(site["institute"])}</p>
        <h1>{_e(site["tagline"])}</h1>
        <p class="lede">{_e(site["description"])}</p>
      </div>
    </section>
{bodies}
  </main>
  <footer class="site">
    <div class="wrap">
      <p><strong>{_e(site["institute"])}</strong> — {_e(site["title"])}.
        Courses run on the institute's LMS at
        <a href="{_e(site["catalog"])}">atheniq.courses</a>.</p>
      <p>Program questions: <a href="mailto:{_e(site["contact"])}">{_e(site["contact"])}</a>.
        For funding questions, Commonwealth Corporation can be reached at
        <a href="mailto:fastai@commcorp.org">fastai@commcorp.org</a>.</p>
    </div>
  </footer>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed page differs from the generated one")
    ap.add_argument("--stdout", action="store_true", help="print the page, do not write it")
    ap.add_argument("--out", default=OUT_FILE, help="where to write (default web/workforce/index.html)")
    args = ap.parse_args()

    page = render(load_model())
    if args.stdout:
        sys.stdout.write(page)
        return 0
    if args.check:
        try:
            current = open(args.out, encoding="utf-8").read()
        except FileNotFoundError:
            print(f"workforce site: {args.out} is missing — run make workforce-site", file=sys.stderr)
            return 1
        if current != page:
            print(f"workforce site: {args.out} is stale — run make workforce-site", file=sys.stderr)
            return 1
        print("workforce site is up to date.")
        return 0
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
