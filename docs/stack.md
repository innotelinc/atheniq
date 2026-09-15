# 🎓 AthenIQ — Platform Stack Role

**Classification: LearningOps**

Open learning platform: courses, enrollment, delivery, and AI classrooms — the
university / workforce-development / training surface of the ecosystem.

This page declares AthenIQ's role in the
[**Innotel Platform Stack**](https://github.com/innotelinc/innotel-platform-stack) —
the canonical single-responsibility architecture. The stack is defined in exactly one
place; this page links each product to it and states what this platform owns, consumes,
provides, and explicitly does not own.

## Owns

- Course catalog and enrollment
- Courseware delivery (LMS + Studio authoring)
- Assessments, grading, and learner records
- AI interactive classrooms (multi-agent lessons, quizzes, simulations)
- Course completions and completion evidence
- Course media authoring workflows

## Provides

- Learning delivery and completion evidence for the ecosystem
- Completion records that feed certificate workflows

## Consumes

- Authentik — identity, SSO, MFA, groups (learners, instructors, admins)
- Cerulean Vault — secrets, provider keys, OAuth secrets
- Cerulean — DNS, certificates, TLS (TrustOps)
- ONYX — storage and backups for courseware media
- Magnate — paid courses, subscriptions, entitlements
- Signara — signed course certificates for completed learners

## Explicitly does NOT own

- Identity (Authentik)
- Secrets (Cerulean Vault)
- Certificates / DNS / TLS (Cerulean)
- Storage (ONYX)
- Billing (Magnate)
- Signing / agreement audit trails (Signara)

## External building blocks

AthenIQ assembles upstream open-source projects rather than re-implementing
them. They are integrated, not forked responsibilities:

- **Tutor** (OverhangIO) — Dockerized Open edX LMS/CMS distribution
- **OpenMAIC** (THU-MAIC) — Open Multi-Agent Interactive Classroom
- **Convex** (self-hosted backend) — realtime state for live classrooms
- **Open Generative AI** (MuAPI studio) — course media generation
- **OpenClaw · OpenClaude · OmniRoute** — the AI agent layer and model gateway

## Secrets (Cerulean Vault)

The platform's SecretOps is **Cerulean Vault** — HashiCorp Vault, KV v2, hosted
by Cerulean — with `vault://<mount>/<path>#<key>` references in `.env`.

### Legacy: the Infisical profile

This stack currently still imports its provider keys, OAuth secrets, and service
credentials into an **Infisical** workspace and derives `.env` from it. Generate
local development values with `./setup.sh`; production values are pulled from
Infisical at bring-up until the `vault://` path lands. See
[docs/Deployment.md](Deployment.md).

## Golden rules

- **Authentik = Identity** · **Cerulean Vault = Secrets** · **Cerulean = Trust** ·
  **ONYX = Storage** · **Magnate = Revenue** — everything else is a business function.
- No platform duplicates another's responsibility.
- No credit in commits, footers, or headers to anyone but the project owner.

---

*AthenIQ · LearningOps · [Innotel Platform Stack](https://github.com/innotelinc/innotel-platform-stack)*
