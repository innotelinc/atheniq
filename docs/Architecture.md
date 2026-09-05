# AuthenIQ — Architecture

AuthenIQ is the **LearningOps** platform of the Innotel Platform Stack: an
open learning platform whose LMS core, generative classrooms, realtime layer,
media studio, and agent layer are assembled from self-hosted open-source
projects and bound together by the stack's platform services (Authentik,
Infisical, Cerulean, ONYX, Magnate, Signara).

## System overview

```
                 LEARNERS / INSTRUCTORS / ADMINISTRATORS
                                   │
                                   ▼  (Authentik SSO — OIDC)
                 ┌───────────────────────────────────────────────┐
                 │                AUTHENTIK                      │
                 │   IdentityOps — users, groups, MFA, SCIM      │
                 └───────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────────┐
          ▼                        ▼                            ▼
┌────────────────────┐   ┌────────────────────┐   ┌────────────────────────┐
│   TUTOR / Open edX │   │      OpenMAIC      │   │  OpenClaw · OpenClaude │
│  LMS + Studio (CMS)│   │  AI classrooms     │   │  agent layer           │
│  catalog, enroll,  │   │  slides, quizzes,  │   │  skills, chat channels │
│  grade, records    │   │  sims, PBL         │   └───────────┬────────────┘
└─────────┬──────────┘   └─────────┬──────────┘               │
          │                        │                          │
          │        ┌───────────────┴──────────────┐           │
          │        ▼                              ▼           ▼
          │  ┌──────────────────┐   ┌─────────────────────────────┐
          │  │  CONVEX (self-   │   │   OMNIROUTE (OpenAI-compat)  │
          │  │   hosted)        │   │   model gateway — providers  │
          │  │  realtime state, │   │   OpenMAIC + agents share it │
          │  │  presence, chat  │   └─────────────────────────────┘
          │  └──────────────────┘
          │
          ▼   completion events
┌───────────────────────────────────────────────┐
│  SIGNARA (DocumentOps) — signed course certs  │
└───────────────────────────────────────────────┘

Platform services consumed throughout:
  Infisical (secrets) · Cerulean (DNS/TLS) · ONYX (storage) · Magnate (revenue)
```

## Components

| Component | Role | Notes |
| --- | --- | --- |
| Tutor / Open edX | LMS core | Course catalog, enrollment, courseware, assessments, grading, learner records. Tutor runs its own containers (`tutor local`); this repo configures and operates it. |
| OpenMAIC | AI classroom | Multi-agent lesson generation (slides, quizzes, simulations, PBL) with AI teachers/classmates. Runs from its upstream repo (`docker compose --profile server-persistence`). |
| Convex (self-hosted) | Realtime layer | Presence, chat, live quiz state, progress sync for classrooms and study groups. Backend on `:3210`, HTTP actions `:3211`, dashboard `:6791`. |
| Open Generative AI | Media studio | Course image/video/lip-sync generation (MuAPI-powered) for Studio authors. |
| OmniRoute | Model gateway | OpenAI-compatible endpoint (`:20128`) pooling model providers; the single model exit for OpenMAIC and the agent layer. |
| OpenClaw | Assistant gateway | Sessions, tools, events, channels (Slack, Telegram, Discord…); runs the OpenMAIC skill. |
| OpenClaude | Agent CLI | CLI agent for authoring/operations tasks, pointed at the OmniRoute endpoint. |
| Signara | Certificate signing | Receives completion records and returns signed course certificates. |
| Authentik | Identity | OIDC/OAuth2/SAML/MFA/SCIM for every surface above. |
| Infisical | Secrets | Provider keys and OAuth secrets; `.env` is derived, never committed. |
| Cerulean | Trust | DNS records, NGINX Proxy Manager hosts, and TLS certificates for every public host. |
| ONYX | Storage | Object storage and backups for courseware media. |
| Magnate | Revenue | Paid courses, subscriptions, and entitlements (group-gated access). |

## Data flows

### Identity
Learner → Authentik (OIDC) → Tutor LMS and OpenMAIC exchange the same
session/group claims. Enrollment groups (`learners`, `instructors`,
`authentiq-admins`) live in Authentik; disabling a user removes them from every
surface at once.

### Enrollment → delivery
Learner enrolls (via catalog, or a Magnate entitlement) in Tutor → course runs
link OpenMAIC classroom sessions → live session state (presence, chat, quiz
answers) syncs through self-hosted Convex → progress writes back to Open edX
gradebook.

### Model traffic
OpenMAIC lessons and agent-layer requests call the OmniRoute endpoint
(`OMNIROUTE_BASE_URL`), which routes to whichever provider accounts the
operator has connected — no per-surface model keys, no cloud dependency.

### Completion → certificate
Course completion in Open edX emits a completion event → AuthenIQ prepares a
completion record (learner, course, score, date, issuer) → Signara signs the
course certificate through its signature workflows → the signed artifact is
stored and returned to the learner record.

### Media
Authors generate courseware media through the self-hosted Open Generative AI
studio; finished assets land in ONYX object storage and are referenced by
Studio courseware.

## Security boundaries

1. **Identity boundary** — passwords and groups exist only in Authentik; Tutor,
   OpenMAIC, Convex, and the agent layer bind via OIDC/OAuth2.
2. **Secret boundary** — provider keys and OAuth secrets live in Infisical;
   `.env` files are derived and gitignored.
3. **Trust boundary** — every public host is fronted by NGINX Proxy Manager with
   Cerulean-issued TLS; nothing is published plaintext.
4. **Network boundary** — Convex, the model gateway, and Postgres stay on
   private/internal addresses; only canonical subdomains are proxied.
5. **Certificate boundary** — certificates are *signed* through Signara's
   audited signature workflows, never by AuthenIQ itself; AuthenIQ only emits
   completion evidence.
6. **Commit boundary** — the attribution guard runs locally and in CI.

## Deployment topology

```
internet ──► NGINX Proxy Manager (Cerulean-provisioned)
              ├── learn.<domain>      → Tutor LMS
              ├── studio.<domain>     → Open edX Studio
              ├── classroom.<domain>  → OpenMAIC
              └── certs.<domain>      → Signara portal (shared)
host network (private)
  ├── OmniRoute        :20128   (model gateway)
  ├── Convex backend   :3210    (realtime)
  ├── Convex dashboard :6791
  ├── OpenMAIC Postgres (profile)
  └── Tutor's own compose network (managed by Tutor CLI)
```

See [docs/Deployment.md](Deployment.md) for the bring-up runbook and
[docs/Integrations.md](Integrations.md) for per-component configuration.
