# OpenMAIC classrooms — ITSP101

[`classrooms.json`](classrooms.json) is the generative-classroom specification for
the seven chapters of ITSP101. OpenMAIC turns each entry into a live, multi-agent
lesson — slides, roleplay, simulations, and quizzes with an AI teacher and
classmates.

## Why this is a spec, not generated content

OpenMAIC is cloned at bring-up (`./services/OpenMAIC`, see
[`docs/Integrations.md`](../../../docs/Integrations.md#openmaic--generative-interactive-classroom));
it is not vendored into this repo. Committing the *specification* keeps the
classroom design versioned and reviewable, while generation stays with OpenMAIC and
is routed through the platform's single OmniRoute gateway.

## Generate

1. Bring OpenMAIC up against the platform's OmniRoute gateway: in
   `services/OpenMAIC/.env.local`, set `OPENAI_BASE_URL` to
   `$OMNIROUTE_BASE_URL` and `OPENAI_API_KEY` to this project's OmniRoute key
   (`cerulean/atheniq#OMNIROUTE_API_KEY` in Cerulean Vault).
2. For each entry in `classrooms.json`, submit `prompt`, `objectives`, and the
   `defaults` agent roles to OpenMAIC as the lesson brief. The `activities` list is
   the intended shape of the generated classroom.
3. Optionally drive the same requests from chat through **OpenClaw** with the
   OpenMAIC skill.

## Link back to the LMS

Each classroom declares `linked_units` using the course's OLX `url_name`s. After
generation, embed the classroom in the matching AthenIQ unit (an LTI or iframe
component) so learners move from the static lesson to the interactive classroom
inside the same course. The classroom aligns with, and does not replace, that
chapter's graded activity.

## Keeping it honest

If a chapter's outline changes, update its `chapter`, `linked_units`, and
`objectives` here in the same change — the spec and the OLX should never drift.
