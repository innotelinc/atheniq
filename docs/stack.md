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

Cerulean mints this stack's **path-scoped** token (its policy covers only
`cerulean/data/atheniq`, never a sibling's secrets) and renews it in place. Copy
it to `./data/vault/token/atheniq.token`, then move any plaintext values across:

```bash
VAULT_ADDR=http://<cerulean-host>:8200 \
  VAULT_TOKEN_FILE=./data/vault/token/atheniq.token \
  VAULT_PREFIX=cerulean VAULT_PATH=atheniq \
  python3 scripts/vault-migrate.py --from-env-file .env \
    --keys OMNIROUTE_API_KEY,OIDC_CLIENT_SECRET
```

`vault-migrate.py` never prints a value, unions with whatever is already at the
path (so a re-run is a no-op, not an overwrite), and accepts either `.env` or a
legacy Infisical workspace as its source.

A `vault://` value is the platform's reference *form*; it is resolved by whichever
layer consumes it (ONYX's Go services, Distro's Node control plane, Zeus at boot,
Atlas at setup). This repo has no resolver, so `.env` must hold the resolved
value — a reference left in place reaches the container as a literal string.
Generate local development values with `./setup.sh`; see
[docs/Deployment.md](Deployment.md).

## Golden rules

- **Authentik = Identity** · **Cerulean Vault = Secrets** · **Cerulean = Trust** ·
  **ONYX = Storage** · **Magnate = Revenue** — everything else is a business function.
- No platform duplicates another's responsibility.
- No credit in commits, footers, or headers to anyone but the project owner.

---

*AthenIQ · LearningOps · [Innotel Platform Stack](https://github.com/innotelinc/innotel-platform-stack)*
