<div align="center">

# 🎓 AthenIQ — Learn What's Real.

**Open-source learning platform (LMS) for universities, workforce development & training — self-hosted, Authentik-native, AI-classroom ready.**

AthenIQ is an open learning platform built on **Tutor (Open edX)** and
**OpenMAIC**, the multi-agent interactive classroom. One stack for course
authoring, enrollment, delivery, and AI-assisted learning — with every course
completion eligible for a **certificate signed through Signara** and trusted
through the Innotel Platform Stack.

[![CI](https://github.com/innotelinc/atheniq/actions/workflows/ci.yml/badge.svg)](https://github.com/innotelinc/atheniq/actions/workflows/ci.yml)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0-or-later-brightgreen.svg)](LICENSE)

</div>

> **About AthenIQ** — the self-hosted LMS for real institutions: the battle-tested
> Open edX course engine (via [Tutor](https://github.com/overhangio/tutor)) meets
> [OpenMAIC](https://github.com/THU-MAIC/OpenMAIC)'s generative multi-agent
> classrooms, with **Authentik** as the identity provider and **Signara**
> certifying course certificates. **Landing page:**
> [innotelinc.github.io/atheniq](https://innotelinc.github.io/atheniq)

---

## Why AthenIQ

| Problem | AthenIQ answer |
| --- | --- |
| Proprietary LMS lock-in and per-seat fees | Open source, self-hosted, unlimited learners |
| Dull, static courseware | OpenMAIC classrooms: AI teachers, classmates, quizzes, simulations |
| Identity you don't control | Authentik-native SSO — OIDC, OAuth2, SAML, MFA, RBAC, SCIM |
| Credentials nobody trusts | Completion flows straight into Signara for signed course certificates |
| AI model lock-in | Every model call routes through OmniRoute — one gateway, many providers |
| Media tools scattered | Open Generative AI (MuAPI studio) for course imagery, video, and voice |
| Fragile realtime sessions | Self-hosted Convex for live presence, discussion, and progress sync |

## What it is

- **LMS core (Tutor / Open edX)** — enrollments, courseware, assessments,
  grading, learner records, and Studio authoring on the most widely deployed
  open LMS.
- **Generative interactive classrooms (OpenMAIC)** — one prompt or uploaded
  material becomes a multi-agent lesson: slides, quizzes, interactive HTML
  simulations, project-based learning, AI teachers and classmates who talk,
  draw, and discuss.
- **Realtime layer (Convex, self-hosted)** — presence, chat, live quizzes, and
  moment-by-moment learner progress for classroom sessions and study groups.
- **Course media studio (Open Generative AI)** — self-hosted image, video, and
  lip-sync generation for courseware authors.
- **Agent layer (OpenClaw + OpenClaude via OmniRoute)** — assistant
  integrations (Slack, Telegram, Discord and more), an OpenMAIC skill, and a
  CLI agent for authoring and operations — all models routed through one
  OpenAI-compatible gateway.
- **Signed certificates (Signara, live)** — the cert bridge
  (`scripts/cert-bridge.py`) watches Open edX for issued certificates and
  pushes each completion into Signara's signing workflow, producing
  audit-trailed, verifiable signed certificates.
- **The whole Innotel stack behind it** — Authentik (identity), Infisical
  (secrets), Cerulean (DNS + TLS), ONYX (storage), Magnate (revenue).

## 🚀 Quick start

```bash
git clone https://github.com/innotelinc/atheniq.git
cd atheniq
./setup.sh        # installs guard hooks, generates .env secrets, prints the checklist
```

### 1. LMS core — Tutor (Open edX)

```bash
python3 -m pip install tutor
tutor local quickstart        # interactive first boot of LMS + Studio
```

Tutor owns its own containers; AthenIQ configures it for this ecosystem
(domain, Authentik OIDC, theme). See [docs/Deployment.md](docs/Deployment.md).

### 2. AI classroom — OpenMAIC (with server-backed persistence)

```bash
git clone https://github.com/THU-MAIC/OpenMAIC.git ./services/OpenMAIC
cd services/OpenMAIC
cp .env.example .env.local    # add model providers, point at OmniRoute
docker compose --profile server-persistence up --build
```

### 3. Realtime + AI services on this repo's compose

```bash
cp .env.example .env
docker compose --profile gateway up -d      # OmniRoute model gateway
docker compose --profile openmaic up -d      # OpenMAIC Postgres persistence
```

Full bring-up order, Authentik/Cerulean/Signara wiring, and the Convex
self-hosted backend are in [docs/Deployment.md](docs/Deployment.md) and
[docs/Integrations.md](docs/Integrations.md).

## Technology stack

| Layer | Technology |
| --- | --- |
| LMS core | Tutor (Dockerized Open edX — LMS, Studio/CMS, XBlocks) |
| AI classroom | OpenMAIC (multi-agent interactive classroom, MIT) |
| Realtime state | Convex (self-hosted backend) |
| Media generation | Open Generative AI (MuAPI studio) |
| Agent layer | OpenClaw · OpenClaude · OmniRoute (OpenAI-compatible gateway) |
| Identity | Authentik (OIDC / OAuth2 / SAML / SCIM / MFA) |
| Secrets | Infisical (SecretOps — `.env` is derived) |
| Trust / DNS / TLS | Cerulean (TrustOps) |
| Storage | ONYX (StorageOps) |
| Revenue | Magnate (RevenueOps — paid courses, entitlements) |
| Certificates | Signara (DocumentOps — signed course certificates) |
| Deployment | Docker Compose + Tutor CLI + NGINX Proxy Manager |

## 📚 Documentation

| Document | Purpose |
| --- | --- |
| [docs/stack.md](docs/stack.md) | AthenIQ's role in the Innotel Platform Stack (LearningOps) |
| [docs/Architecture.md](docs/Architecture.md) | System design, components, data flows |
| [docs/Integrations.md](docs/Integrations.md) | Tutor, OpenMAIC, Convex, Open Generative AI, OpenClaw/OmniRoute, Authentik, Signara |
| [docs/Deployment.md](docs/Deployment.md) | Bring-up runbook, Cerulean DNS/TLS, production notes |

## Repository layout

```
atheniq/
├── docs/                      # Architecture, Integrations, Deployment, stack role
├── web/landing/               # Static GitHub Pages landing page
├── .github/workflows/         # CI, attribution guard, Pages publish
├── .githooks/                 # Local attribution guard (shared with CI)
├── docker-compose.yml         # AI services: OmniRoute gateway, OpenMAIC Postgres
├── scripts/                   # setup.sh, commit-message policy
├── .env.example               # Environment template (never commit .env)
└── Makefile                   # Operator workflow
```

## Development & operations

```bash
make help        # every target, one view
make setup       # hooks + .env + preflight
make gateway:up  # OmniRoute model gateway
make openmaic:up # OpenMAIC persistence Postgres
make check:commits
```

## Hosted landing page

The project landing page is published through GitHub Pages at
[https://innotelinc.github.io/atheniq/](https://innotelinc.github.io/atheniq/),
maintained in [web/landing/index.html](web/landing/index.html) and deployed by
[.github/workflows/pages.yml](.github/workflows/pages.yml).

## Community & contribution

- Report issues: https://github.com/innotelinc/atheniq/issues
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)

## Security

Found a vulnerability? Do **not** open a public issue — see the responsible
disclosure notes in [docs/Deployment.md](docs/Deployment.md#security).

---

*AthenIQ — Learn What's Real. © 2026*

## 🏛️ Platform stack

AthenIQ is the ecosystem's **LearningOps** platform — courses, delivery, and
AI classrooms in the [**Innotel Platform Stack**](https://github.com/innotelinc/innotel-platform-stack) —
the canonical single-responsibility architecture where Authentik owns identity,
Infisical owns secrets, Cerulean owns trust, ONYX owns storage, Magnate owns
revenue, and every other platform is a business function that consumes them.

---

## License

AthenIQ is licensed under the GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See [LICENSE](LICENSE) for the full text.

See [docs/stack.md](docs/stack.md) for this platform's owns/consumes boundaries.
