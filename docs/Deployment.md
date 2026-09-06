# AuthenIQ — Deployment

This runbook brings up the AuthenIQ learning platform on one self-hosted host.
It is an operator-run flow: nothing in CI connects to or deploys any server.

## Prerequisites

- A Linux host (Debian/Ubuntu recommended) with Docker + Compose plugin,
  `python3`, `openssl`, `git`, and `curl`.
- A domain you control with a zone managed by **Cerulean** (BIND) so records
  and TLS are provisioned automatically. Reference DNS: `*.learn.<domain>`
  style hosts under your zone (see [Cerulean DNS and TLS](#cerulean-dns-and-tls)).
- **Authentik** tenant reachable for OIDC (IdentityOps) and **Infisical** for
  secrets (SecretOps), per the Innotel Platform Stack bring-up order.
- Disk headroom: Open edX images + learner media + OpenMAIC models and builds
  are large — plan for tens of GB on first boot.

## Stage 0 — bootstrap this repo

```bash
git clone https://github.com/innotelinc/authentiq.git
cd authentiq
./setup.sh
```

`setup.sh` is idempotent: it preflights the tools above, installs the local
attribution guard hooks, and (first run only) creates `.env` from
[.env.example](../.env.example) with generated secrets. It prints the stage
checklist below.

## Stage 1 — LMS core (Tutor / Open edX)

```bash
python3 -m pip install tutor
tutor config save --set LMS_HOST=learn.<domain> --set CMS_HOST=studio.<domain>
tutor local quickstart        # first boot (interactive); then:
tutor local launch            # idempotent full deployment on later runs
```

- Tutor runs its own compose project and volumes under the tutor root; keep
  this repo for the ecosystem glue, not Tutor's internals.
- Add the Authentik OIDC/SSO provider to the LMS per Stage 2.
- For uploaded courseware that should live on **ONYX**, configure Open edX
  storage settings to the ONYX S3-compatible endpoint (see
  [docs/Integrations.md](Integrations.md#tutor-open-edx--the-lms-core)).
- Upgrade path stays with Tutor: `tutor local upgrade` after reading upstream
  release notes.

## Stage 2 — Authentik OIDC applications

Create OIDC applications in the Authentik admin for each public surface:

| Surface | Redirect / provider hints |
| --- | --- |
| `authentiq-lms` | Tutor LMS + Studio OAuth callback |
| `authentiq-classroom` | OpenMAIC sign-in callback |
| `authentiq-studio` | Media studio (optional) |

**Realized (2026-09):** `authentiq-lms` is live on Cerulean's Authentik
(`auth.cerulean.innotel.us`, client id `authentiq-lms`). Open edX is enabled via
the Tutor plugin in [`contrib/tutor-ceruleansso`](../contrib/tutor-ceruleansso)
(installed as `tutor-ceruleansso` in the tutor venv): it sets
`FEATURES["ENABLE_THIRD_PARTY_AUTH"]`, registers python-social-auth's
`OpenIdConnectAuth` backend (`oidc`), and points
`SOCIAL_AUTH_OIDC_OIDC_ENDPOINT` at
`https://auth.cerulean.innotel.us/application/o/authentiq-lms`. The TPA
`ProviderConfig` row (site = default, backend `oidc`) holds the client id/secret;
Authentik redirect URIs are `https://learn.innotel.us/auth/complete/oidc/` and
`https://studio.innotel.us/auth/complete/oidc/` (strict). LMS verified:
auth entry redirects to Authentik authorize and returns to the login flow; the
container reaches Authentik discovery over the edge. Full browser sign-in needs
the `learn`/`studio.innotel.us` NPM edge hosts + DNS (see Stage 5).

Use the Authentik authorization/`userinfo` endpoints in `.env` (`OIDC_*`) and
apply the same group claims (`learners`, `instructors`, `authentiq-admins`,
`paid_users`) as the rest of the stack. See
[docs/Integrations.md](Integrations.md#authentik--identity-identityops).

## Stage 3 — AI classroom (OpenMAIC)

```bash
git clone https://github.com/THU-MAIC/OpenMAIC.git ./services/OpenMAIC
cd services/OpenMAIC
cp .env.example .env.local
# point models at OmniRoute (Stage 6) or add provider keys as usual
docker compose --profile server-persistence up --build
```

- Persistence Postgres runs on this repo's compose (Stage 3b) or you can let
  OpenMAIC's own profile manage it.
- Front OpenMAIC with NGINX Proxy Manager at `classroom.<domain>` (Cerulean
  provisions the host + TLS). Set `ACCESS_CODE` for shared deployments.

### Stage 3b — OpenMAIC persistence Postgres (this repo)

```bash
docker compose --profile openmaic up -d
```

## Stage 4 — Realtime (Convex, self-hosted)

```bash
curl -fsSL -o convex-compose.yml \
  https://raw.githubusercontent.com/get-convex/convex-backend/main/self-hosted/docker/docker-compose.yml
docker compose -f convex-compose.yml up -d
docker compose -f convex-compose.yml exec backend ./generate_admin_key.sh
```

Copy the admin key into `.env`:

```env
CONVEX_SELF_HOSTED_URL=http://127.0.0.1:3210
CONVEX_SELF_HOSTED_ADMIN_KEY=<admin key>
```

Dashboard: `http://<host>:6791`. For production workloads, follow the upstream
advanced guides to move the store to Postgres/MySQL and files to S3. Convex
Auth is not supported self-hosted — keep app auth on Authentik OIDC.

## Stage 5 — Course media studio (Open Generative AI, optional)

Self-host the studio from https://github.com/anil-matcha/open-generative-ai and
set `OPEN_GENERATIVE_AI_URL`. Keep it author-only (LAN or a proxied
`media.<domain>` host) — learners do not need direct access.

## Stage 6 — Model gateway and agents

```bash
docker compose --profile gateway up -d     # OmniRoute on 127.0.0.1:20128
```

1. Open the OmniRoute dashboard at `http://127.0.0.1:20128` and connect the
   provider accounts the platform may use.
2. Set `OMNIROUTE_BASE_URL=http://127.0.0.1:20128/v1`, `OMNIROUTE_API_KEY`, and
   `OMNIROUTE_MODEL` in `.env`.
3. OpenMAIC reads the same endpoint, so classrooms and agents share the pool.
4. For chat-driven classrooms, run **OpenClaw** with the OpenMAIC skill, and
   point the **OpenClaude** CLI at the OmniRoute endpoint for authoring tasks
   (see [docs/Integrations.md](Integrations.md#openclaw--openclaude--omniroute--agent-layer)).

## Stage 7 — Signed certificates (Signara)

1. In the Signara portal, create the signature workflow/template for course
   certificates and an API token for AuthenIQ.
2. Set `SIGNARA_API_URL` and `SIGNARA_API_KEY` in `.env`.
3. Completion events in Open edX flow to Signara and return signed certificates
   as described in [docs/Integrations.md](Integrations.md#signara--signed-course-certificates-documentops).

## Cerulean DNS and TLS

Public hosts are provisioned through Cerulean as usual for stack platforms:

- Cerulean writes DNS records (A/CNAME) into your BIND zone and requests
  Let's Encrypt certificates (regular or wildcard via DNS-01).
- NGINX Proxy Manager hosts are created automatically for each canonical
  subdomain, with TLS termination at NPM.

Canonical hosts for a reference deployment:

| Host | Backend |
| --- | --- |
| `learn.<domain>` | Tutor LMS |
| `studio.<domain>` | Open edX Studio |
| `classroom.<domain>` | OpenMAIC |
| `cert.<domain>` | Signara portal (shared DocumentOps) |

Set the `CERULEAN_*` variables in `.env` (`CERULEAN_BASE_DOMAIN`,
`CERULEAN_ZONE`, API URL/password, WAN discovery) before running any
Cerulean provisioning. Docker/LAN addresses are never published to DNS; only
the public WAN address is used for records and the LAN address for NPM
upstreams.

## Operations

- **Backups:** Tutor volumes and the OpenMAIC/Convex Postgres databases are the
  state you must protect. Dump Postgres (`pg_dump`) on a schedule and mirror
  dumps plus courseware media to **ONYX** object storage (off-host).
- **Logs:** `docker compose logs -f` for this repo's services; `tutor local
  logs` for the LMS; retain learner-access audit trails per your policy.
- **Health:** check `/healthz` surfaces where available; confirm NPM hosts and
  certificate renewal via Cerulean's compliance view.
- **Upgrades:** Tutor has its own upgrade command; OpenMAIC, Convex, OmniRoute,
  and the agent layer follow upstream releases. Test on a staging host first.
- **Rollback:** keep previous container images and DB dumps; restore =
  recreate volumes from the last good dump, then relaunch the same image tags.

## Security

- Found a vulnerability? Do **not** open a public issue. Report it privately to
  the repository owner (`dhunter@innotel.us`) with the affected version and
  reproduction steps.
- The stack security boundaries (identity, secrets, trust, network,
  certificates, commits) from [docs/Architecture.md](Architecture.md#security-boundaries)
  apply to every deployment. In particular, AuthenIQ never signs certificates
  itself — Signara does — and no `.env`, key, or token is ever committed.
