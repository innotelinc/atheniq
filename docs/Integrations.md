# AthenIQ — Integrations

AthenIQ integrates upstream open-source projects rather than re-implementing
them. Each section states what the project is, why AthenIQ uses it, and how it
is configured. Environment variables are defined in [.env.example](../.env.example);
secrets come from **Cerulean Vault** (HashiCorp Vault, KV v2, hosted by
Cerulean) at production bring-up — `scripts/vault-migrate.py` moves this stack's
plaintext values into `cerulean/atheniq`, and `.env` must then carry the resolved
values (see [docs/stack.md](stack.md)).

## Tutor (Open edX) — the LMS core

**Upstream:** https://github.com/overhangio/tutor · AGPL-3.0

Tutor is the Dockerized distribution of Open edX (LMS + Studio/CMS). AthenIQ
uses it as the authoritative course engine: catalog, enrollment, courseware,
assessments, grading, and learner records.

- Install: `python3 -m pip install tutor`
- Bring up: `tutor local quickstart` (interactive) or `tutor local launch`
- Tutor owns its compose project; this repository configures and operates it.
- Integration points:
  - **Authentik OIDC** — configure Tutor's LMS OAuth/OIDC settings against the
    Authentik application (`auth.<domain>/application/o/atheniq-lms/`).
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
project-based learning, and AI teachers/classmates. AthenIQ embeds OpenMAIC
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

Convex provides reactive database/state functions. AthenIQ uses a self-hosted
backend as the realtime substrate for live classrooms and study groups:
presence, chat, live quizzes, and moment-by-moment progress.

- Run the in-repo profile (reviewed here, not fetched from upstream): the
  `convex` + `convex-dashboard` services in [docker-compose.yml](../docker-compose.yml)
  — backend `:3210`, HTTP actions `:3211`, dashboard `:6791`, both bound to
  loopback. Images default to `latest` and pin independently via
  `CONVEX_BACKEND_VERSION` / `CONVEX_DASHBOARD_VERSION`:

  ```bash
  make convex-up
  ```

- Generate an admin key from the **running** backend: `make convex-key` (only
  the backend can sign a valid one; it cannot be generated locally).
- Configure the frontend/CLI:

  ```env
  CONVEX_SELF_HOSTED_URL=http://127.0.0.1:3210
  CONVEX_SELF_HOSTED_ADMIN_KEY=<admin key>
  ```

- Production notes: SQLite is the default store — move to Postgres/MySQL and
  S3-backed storage per the upstream advanced guides before heavy workloads.
- Convex Auth is not supported on self-hosted deployments; bind app-level auth
  to Authentik OIDC instead.

## ONYX — object storage (StorageOps)

**Stack surface:** ONYX owns object storage for the whole platform; AthenIQ
consumes it and runs no storage of its own.

Classroom media (Convex's file storage) and courseware uploads belong on
ONYX's S3-compatible object store rather than a container-local volume.

- Set `ONYX_S3_ENDPOINT` (the objectstore's S3 surface —
  `storage.onyx.innotel.us`, or `http://<onyx-host>:2090` on the LAN),
  `ONYX_S3_ACCESS_KEY` / `ONYX_S3_SECRET_KEY` (ONYX's own
  `S3_ACCESS_KEY`/`S3_SECRET_KEY` pair), and the two bucket names in `.env`.
- Provision the buckets through the S3 API (SigV4, standard library only):

  ```bash
  make onyx-buckets   # create atheniq-files + atheniq-exports (idempotent)
  make onyx-check     # verify they are reachable (read-only)
  ```

  [`scripts/onyx-buckets.py`](../scripts/onyx-buckets.py) implements SigV4 from
  the spec, so no `aws`/`mc` client is required; `--dry-run` prints the plan and
  `--selftest` validates the config without touching the network. It checks the
  credentials with a `ListBuckets` probe first, so a wrong key is reported as
  "credentials rejected" rather than mistaken for a missing bucket.
- Then bring Convex up against ONYX (`make convex-up`); it reads the same
  `ONYX_S3_*` values for its file and export buckets. Leaving the endpoint blank
  is a supported state — Convex then keeps files on its own data volume.
- ONYX tiers a bucket `local` / `cloud` / `tiered` through its own control API;
  AthenIQ's two buckets are plain local buckets.

## Open Generative AI — course media studio

**Upstream:** https://github.com/anil-matcha/open-generative-ai

A free, open-source image/video/cinema/lip-sync studio (MuAPI-powered). Studio
authors use it to produce course thumbnails, explainer visuals, and short
lesson media without leaving the platform.

- Self-host the studio per its upstream README and expose it at
  `media.<domain>` (or keep it author-only on the LAN).
- Finished assets are exported to ONYX object storage and referenced by Open
  edX Studio courseware.
- `OPEN_GENERATIVE_AI_URL` in `.env` points the authoring workflow at the
  studio API.

## OpenClaw · OpenClaude · OmniRoute — agent layer

- **OmniRoute** — https://github.com/diegosouzapw/OmniRoute. The platform's
  OpenAI-compatible model gateway: one endpoint pools the provider accounts the
  operator connects. **AthenIQ runs none** — the single OmniRoute lives in Group 2
  (`2-voice/`), on the gateway host `192.168.1.46`, and the door to it is the SSO
  proxy in front (`:20129`); the gateway's own `:20128` answers on that host's
  loopback and bridge alone. There is no container to start here:

  ```bash
  # in .env
  OMNIROUTE_BASE_URL=http://192.168.1.46:20129/v1
  ```

- **OpenClaw** — https://github.com/openclaw/openclaw. Assistant gateway for
  sessions, tools, events, and channels. AthenIQ uses OpenClaw with the
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

- OIDC applications for `atheniq-lms` (Tutor), `atheniq-classroom`
  (OpenMAIC), and the agent/studio consoles.
- Groups: `atheniq-admins`, `instructors`, `learners`, `paid_users`
  (Magnate-managed).
- Disable a user in Authentik → immediate loss of access everywhere.

## Magnate — paid courses & entitlements (RevenueOps)

**Stack surface:** Magnate owns billing, plans, and entitlements for the whole
platform; AthenIQ never holds Stripe keys or a price.

Paid courses gate on a Magnate **plan entitlement**, checked server-to-server
with the shared bearer token (`ENTITLEMENTS_API_TOKEN` on Magnate):

```bash
make magnate-probe                                                    # reachability + token
python3 scripts/magnate-entitlements.py check --user learner@x.edu --plan premium
```

- `entitled: true` → AthenIQ grants access (enrollment mode, course visibility,
  or the `paid_users` Authentik group). `false` → it does not. Group membership
  stays Authentik's job; Magnate only reports the billing decision.
- The same token gates `POST /api/purchases`, AthenIQ's path to sell one course
  as a one-off hosted Checkout item without any Stripe key of its own:

  ```bash
  python3 scripts/magnate-entitlements.py buy \
    --course course-v1:Innotel+TEST101+2026_T1 \
    --name "TEST101 — certificate" --amount-cents 4900 --user learner
  ```

  The course key and username ride along in the item's `metadata`.
- Magnate's purchase-completion callback (`purchase.completed`, header
  `X-Magnate-Signature` = HMAC-SHA256 over the raw body) is a **single
  platform-wide hook** (`MAGNATE_PURCHASE_FULFILLMENT_URL` on Magnate), already
  claimed by another consumer in this estate. AthenIQ therefore treats the plan
  *entitlement* as the gate and does not depend on owning that hook; if it ever
  does, `magnate-entitlements.py verify-signature` validates the callback.
- Cancellation and expiry need no separate plumbing: when Magnate reports
  `entitled: false` (or the user leaves `paid_users`), paid-course access ends.
- **Enrolling the paid learner** — `scripts/paid-enrollment.py` turns the
  entitlement into an Open edX enrollment (mode `PAID_ENROLLMENT_MODE`, default
  `verified`), idempotently, and revokes it with `--revoke`. It reaches the LMS
  through the Tutor MySQL container the same way the cert bridge does, and
  ledgers every grant in `atheniq_paid_enrollment`:

  ```bash
  python3 scripts/paid-enrollment.py --user learner@x.edu \
      --course course-v1:Innotel+TEST101+2026_T1
  python3 scripts/paid-enrollment.py --status        # ledger health
  ```

- **Keeping group membership honest** — `scripts/entitlement-sync.py` walks the
  `learners` group in Authentik and adds or removes `paid_users` to match the
  plan entitlement, so a missed webhook, a restored database, or a manual plan
  change converges on the next pass. An entitlement it cannot determine changes
  nothing — an outage never revokes access. Run it on a timer via
  [`deploy/systemd/atheniq-entitlement-sync.timer`](../deploy/systemd/atheniq-entitlement-sync.timer):

  ```bash
  make entitlement-status   # learners / paid / plan counts, no writes
  make entitlement-sync     # dry run of the reconciliation
  ```

## Signara — signed course certificates (DocumentOps)

Completion → certificate flow (**implemented** by
[`scripts/cert-bridge.py`](../scripts/cert-bridge.py) — see
[docs/Deployment.md](Deployment.md#97-signara-signing-leg-cert-bridge)):

1. Open edX issues a course certificate (a `downloadable`
   `GeneratedCertificate` row) on course completion.
2. The cert bridge reads the completion record from the LMS DB: learner
   identity, course, final score, completion date, issuer.
3. The record is submitted to Signara (`X-API-Key` machine auth), which runs
   its signature workflow — document upload, signing request with the
   issuer/signatory as signer, signature — and returns the signed course
   certificate.
4. The signed artifact is stored in Signara's document store (MinIO) with a
   hash-bound evidence/audit trail the learner can verify in the Signara
   portal; ONYX object-storage mirroring is a later hardening phase.

The bridge keeps an idempotency ledger (`atheniq_cert_sync` in the LMS DB), so
certificates are signed exactly once and re-runs are safe.

AthenIQ never signs certificates itself — it only produces completion
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
| `ONYX_S3_ENDPOINT` / `ONYX_S3_ACCESS_KEY` / `ONYX_S3_SECRET_KEY` | ONYX S3-compatible endpoint + credential for classroom media (`make onyx-buckets`) |
| `ONYX_S3_BUCKET_FILES` / `ONYX_S3_BUCKET_EXPORTS` | Convex's ONYX buckets (default `atheniq-files` / `atheniq-exports`) |
| `MAGNATE_API_URL` / `MAGNATE_ENTITLEMENTS_TOKEN` | Magnate base URL + shared entitlement/purchase bearer token |
| `MAGNATE_PAID_PLAN` | Plan slug that gates paid courses/tracks |
| `PAID_ENROLLMENT_MODE` | Open edX enrollment mode granted on entitlement (default `verified`) |
| `AUTHENTIK_API_URL` / `AUTHENTIK_API_TOKEN` | Authentik API access for the paid-access reconciler |
| `OPEN_GENERATIVE_AI_URL` | Media studio API base |
| `SIGNARA_API_URL` / `SIGNARA_API_KEY` | Certificate signing submission (machine auth via `X-API-Key`) |
| `CERT_SIGNER_NAME` / `CERT_SIGNER_EMAIL` / `CERT_SIGNER_TITLE` | Issuer/signatory on certificate signing requests |
| `CERULEAN_*` | DNS / NPM / TLS provisioning (TrustOps) |
| `VAULT_*` | SecretOps bootstrap values (`VAULT_ADDR`, the path-scoped `VAULT_TOKEN_FILE`, `VAULT_PREFIX`, `VAULT_PATH`) |
