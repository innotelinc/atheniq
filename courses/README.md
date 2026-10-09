# Courses

Authoring source for the courses AthenIQ delivers on the Tutor engine.
Course *content* lives here as **OLX** — the same Open Learning XML layout Studio
exports and imports — so it is versioned, reviewable, and portable. The LMS remains
the runtime; this directory is the source of truth for the courseware.

| Course | Key | Track | Contents |
| --- | --- | --- | --- |
| **TEST101 — AthenIQ Demo Course** | `course-v1:InnotelLabs+TEST101+2026_T1` | — (platform demo) | [`demo-course/`](demo-course/README.md) |
| **ITSP101 — IT Support Foundations** | `course-v1:InnotelLabs+ITSP101+2026_T1` | `it-support` | [`it-support-certification/`](it-support-certification/README.md) |
| **ITSP102 — Networking & Systems Support** | `course-v1:InnotelLabs+ITSP102+2026_T1` | `it-support` | [`networking-systems-support/`](networking-systems-support/README.md) |
| **ITSP103 — Security Operations Foundations** | `course-v1:InnotelLabs+ITSP103+2026_T1` | `it-support` | [`security-operations/`](security-operations/README.md) |
| **ITSP104 — IT Support Capstone** | `course-v1:InnotelLabs+ITSP104+2026_T1` | `it-support` | [`capstone/`](capstone/README.md) |
| **DATA101 — Data Foundations** | `course-v1:InnotelLabs+DATA101+2026_T1` | `data-foundations` | [`data-foundations/`](data-foundations/README.md) |
| **SQL101 — SQL Essentials** | `course-v1:InnotelLabs+SQL101+2026_T1` | `data-foundations` | [`sql-essentials/`](sql-essentials/README.md) |
| **MAIC101 — AI Classroom Facilitation** | `course-v1:InnotelLabs+MAIC101+2026_T1` | `ai-classroom-facilitator` | [`ai-classroom-facilitation/`](ai-classroom-facilitation/README.md) + [OpenMAIC classrooms](ai-classroom-facilitation/openmaic/README.md) |

## Bundle and import

```bash
make course-bundle                              # validate + write dist/courses/<slug>.tar.gz
python3 scripts/import-courses.py                # plan only: what would be imported
python3 scripts/import-courses.py --course ITSP102
make course-import                               # import every course into the running LMS
```

`scripts/import-courses.py` finds every `courses/*/olx` package, validates it with
the same linter CI runs, bundles each with a top-level `olx/` directory, and prints
the `docker cp` + extract + `manage.py cms import` commands it would run. Note that
`manage.py cms import` takes a data directory plus course *directories* inside it —
it does not unpack archives and a course key is not a valid argument — so the tool
stages each bundle under `/openedx/data/<slug>-<run>` (extracting the `olx/`
wrapper) and imports it by directory name; the key is read from `course.xml`.
Nothing touches the LMS until `--execute` (or `make course-import`) — a deliberate
operator action. See [docs/Deployment.md](../docs/Deployment.md).

Re-importing is idempotent in effect: importing a course under the same
`course-v1:` key updates it in place.

## Catalog page

Two pages are **generated** from the config files and the OLX packages, so they
never drift from them:

- `web/landing/catalog/index.html` — every track and course.
- `web/landing/courses/<slug>/index.html` — a learner-facing syllabus per course,
  built by walking the OLX outline.

```bash
make catalog          # regenerate the catalog page
make syllabus         # regenerate the per-course syllabus pages
make check-catalog    # CI: fail if a generated page is stale
make check-syllabus
```

## Course card images (PNG)

Each course keeps its card as a **vector master** (`static/<slug>-course-card.svg`)
and a rendered **raster** (`static/<slug>-course-card.png`). The PNG is the LMS-facing
`course_image` because the AthenIQ course card, social unfurlers, and app icons do
not render SVG.

```bash
make images           # render every PNG with Pillow (no SVG rasteriser needed)
make check-images     # CI: fail if a raster is missing or mis-sized
```

`scripts/build-course-images.py` derives the card text from the OLX package and
[`config/workforce-tracks.json`](../config/workforce-tracks.json); it also renders the
landing page's `favicon-32.png`, `apple-touch-icon.png`, and `atheniq-og.png`. Pillow
is the only dependency (`pip install Pillow`), and the palette/geometry mirror
[`docs/Brand.md`](../docs/Brand.md) — change the brand there first.

## Classroom specs (OpenMAIC)

A course may ship a **generative-classroom specification** beside its courseware at
`courses/<slug>/openmaic/classrooms.json` — one entry per chapter describing the
scenario OpenMAIC should generate (prompt, objectives, agent roles, activities) and
the OLX units it links back to. See
[`it-support-certification/openmaic/`](it-support-certification/openmaic/README.md)
and [`ai-classroom-facilitation/openmaic/`](ai-classroom-facilitation/openmaic/README.md).

```bash
make check-classrooms   # CI: fail if a spec has drifted from the OLX outline
```

`scripts/check-classrooms.py` reads both sides and fails when they disagree: the
`source_course` must have an OLX package here, each classroom's `chapter` must exist
in that course's outline, and every `linked_units` entry must be a unit **of that
chapter** — so a unit renamed, deleted, or moved between chapters is caught. It also
warns when a chapter has no classroom.

## Adding a course

1. Create `courses/<course-slug>/olx/` in the Studio export layout (root
   `course.xml`, then `course/`, `chapter/`, `sequential/`, `vertical/`, `html/`,
   `problem/`, `policies/`, `about/`, `info/`).
2. Add the course key to [`config/workforce-tracks.json`](../config/workforce-tracks.json)
   (and [`config/course-prices.json`](../config/course-prices.json) if it is paid).
3. Optionally author `courses/<course-slug>/openmaic/classrooms.json` for a live
   multi-agent classroom in the course's own chapters.
4. Run the lints — they are wired into CI:

   ```bash
   make images            # render the course card + brand PNGs
   make check-courses     # the OLX structure
   make check-classrooms  # the classroom specs (if any) vs the OLX outline
   make check-tracks      # the workforce-track catalog
   make test              # unit tests
   ```

See [`docs/WorkforceTracks.md`](../docs/WorkforceTracks.md) for how a course maps
onto a track, an entitlement, and a credential.
