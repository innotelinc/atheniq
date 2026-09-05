# AuthenIQ — Integrations

AuthenIQ integrates upstream open-source projects rather than re-implementing
them. Each section states what the project is, why AuthenIQ uses it, and how it
is configured. Environment variables are defined in [.env.example](../.env.example);
secrets come from Infisical at production bring-up.

## Tutor (Open edX) — the LMS core

**Upstream:** https://github.com/overhangio/tutor · AGPL-3.0

Tutor is the Dockerized distribution of Open edX (LMS + Studio/CMS). AuthenIQ
uses it as the authoritative course engine: catalog, enrollment, courseware,
assessments, grading, and learner records.

- Install: `python3 -m pip install tutor`
- Bring up: `tutor local quickstart` (interactive) or `tutor local launch`
- Tutor owns its compose project; this repository configures and operates it.
- Integration points:
  - **Authentik OIDC** — configure Tutor's LMS OAuth/OIDC settings against the
    Authentik application (`auth.<domain>/application/o/authentiq-lms/`).
  - **Domain/TLS** — set `LMS_HOST`, `CMS_HOST`, and the email/nginx settings so
    Cerulean-provisioned NGINX Proxy Manager hosts terminate TLS and forward.
  - **Storage** — point uploaded courseware at ONYX S3-compatible storage via
    Open edX `DEFAULT_FILE_STORAGE` settings where media should not live on the
    LMS volume.
  - **Magnate** — paid enrollment uses Magnate webhooks → Authentik group
    membership → access in Tutor (same entitlement pattern as the rest of the
    stack).
- Tutor keeps its own upgrade path (`tutor local upgrade`); consult upstream
  release notes before major bumps.

## OpenMAIC — generative interactive classroom

**Upstream:** https://github.com/THU-MAIC/OpenMAIC · MIT

OpenMAIC ("Open Multi-Agent Interactive Classroom") turns a topic or uploaded
document into an interactive lesson: slides, quizzes, HTML simulations,
project-based learning, and AI teachers/classmates. AuthenIQ embeds OpenMAIC
classrooms in courses and links them from Open edX units.

- Clone the upstream repo into `./services/OpenMAIC` at bring-up
  (`./setup.sh` prints the exact steps).
- Run with server-backed persistence so sessions survive restarts:

  ```bash
  cp .env.example .env.local
  # DATABASE_URL / PERSISTENCE_DEV_TOKEN appended as documented upstream
  docker compose --profile server-persistence up --build
  ```

- **Model providers:** OpenMAIC is provider-neutral. Point it at the OmniRoute
  gateway (`OMNIROUTE_BASE_URL`, OpenAI-compatible) so classrooms use the same
  pooled providers as the rest of the stack. Local options (Ollama, Lemonade)
  are supported when a fully offline classroom is required.
- **Realtime:** self-hosted Convex (below) supplies presence/chat state that
  classroom pages subscribe to.
- **Protection:** set `ACCESS_CODE` for site-level gate on shared deployments.
- **Agent skill:** OpenMAIC ships a standard skill package for OpenClaw and
  other workbenches, so classrooms can be requested from chat channels.

## Convex (self-hosted backend) — realtime state

**Upstream:** https://github.com/get-convex/convex-backend (self-hosted README)

Convex provides reactive database/state functions. AuthenIQ uses a self-hosted
backend as the realtime substrate for live classrooms and study groups:
presence, chat, live quizzes, and moment-by-moment progress.

- Fetch the official self-hosted `docker-compose.yml` from the upstream
  `self-hosted/docker/` directory and run it (backend `:3210`, HTTP actions
  `:3211`, dashboard `:6791`).
- Generate an admin key: `docker compose exec backend ./generate_admin_key.sh`
- Configure the frontend/CLI:

  ```env
  CONVEX_SELF_HOSTED_URL=http://127.0.0.1:3210
  CONVEX_SELF_HOSTED_ADMIN_KEY=<admin key>
  ```

- Production notes: SQLite is the default store — move to Postgres/MySQL and
  S3-backed storage per the upstream advanced guides before heavy workloads.
- Convex Auth is not supported on self-hosted deployments; bind app-level auth
  to Authentik OIDC instead.

## Open Generative AI — course media studio

**Upstream:** https://github.com/anil-matcha/open-generative-ai

A free, open-source image/video/cinema/lip-sync studio (MuAPI-powered). Studio
authors use it to produce course thumbnails, explainer visuals, and short
lesson media without leaving the platform.

- Self-host the studio per its upstream README and expose it at
  `studio-media.<domain>` (or keep it author-only on the LAN).
- Finished assets are exported to ONYX object storage and referenced by Open
  edX Studio courseware.
- `OPEN_GENERATIVE_AI_URL` in `.env` points the authoring workflow at the
  studio API.

## OpenClaw · OpenClaude · OmniRoute — agent layer

- **OmniRoute** — https://github.com/diegosouzapw/OmniRoute. Self-hosted,
  OpenAI-compatible model gateway. One endpoint pools the provider accounts the
  operator connects. AuthenIQ runs it from this repo:

  ```bash
  docker compose --profile gateway up -d
  # http://127.0.0.1:20128/v1  (OMNIROUTE_BASE_URL), dashboard on :20128
  ```

- **OpenClaw** — https://github.com/openclaw/openclaw. Assistant gateway for
  sessions, tools, events, and channels. AuthenIQ uses OpenClaw with the
  **OpenMAIC skill** so instructors can request classrooms from Slack,
  Telegram, Discord, or other channels.
- **OpenClaude** — https://github.com/Gitlawb/openclaude. CLI agent for
  authoring and operations tasks. Point it at the OmniRoute endpoint
  (`OMNIROUTE_BASE_URL` + `OMNIROUTE_API_KEY`) so it shares the same pool.

OpenMAIC, OpenClaw, and OpenClaude all speak the OpenAI-compatible protocol, so
OmniRoute is the single model exit: one set of provider credentials in the
gateway, none in the learners' path.

## Authentik — identity (IdentityOps)

Every surface consumes the same Authentik tenant:

- OIDC applications for `authentiq-lms` (Tutor), `authentiq-classroom`
  (OpenMAIC), and the agent/studio consoles.
- Groups: `authentiq-admins`, `instructors`, `learners`, `paid_users`
  (Magnate-managed).
- Disable a user in Authentik → immediate loss of access everywhere.

## Signara — signed course certificates (DocumentOps)

Completion → certificate flow:

1. Open edX emits a course-completion event.
2. AuthenIQ builds a completion record: learner identity (from Authentik),
   course, final score, completion date, issuer.
3. The record is submitted to Signara, which runs its signature workflow and
   returns the signed course certificate.
4. The signed artifact is stored (ONYX) and linked from the learner record in
   the LMS; the learner can verify it through Signara's audit trail.

AuthenIQ never signs certificates itself — it only produces completion
evidence. Signara remains the sole DocumentOps surface of the stack.

## Cerulean — DNS, hosts, TLS (TrustOps)

As usual for stack platforms, public hosts are provisioned through Cerulean:
DNS records into BIND, NGINX Proxy Manager proxy hosts, and Let's Encrypt
(wildcard) certificates. See [docs/Deployment.md](Deployment.md#cerulean-dns-and-tls).

## Environment reference

Full variable list with comments lives in [.env.example](../.env.example).
High-signal variables:

| Variable | Purpose |
| --- | --- |
| `OIDC_*` | Authentik OIDC application endpoints/client for the surfaces |
| `OMNIROUTE_BASE_URL` / `OMNIROUTE_API_KEY` / `OMNIROUTE_MODEL` | Model gateway endpoint, key, default model |
| `OPENMAIC_*` / `PERSISTENCE_*` | OpenMAIC persistence Postgres + tokens |
| `CONVEX_SELF_HOSTED_URL` / `CONVEX_SELF_HOSTED_ADMIN_KEY` | Self-hosted Convex endpoint + admin key |
| `OPEN_GENERATIVE_AI_URL` | Media studio API base |
| `SIGNARA_API_URL` / `SIGNARA_API_KEY` | Certificate signing submission |
| `CERULEAN_*` | DNS / NPM / TLS provisioning (TrustOps) |
| `INFISICAL_*` | SecretOps bootstrap values |
