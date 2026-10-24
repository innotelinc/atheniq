# OnTrak Class — roadmap (AthenIQ classroom host)

> **Re-baselined at 2.0 (2026-10-24).** OnTrak Class is the family's classroom
> product: the OpenMAIC host at `classroom.innotel.us`, generated from an OnTrak
> course and linked from the training app by `Course.classroomUrl` /
> `Cohort.classroomUrl`. The shipped host is **2.0.0**; the next minor milestones
> are 2.1–2.4, and the next majors are 3.0 and 4.0. The portfolio view is
> `ontrak-work/docs/portfolio-roadmap-v2.md`.
>
> This file is the **OnTrak Class product view**. The AthenIQ platform's own
> roadmap (V1 foundation → V2 scale) stays in [../README.md](../README.md) and
> covers the LMS, media studio and realtime layer beneath it.
>
> Status legend: `[x]` shipped · `[~]` in progress · `[ ]` planned.

## 1. Vision

A course is taught, not just published: lessons a learner can enter, checks they
can pass, and a record of what each learner actually finished — in the browser,
with no install.

## 2. 2.0.0 — shipped baseline `[x]`

- `[x]` **The classroom host** at `classroom.innotel.us` (OpenMAIC), behind the
  family's Cerulean sign-in. `/api/health` is the one unauthenticated path, so the
  portal's light probes the lesson server rather than a sign-in redirect.
- `[x]` **Generated multi-agent lessons** — slides, quizzes, interactive HTML
  simulations and project-based learning, generated from a course's modules.
- `[x]` **A validated classroom specification** — `classrooms.json` per course
  (`version`, `defaults`, one entry per module with `id`, `title`, `prompt`,
  `objectives`, `activities`), checked against the course's OLX by
  `scripts/check-classrooms.py` and built by `scripts/build-classrooms.py`.
- `[x]` **A generation console** — an operator creates a course/classroom from the
  browser, previews the spec, downloads it, and submits it to the classroom host.
- `[x]` **Completion → signed certificate** — AthenIQ's V1.2 path: completion
  flows to Signara and the learner's dashboard links the signed PDF.
- `[x]` **The family hand-off** — OnTrak ITS holds the classroom's address and the
  class it belongs to; no learner identity, subject or token is appended to the
  link, so there is no second, weaker identity path.

**2.0 exit:** a cohort opens a generated classroom from its course, works through
the lesson and its checks, and the completion produces a signed certificate.

## 3. Next

### 2.1 — Completion handoff to ITS `[ ]`

**Goal:** the classroom's progress is not a second record of record.

- `[ ]` A classroom completion becomes an ITS training record (and, where the
  course requires it, an ITS certificate), with the classroom's own completion id
  as the idempotency key.
- `[ ]` Exit: finishing a lesson produces a verifiable ITS record, once, and a
  retry does not duplicate it.

### 2.2 — Instructor authoring `[ ]`

- `[ ]` An instructor can edit checks and lesson structure without regenerating
  the whole classroom from a prompt.
- `[ ]` Exit: an edited check grades the same way a generated one does.

### 2.3 — Progress analytics `[ ]`

- `[ ]` Per-learner and per-cohort progress for the instructor: who entered, who
  finished, where they stopped.
- `[ ]` Exit: an instructor answers "who is stuck" without exporting anything.

### 2.4 — Classroom packs `[ ]`

- `[ ]` Versioned, portable classroom bundles so a course can pin its classroom
  set and ship it to another range.

### 3.0 — Multi-course academy `[ ]`

- `[ ]` Cohorts, prerequisites and a catalog spanning courses, with the record
  still landing in one place.

### 4.0 — Adaptive classroom `[ ]`

- `[ ]` The lesson adjusts to demonstrated gaps, with the record still explainable
  and the checks still auditable.

## 4. Boundaries

- OnTrak never holds the classroom's model key, database credentials or
  `ACCESS_CODE`; the classroom host owns them.
- The classroom link carries no identity or token.
- AthenIQ's LMS remains the course-delivery platform; this product is the
  classroom surface the OnTrak family links to.
