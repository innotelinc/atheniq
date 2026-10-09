# AthenIQ — Workforce Tracks

A **track** is a named ladder of AthenIQ courses that share one audience, one
target role, and (optionally) one credential — the unit a workforce-development
or instructor program actually sells and reports on. Tracks are the curated
layer *above* individual courses; they are not a second course engine.

The catalog is data, not code: [`config/workforce-tracks.json`](../config/workforce-tracks.json).
Keeping it machine-readable is what lets the landing page, the runbook, and the
operator share one definition of what a track is.

## Shape

```json
{
  "id": "data-foundations",
  "title": "Data Foundations",
  "summary": "Spreadsheets to SQL: the data literacy every operations role now expects.",
  "audience": "workforce",              // workforce | instructors | learners
  "target_role": "Data / Operations Analyst",
  "status": "draft",                    // draft | active | retired
  "courses": [
    "course-v1:InnotelLabs+DATA101+2026_T1",
    "course-v1:InnotelLabs+SQL101+2026_T1"
  ],
  "credential": {
    "type": "certificate",              // certificate | badge | none
    "title": "Data Foundations — Track Completion",
    "signara_template": "course-completion"
  },
  "entitlement": {
    "plan": "premium"                   // null = free; otherwise a Magnate plan slug
  },
  "skills": ["spreadsheets", "SQL", "data cleaning", "reporting"]
}
```

A track may be free (`entitlement.plan: null`) or gated on a Magnate plan.
Gating reuses the platform's one entitlement decision — see
[docs/Integrations.md](Integrations.md#magnate--paid-courses--entitlements-revenueops) —
so a track never carries its own price or Stripe key.

## Validate

```bash
make check-tracks                                  # human summary
python3 scripts/check-workforce-tracks.py --json   # machine output
python3 scripts/check-workforce-tracks.py --markdown   # README-ready table
```

`scripts/check-workforce-tracks.py` verifies unique slugs, required fields,
`course-v1:<org>+<course>+<run>` course keys, valid statuses, credential types,
and Magnate plan slugs, and warns when one course is claimed by several tracks.
It is a lint only — it never touches the LMS.

## How a track maps onto the platform

| Track field | Lives in | Owned by |
| --- | --- | --- |
| `courses` | Tutor / AthenIQ (course runs) | LearningOps (AthenIQ) |
| `audience` | Authentik groups (`learners`, `instructors`) | Authentik |
| `entitlement.plan` | Magnate plan entitlement | Magnate |
| `credential` | Signed certificate (Signara) via `scripts/cert-bridge.py` | Signara |
| media/courseware assets | ONYX object storage | ONYX |

A learner progresses course by course; each passing grade auto-issues a
certificate (see [docs/Deployment.md](Deployment.md#98-automatic-certificate-issuance-on-passing-course-completion-trigger))
and the bridge signs it in Signara. The track records which courses together
constitute the credential.

> **Status (2026-10):** the catalog and its validation are live, and **all three
> tracks are `active`** — every course a track claims ships as importable OLX in
> [`courses/`](../courses/README.md), so the library and the catalog cannot
> drift:
>
> - `it-support` — the four-course certification ladder **ITSP101 Foundations**,
>   **ITSP102 Networking & Systems Support**, **ITSP103 Security Operations**,
>   and **ITSP104 Capstone** (plus an OpenMAIC classroom spec).
> - `data-foundations` — **DATA101 Data Foundations** and **SQL101 SQL
>   Essentials**.
> - `ai-classroom-facilitator` — **MAIC101 AI Classroom Facilitation** (plus an
>   OpenMAIC classroom spec, since authoring classrooms is the subject it teaches).
>
> Promoting a track to `active` means its course runs exist in the LMS, its
> entitlement (if any) is wired, and — for a track-level credential — the gating
> below is applied and the credential can be signed.

## Gating: a ladder the LMS enforces

A track's courses are listed in progression order; `scripts/track-gating.py`
turns that order into each course's prerequisites and writes them to the LMS.
Sequential (default) unlocks a course once the one before it is passed;
`--cumulative` requires every earlier course.

```bash
make gating                 # print the derived plan
make check-gating           # fail if the catalog cannot be gated cleanly (CI)
make gating-apply           # write prerequisites through the running CMS
python3 scripts/track-gating.py --apply --dry-run   # show the CMS snippet first
```

`--apply` goes through the CMS's own `CourseOverview` model (`./manage.py cms
shell`), so the LMS's gating signals fire — it never edits the row behind Open
edX's back. Nothing is written unless `--apply` is passed.

## Track credential

A completed ladder earns the track's `credential`, signed through Signara exactly
like a course certificate. This happens **automatically**: the certificate bridge
(`scripts/cert-bridge.py`, the same timer that signs course certificates) checks on
every pass whether any learner's certificates now cover a whole track and signs the
track credential then — no operator step. Disable it with `--no-track-credentials`.

`scripts/track-credential.py` is the detector the bridge reuses, and stays useful
on its own for reporting and on-demand signing: it reads the learner's downloadable
course certificates, reports the tracks they complete, and — with `--sign` — renders
a track-completion PDF and pushes it through the same Signara client. Outcomes are
ledgered in `atheniq_track_credential` keyed on (track, learner), so re-runs (and
the bridge's per-pass check) are idempotent.

```bash
python3 scripts/track-credential.py --learner learner@example.edu
python3 scripts/track-credential.py --learner learner@example.edu --sign
make track-credential-status
```

## Where a track's courses live

Courseware is authored in this repo under [`courses/`](../courses/README.md) as
**OLX** — the layout AthenIQ Studio exports and imports — so it is versioned and
reviewable beside the catalog that references it. `scripts/check-course-olx.py`
lints it (`make check-courses`) exactly as `check-workforce-tracks.py` lints the
catalog; the LMS stays the runtime.

## Adding or retiring a track

1. Add the track to `config/workforce-tracks.json` and run `make check-tracks`.
2. Author the course as OLX under `courses/<slug>/` (or create the runs in
   Studio at `studio.<domain>`) under the tracked `course-v1:` keys, with graded
   problems and a certificate definition, then run `make check-courses`.
3. If the track is paid, point `entitlement.plan` at the plan slug Magnate
   reports for it and confirm with
   `python3 scripts/magnate-entitlements.py check --plan <slug>`.
4. Set `status` to `active`. To retire a track, set it to `retired` — leave it
   in the catalog so existing completions keep their history.
