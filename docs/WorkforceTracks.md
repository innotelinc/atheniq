# AthenIQ — Workforce Tracks

A **track** is a named ladder of Open edX courses that share one audience, one
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
| `courses` | Tutor / Open edX (course runs) | LearningOps (AthenIQ) |
| `audience` | Authentik groups (`learners`, `instructors`) | Authentik |
| `entitlement.plan` | Magnate plan entitlement | Magnate |
| `credential` | Signed certificate (Signara) via `scripts/cert-bridge.py` | Signara |
| media/courseware assets | ONYX object storage | ONYX |

A learner progresses course by course; each passing grade auto-issues a
certificate (see [docs/Deployment.md](Deployment.md#98-automatic-certificate-issuance-on-passing-course-completion-trigger))
and the bridge signs it in Signara. The track records which courses together
constitute the credential.

> **Status (2026-09):** the catalog and its validation are live. The
> `it-support` track is **active**, backed by a four-course certification ladder
> authored in [`courses/`](../courses/README.md) as importable OLX (plus an
> OpenMAIC classroom spec): **ITSP101 Foundations**, **ITSP102 Networking &
> Systems Support**, **ITSP103 Security Operations**, and **ITSP104 Capstone**.
> The other tracks are seeded `draft`. Promoting a track to `active` means its
> course runs exist in the LMS, its entitlement (if any) is wired, and — for a
> track-level credential — a Signara signing flow for the track is configured.
> Track-level credential issuance and in-LMS track gating are the remaining V2
> work.

## Where a track's courses live

Courseware is authored in this repo under [`courses/`](../courses/README.md) as
**OLX** — the layout Open edX Studio exports and imports — so it is versioned and
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
