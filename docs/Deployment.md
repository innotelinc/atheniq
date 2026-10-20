# AthenIQ — Deployment

This runbook brings up the AthenIQ learning platform on one self-hosted host.
It is an operator-run flow: nothing in CI connects to or deploys any server.

## Prerequisites

- A Linux host (Debian/Ubuntu recommended) with Docker + Compose plugin,
  `python3`, `openssl`, `git`, and `curl`.
- A domain you control with a zone managed by **Cerulean** (Technitium) so records
  and TLS are provisioned automatically. Reference DNS: `*.learn.<domain>`
  style hosts under your zone (see [Cerulean DNS and TLS](#cerulean-dns-and-tls)).
- **Authentik** tenant reachable for OIDC (IdentityOps) and **Cerulean Vault** for
  secrets (SecretOps), per the Innotel Platform Stack bring-up order.
- Disk headroom: AthenIQ images + learner media + OpenMAIC models and builds
  are large — plan for tens of GB on first boot.

## Stage 0 — bootstrap this repo

```bash
git clone https://github.com/innotelinc/atheniq.git
cd atheniq
./setup.sh
```

`setup.sh` is idempotent: it preflights the tools above, installs the local
attribution guard hooks, and (first run only) creates `.env` from
[.env.example](../.env.example) with generated secrets. It prints the stage
checklist below.

## Stage 1 — LMS core (Tutor)

```bash
python3 -m pip install tutor
tutor config save --set LMS_HOST=learn.<domain> --set CMS_HOST=studio.<domain>
tutor local quickstart        # first boot (interactive); then:
tutor local launch            # idempotent full deployment on later runs
```

- Tutor runs its own compose project and volumes under the tutor root; keep
  this repo for the ecosystem glue, not Tutor's internals.
- Add the Authentik OIDC/SSO provider to the LMS per Stage 2.
- For uploaded courseware that should live on **ONYX**, configure AthenIQ
  storage settings to the ONYX S3-compatible endpoint (see
  [docs/Integrations.md](Integrations.md#tutor--the-lms-core)).
- Upgrade path stays with Tutor: `tutor local upgrade` after reading upstream
  release notes.
- Courseware authored in this repo under `courses/` imports into Studio as OLX;
  the full walkthrough (and the ITSP101 certification course) is in
  [`courses/it-support-certification/README.md`](../courses/it-support-certification/README.md).
  `make check-courses` lints those packages in CI, and `make course-bundle` builds
  each as a `.tar.gz` artifact. The course org slug is **`InnotelLabs`** (the
  Innotel Labs brand); re-import runs created under the older `Innotel` org under
  the new key. `make course-import` bundles and imports every package into the
  running CMS (preview first with `python3 scripts/import-courses.py`), and
  `make course-bundle` writes the `dist/courses/*.tar.gz` archives without touching
  the LMS. Each package ships its course card as a rendered PNG
  (`static/<slug>-course-card.png`, the policy's `course_image`), because the Open
  edX course card does not render SVG; `make images` regenerates the rasters and
  `make check-images` verifies them in CI (`pip install Pillow` is the only extra
  dependency). See [`docs/Brand.md`](Brand.md) for the asset set.
- To converge the LMS on the repo's courseware automatically, install the import
  timer (daily, and on boot):

  ```bash
  sudo cp deploy/systemd/atheniq-course-import.service deploy/systemd/atheniq-course-import.timer /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl enable --now atheniq-course-import.timer
  journalctl -u atheniq-course-import.service -n 20   # watch runs
  ```

  The unit runs `scripts/import-courses.py --execute` **then**
  `scripts/track-gating.py --apply` (oneshot) each tick; an invalid package is
  refused, and re-importing a course under the same `course-v1:` key updates it in
  place. The second step is required, not cosmetic: a (re-)import rebuilds the
  course block from the OLX, which does not carry `pre_requisite_courses`, so an
  import on its own clears the workforce-track gate. Doing both in one unit keeps
  a re-import from silently un-gating the tracks — see
  [docs/WorkforceTracks.md](WorkforceTracks.md#gating-a-ladder-the-lms-enforces).

## Stage 2 — Authentik OIDC applications

Create OIDC applications in the Authentik admin for each public surface:

| Surface | Redirect / provider hints |
| --- | --- |
| `atheniq-lms` | Tutor LMS + Studio OAuth callback |
| `atheniq-classroom` | OpenMAIC sign-in callback |
| `atheniq-studio` | Media studio (optional) |

**Realized (2026-09):** `atheniq-lms` is live on Cerulean's Authentik
(`auth.cerulean.innotel.us`, client id `atheniq-lms`). AthenIQ is enabled via
the Tutor plugin in [`contrib/tutor-ceruleansso`](../contrib/tutor-ceruleansso)
(installed as `tutor-ceruleansso` in the tutor venv): it sets
`FEATURES["ENABLE_THIRD_PARTY_AUTH"]`, registers python-social-auth's
`OpenIdConnectAuth` backend (`oidc`), and points
`SOCIAL_AUTH_OIDC_OIDC_ENDPOINT` at
`https://auth.cerulean.innotel.us/application/o/atheniq-lms`. The TPA
`ProviderConfig` row (site = default, backend `oidc`) holds the client id/secret;
Authentik redirect URIs are `https://learn.innotel.us/auth/complete/oidc/` and
`https://studio.innotel.us/auth/complete/oidc/` (strict). `lms.innotel.us` is
registered as well, so a sign-in started on the alias still completes. LMS
verified: auth entry redirects to Authentik authorize and returns to the login
flow; the container reaches Authentik discovery over the edge. Full browser
sign-in needs the `learn`/`studio.innotel.us` NPM edge hosts + DNS (see
[Cerulean DNS and TLS](#cerulean-dns-and-tls)).

Use the Authentik authorization/`userinfo` endpoints in `.env` (`OIDC_*`) and
apply the same group claims (`learners`, `instructors`, `atheniq-admins`,
`paid_users`) as the rest of the stack. See
[docs/Integrations.md](Integrations.md#authentik--identity-identityops).

### Branding — the platform is AthenIQ

The platform presents as **AthenIQ** (see [docs/Brand.md](Brand.md)):

```bash
tutor config save --set PLATFORM_NAME=AthenIQ   # titles, emails, welcome, MFE SITE_NAME
tutor local restart lms cms                       # apply the regenerated config
```

`PLATFORM_NAME` lands in the mounted `lms.env.yml` / `cms.env.yml`, so a restart
applies it without an image rebuild. It also flows into the MFEs' runtime config
(`/api/mfe_config/v1` reports `SITE_NAME: AthenIQ`).

The Indigo theme additionally hard-codes "Powered by: Tutor + Open edX" in its
footer and an edX trademark paragraph, and ships the upstream header logo and
favicon. [`contrib/atheniq-theme`](../contrib/atheniq-theme) holds clean
replacements — the footer/overlay templates plus the generated
`logo.png` / `logo-white.png` / `favicon.ico` (render them with `make images`).
Apply them to the running LMS with:

```bash
make theme        # == ./scripts/apply-atheniq-theme.sh
```

The copies live in the container's writable layer — re-run the script after a
container recreate, or fold them into a Tutor theme plugin before a rebuild.

> **The learner MFEs** (catalog, learning, profile) render their own footer from
compiled JS bundles. Indigo installs its footer into the frontend-plugin-framework
footer slot and that footer still prints the Tutor + Open edX logos. The
[`contrib/tutor-atheniq-mfe`](../contrib/tutor-atheniq-mfe) plugin replaces that
slot widget with the AthenIQ lockup; because the MFE footer is compiled, it needs
`tutor images build mfe` (see [docs/Brand.md](Brand.md)).

The same plugin also installs the platform nav in the MFE header — **Courses ·
Programs · Classrooms · Studio · Platform** — opening `ai.lms.innotel.us` on the
Authentik session the LMS already has, so it is a click, not a second sign-in.
On the authoring app it adds the create row the platform actually needs
(**+ New Program · + New Course · + New Classroom · + New Library**) in the page
banner; the stock page still renders its own heading and single "+ New course"
button, which only a fork of the authoring app can remove.

### One session across Studio, the LMS and the MFEs

Tutor gives each service its own host cookie, so `learn.innotel.us` and
`studio.innotel.us` each asked for a sign-in even though Authentik already knew
the learner. `ATHENIQ_SESSION_COOKIE_DOMAIN` (in `contrib/tutor-atheniq-hosts`)
fixes that at the Open edX layer:

```bash
tutor config save --set ATHENIQ_SESSION_COOKIE_DOMAIN=.innotel.us
tutor local restart lms cms        # settings patches apply on restart, no rebuild
```

Both the LMS and the CMS then set `sessionid` / `csrftoken` on `.innotel.us`
with `SameSite=Lax`, so every Open edX name reads the same session. Verified
live: `set-cookie: sessionid=…; Domain=.innotel.us; SameSite=Lax; Secure`.
Leaving the value empty keeps Tutor's per-host default; setting it sends one
cookie to every name under the domain, which is why it is configuration rather
than a plugin default.

This unifies the Open edX services only. `ai.lms.innotel.us` and
`classroom.innotel.us` sit behind their own `oauth2-proxy` instances with their
own Authentik clients, and two proxies with different clients cannot share a
cookie. One cookie across those needs one proxy in front of all of them (the
`cerulean-npm-sso` pattern, `--cookie-domain=.innotel.us`), not a second client. Build only the apps that need it: `tutor images
build mfe` compiles all thirteen in parallel and has taken a production node
down, while `docker build --target catalog-prod` (then `learning-prod`,
`learner-dashboard-prod`) plus a wrapper image that copies the new `/openedx/app/dist`
over `/openedx/dist/<app>` is one webpack build per page. The plugin's README has
the commands, including the rollback tag.

It also refreshes `caniuse-lite` at the `mfe-dockerfile-pre-npm-build` and
`mfe-dockerfile-pre-npm-build-site` hooks. Browserslist reads that snapshot from
the lockfile, which is months old by build time; `npm install
caniuse-lite@latest` fails there with `ERESOLVE`, so the hook unpacks the current
tarball over `$(pwd)/node_modules` instead. `$(pwd)` matters: the per-app stages
build in `/openedx/app`, the site stage in `/openedx/site`, and the site stage is
the one that actually compiles the bundles.

## Stage 3 — AI classroom (OpenMAIC)

```bash
git clone https://github.com/THU-MAIC/OpenMAIC.git ./services/OpenMAIC
cd services/OpenMAIC
cp .env.example .env.local
# point models at OmniRoute (Stage 6) or add provider keys as usual
docker compose up -d --build
# research and document parsing are separate projects on the classroom network
node scripts/vault-env.mjs --in .env.classroom-secrets.example \
    --out .env.classroom-secrets
docker compose --env-file .env.classroom-secrets -f docker-compose.websearch.yml up -d
docker compose -f docker-compose.mineru.yml up -d
```

The two extras are not part of `docker-compose.yml` (that file stays an
upstream checkout), so `docker compose up -d` alone does not start them. A
classroom whose research step answers `INTERNAL_ERROR: fetch failed` or whose
outline ends in a 503 usually has them stopped: check
`docker ps | grep -E 'searxng|mineru'` before blaming the model. Both carry
`restart: unless-stopped`, but a clean `docker compose stop` is remembered, so
they stay down until they are started again.

- Compose interpolation knobs live in `services/OpenMAIC/.env` —
  `OPENMAIC_PORT`, `OPENMAIC_PUBLISH_ADDRESS`, `PERSISTENCE_POSTGRES_PASSWORD`.
  Compose reads that file; `.env.local` is loaded into the container instead,
  so a value set in the wrong one is silently ignored.
- Persistence Postgres runs on this repo's compose (Stage 3b) or you can let
  OpenMAIC's own bundled `postgres` service manage it, which is the default and
  what `docker compose up -d --build` does.
- Front OpenMAIC with NGINX Proxy Manager at `classroom.<domain>` (Cerulean
  provisions the host + TLS). Set `ACCESS_CODE` for shared deployments, and
  publish beyond loopback (`OPENMAIC_PUBLISH_ADDRESS`) or the edge cannot reach
  it — the two go together.

### Classrooms inside a course unit

A course chapter can run as a live OpenMAIC classroom inside the LMS
(`courses/<slug>/openmaic/classrooms.json`). Two settings on the classroom host
make the embed work, and both are easy to miss:

- **Frame ancestors.** OpenMAIC sends `frame-ancestors 'self'` unless
  `ALLOWED_FRAME_ANCESTORS` names the LMS origins. It is a **build** arg (compose
  passes it into the image), not a runtime variable, so set it in
  `services/OpenMAIC/.env` and rebuild:

  ```
  ALLOWED_FRAME_ANCESTORS=https://learn.innotel.us https://apps.learn.innotel.us https://lms.innotel.us https://apps.lms.innotel.us https://atheniq.innotel.us
  docker compose build openmaic && docker compose up -d openmaic
  ```

  Every origin a course unit is served from has to be listed, canonical and
  alias alike: a learner who followed an old `lms` link is still the parent
  frame. Because the value is compiled into
  `.next/routes-manifest.json` (it is read by `next.config.ts`), a rebuild is
  the only way to change it — a running container keeps the allowlist it was
  built with, and a course unit embedded from an origin that is missing shows a
  blank frame with a CSP violation in the console.

  When a rename cannot wait for a rebuild (the box has no headroom for a Next
  build, which is what happened here), patch the running container and make the
  patch part of an image instead:

  ```bash
  # 1. edit the manifest inside the running container, restart, verify the header
  docker cp scripts/openmaic-csp-patch.js openmaic-openmaic-1:/tmp/patch.js
  docker exec -u root openmaic-openmaic-1 node /tmp/patch.js
  docker restart openmaic-openmaic-1
  # 2. keep it across recreates by committing the patched container as the
  #    image this compose project uses (keep the old one for rollback)
  docker tag "$(docker inspect -f '{{.Image}}' openmaic-openmaic-1)" openmaic-openmaic:pre-<change>
  docker commit openmaic-openmaic-1 openmaic-openmaic:latest
  cd services/OpenMAIC && docker compose up -d --no-build --force-recreate openmaic
  ```

  The source rebuild still wins in the end: `docker compose build openmaic`
  overwrites `openmaic-openmaic:latest` and bakes the value from `.env`.

  With it set, OpenMAIC omits `X-Frame-Options` and allows those origins in the
  CSP. The LMS sends no frame policy of its own.
- **Who may enter.** `classroom-sso` is an oauth2-proxy in front of the app. Its
  `--allowed-group` has to include the group your LMS learners hold (here
  `AthenIQ LMS` as well as `atheniq-admins`), or a signed-in learner is refused
  after the redirect.

Then generate and embed the classrooms from the course repository:

```bash
python3 scripts/build-classrooms.py            # plan: which chapters lack a classroom
python3 scripts/build-classrooms.py --execute  # generate them (one at a time)
python3 scripts/build-classrooms.py --inject   # write the embeds into the lesson units
python3 scripts/import-courses.py --execute --course <key>   # publish to the LMS
```

`--execute --publish` does the last three automatically as each classroom
finishes. The classroom id is written back into the spec, so a re-run only
handles what is still missing.

**A paused run is a model-supply failure.** The tool stops at the first one and
prints the step and the gateway's own error — an exhausted quota, a rate limit,
a provider with no credential — instead of waiting it out. Give it a chain of
gateway models to fall back through and it moves instead of stopping:

```bash
python3 scripts/build-classrooms.py --execute --publish \
  --models codex/gpt-5.6-luna-medium,auto/best-chat,auto/best-coding
```

A paused classroom is re-submitted on the next model after the tool points the
classroom's chat slots at it through OpenMAIC's model settings (`PUT
/api/model-config`, no rebuild), the model that works is reused for the rest of
the batch, and `--models` runs one classroom at a time because that setting is
workspace-wide. When the chain runs out the batch stops and says how many
classrooms it left — add a provider to the gateway (or wait for a quota window)
and run the same command again. `--max-resumes N` (default 0) resumes a paused
run in place instead, which is only worth it when the pause really was
transient. A run that is merely slow is not a failure: `--run-timeout`
(default 5400s) is the limit.

A slot in `services/OpenMAIC/openmaic.yml` may carry a `fallback`, and the
shipped file gives every language slot one (`auto/best-chat` for prose,
`auto/best-coding` for the interactive writer and the workbench agent). That is
what keeps a single provider's five-hour quota from pausing every run while the
rest of the gateway is idle: the primary is tried first, the fallback once when
the primary answers with a retryable error. A deployment that pins all four
slots to one model has no such second chance, and `--models` is then the only
way through a cooldown.

The models a classroom may be pointed at are the ones the deployment declares in
`services/OpenMAIC/openmaic.yml` — anything else is refused with
`PROVIDER_DISABLED`, so the chain has to be built from those names (the shipped
file declares the gateway's `auto/best-*` routes). A paused run is discarded
before the next model is tried: it has no classroom yet and still counts against
the owner's concurrent-run limit, so leaving them behind jams a batch shut.
`--skip <slug|code>` leaves a course out of the run, which is how the demo course
stays classroom-free.

### Course-generation console (`ai.lms.<domain>`)

`scripts/build-classrooms.py` is the batch: an operator runs it from a shell, in
one long command, and reads the log. The console is the same work from a
browser — the staff screen that lists every course's classroom briefs, starts
one, shows the run's step, and writes a finished classroom's id back into the
spec on its own. It is a **front for OpenMAIC**, not a second generator:
OpenMAIC keeps the runs, the classrooms and the model settings.

```bash
make up                       # this repo's compose: landing + generation
# on a box with OpenMAIC locally:
make generation-console       # opens on 127.0.0.1:8090, trusting local requests
```

What it serves (`web/generate/`, no build step, stdlib Python — see the module
docstring in `scripts/generation-console.py` for the full route list):

- **Courses** — one row per classroom in `courses/*/openmaic/classrooms.json`,
  with its chapter, its linked units, and whether the spec already records a
  `classroom_id`. A missing one gets a **Generate** button; a generated one
  links straight to `classroom.<domain>/classroom/<id>`.
- **Runs** — what OpenMAIC is holding: step, progress, and the gateway's own
  error words on a paused run. A paused run can be **retried** or **discarded**
  (a run that already produced a classroom answers 409 and is kept). A run that
  came from a spec is **recorded without a click**: the moment it completes, its
  `classroom_id` is written into the spec and the entry leaves the list, which is
  what the batch tool does in `--execute`. A spec that has meanwhile been given a
  *different* classroom is the one case left for a person — overwriting it would
  silently repoint a course's embeds — so that run stays visible with the reason
  attached.
- **Generate all missing** — one run per classroom without a `classroom_id`,
  across every spec in `courses/`. Two ceilings decide how many run at once, and
  both are configuration rather than code: `GENERATION_SUBMITS_PER_HOUR` (the
  console's own per-person hourly limit, default 10, `0` disables it) and
  OpenMAIC's `OPENMAIC_MAX_ACTIVE_RUNS_PER_OWNER` (how many of one owner's runs
  may be in progress at once, platform default 2). What neither ceiling can start
  is **queued**, not dropped: the service keeps the classroom, the answer says how
  many are waiting, the page lists them under the runs they are waiting for, and
  the next run to finish starts the next one — the sweeper's tick does it with no
  page open, and the page's own poll does it while one is. One click therefore
  covers a whole course. The number running at once is the active-run limit, so a
  deployment that wants five sets it to `5` (with
  `OPENMAIC_AGENT_RUNTIME_MAX_CONCURRENT` and
  `OPENMAIC_GENERATION_RUN_MAX_CONCURRENT` at least that high, since the lowest
  ceiling wins). `ai.lms` runs that way: the hourly limit is off and all three
  are `5`. Classrooms already in flight are skipped rather than submitted twice,
  because the spec does not learn about a run until it finishes; so is one the
  spec has meanwhile been given, with the reason attached.
- **New brief** — a free-form classroom for something not in a spec yet.

Recording does not depend on somebody having the page open: the service sweeps
finished runs every `GENERATION_AUTORECORD_SECONDS` (the unit ships `20`), and
keeps the run → spec map in `GENERATION_STATE` so a restart between a run
finishing and its recording does not lose it.

**Who may generate.** The console sits behind an oauth2-proxy and does not trust
it blindly: every request must carry the identity headers the proxy sets, and
the caller must hold one of `GENERATION_ALLOWED_GROUPS` (default
`atheniq-admins,instructors`). No headers is a 401, the wrong groups is a 403,
so a misrouted proxy fails closed instead of publishing an endpoint that spends
model budget.

The console reads **both** header families oauth2-proxy can supply, because the
two flags write to different places: `--set-xauthrequest` sets
`X-Auth-Request-*` on the *response* (for an nginx `auth_request` in front),
while `--pass-user-headers` sets `X-Forwarded-*` on the request it proxies
*upstream* — the request the console receives. Accepting only the first family
is what made a signed-in browser get 401 from every `/api/` call, and the
console's "signed out" label, while the proxy logged the same user as
authenticated. `X-Auth-Request-*` wins when both are present. Mutating calls also
require the console's own header plus a same-origin `Origin`, which is what stops
a cross-site post.

```bash
# alongside the classroom's own oauth2-proxy; the upstream is where the console
# listens (GENERATION_BIND), not OpenMAIC itself
oauth2-proxy \
  --provider=oidc --oidc-issuer-url=https://auth.cerulean.innotel.us/application/o/classroom/ \
  --oidc-groups-claim=groups --scope="openid email profile groups" --email-domain='*' \
  --allowed-group=atheniq-admins --allowed-group=AthenIQ \
  --set-xauthrequest=true --pass-user-headers=true --cookie-secure=true \
  --reverse-proxy=true --http-address=0.0.0.0:3001 \
  --upstream=http://<atheniq host>:8090
```

**Why it runs on the host network.** OpenMAIC publishes its API on the host's
loopback (`OPENMAIC_PUBLISH_ADDRESS=127.0.0.1`) so nothing on the LAN reaches it
without the SSO proxy in front of it; a bridged console container cannot see
that address,
and publishing OpenMAIC for the console's sake would undo the isolation. On the
host network the console dials `127.0.0.1:3000` and listens on `GENERATION_BIND`
(the LAN address the proxy dials). `courses/` is mounted writable, for recording
a classroom id in its spec; `scripts/` and `web/` are read-only.

`/healthz` answers without an identity (it says the process is up and nothing
else) so the container healthcheck does not need to sign in.

`generation-sso` skips authentication for exactly that path
(`--skip-auth-route=^/healthz$`), so an uptime probe can cross the same
NPM -> oauth2-proxy -> console path a browser takes. The timer below runs
`scripts/check-generation-console.sh` every five minutes and leaves the unit
failed when the console or the proxy stops answering:

```bash
sudo cp deploy/systemd/atheniq-generation-uptime.service deploy/systemd/atheniq-generation-uptime.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now atheniq-generation-uptime.timer
journalctl -u atheniq-generation-uptime.service -n 20
```

A failing probe leaves the unit failed; it also emails `ATHENIQ_ALERT_EMAIL`
through the site's Mailcow relay (`mail.innotel.us`, `192.168.1.15`, port 25 with
STARTTLS and no credentials; set `ATHENIQ_SMTP_USER`/`ATHENIQ_SMTP_PASSWORD` for
a relay that wants submission auth on 587). The values live in a drop-in so a
repository update keeps them:

```bash
sudo mkdir -p /etc/systemd/system/atheniq-generation-uptime.service.d
sudo tee /etc/systemd/system/atheniq-generation-uptime.service.d/alert.conf >/dev/null <<'CONF'
[Service]
Environment=ATHENIQ_ALERT_EMAIL=ops@example.edu
Environment=ATHENIQ_SMTP_HOST=mail.example.edu
Environment=ATHENIQ_SMTP_PORT=25
Environment=ATHENIQ_SMTP_FROM=atheniq-uptime@example.edu
CONF
sudo systemctl daemon-reload
```

`ATHENIQ_ALERT_WEBHOOK_URL` remains supported as a second channel (a plain-text
POST for ntfy-style endpoints); this host sends email only. The unit is left
failed whether or not a channel is configured, and a failed delivery is printed
in the journal without masking the probe's own failure.

**Realized (2026-10, `ai.lms.innotel.us`).** The console runs from
`atheniq-generation.service` (`deploy/systemd/atheniq-generation.service`):
`/home/tutor/atheniq-generation` holds this repo's `scripts/generation-console.py`,
`web/generate/` and the fourteen `courses/*/openmaic/classrooms.json`, and the
unit binds `192.168.1.59:8090` as the `tutor` user (so recording a classroom id
can write the spec it owns). In front of it, a second oauth2-proxy
(`generation-sso`, published `192.168.1.59:8091`) reuses the classroom's
Authentik client with `--set-xauthrequest`/`--pass-user-headers`; its callback
`https://ai.lms.innotel.us/oauth2/callback` had to be added to that provider
(the `Classroom` provider, `client_id=classroom`) — Authentik's OAuth2 model is
at `/api/v3/providers/oauth2/`, not under `core/`.

```bash
# on the edge host, in this order
scp scripts/cerulean-issue-cert.js scripts/npm-upload-cert.py scripts/ai-lms-edge.py proxy:/tmp/
docker cp /tmp/cerulean-issue-cert.js cerulean:/tmp/
# 1. the certificate: Cerulean's own ACME path (DNS-01 through Technitium)
docker exec -e DOMAIN=ai.lms.innotel.us cerulean node /tmp/cerulean-issue-cert.js
# 2. into NPM, which is what terminates TLS (multipart upload, not JSON)
python3 /tmp/npm-upload-cert.py <cerulean certificate id>
# 3. the zone CNAME and the proxy host (192.168.1.59:8091) behind it
python3 /tmp/ai-lms-edge.py            # DRY_RUN=1 to plan only
```

The certificate is one name, not a wildcard: `ai.lms.` is not covered by the
`lms.innotel.us` pair, and a wildcard for a name only used by staff would be
wider than the need. Verified live: `CN=ai.lms.innotel.us` (Let's Encrypt),
`302` to Authentik on every path including `/api/`, and a request that sets its
own `X-Auth-Request-*` headers is still refused — the proxy authenticates before
it forwards.

### Programs — degrees and certificates (this repo)

The console also runs whole credentials. A program is the ordered set of
semesters, courses, prerequisites and final assessments that ends in a degree or
a stackable certificate; `scripts/program-catalog.py` ships three
(`criminal-justice`, `business-administration`, `nursing`) and
`scripts/program-manager.py` holds the rules. Programs are stored as JSON under
`GENERATION_ROOT/programs/`, so the store must be writable by the unit's user
(`tutor` on this host) and `conferrals/` beside it receives the signed record.

```text
GET    /api/programs                     running programs + catalogue templates
POST   /api/programs                     create from a template or a course list
GET    /api/programs/<id>                the program with its semester plan and finals
GET    /api/programs/<id>/progress?student=…
POST   /api/programs/<id>/generate       one classroom run per course (semester/course filters)
POST   /api/programs/<id>/sync           record finished runs into the plan
POST   /api/programs/<id>/enroll         enrol a learner
POST   /api/programs/<id>/complete       record a grade and final result
POST   /api/programs/<id>/confer         confer the credential and sign it
```

`/programs.html` is the learner's page (catalogue, progress, what they can take
next); the instructor/administrator controls on the same page appear only when
the caller holds `GENERATION_ALLOWED_GROUPS`. Conferral is refused until every
course, credit, GPA and final requirement is met, and the signed degree is
rendered by `scripts/cert-bridge.py` and pushed through Signara using the same
signer as course certificates. Because the service runs as `tutor`, the unit
creates `programs/` and `conferrals/` owned by that user.

### Learner portal — `lms.innotel.us`

`scripts/student-portal.py` serves the learner-facing catalogue: the programs the
platform runs and the courses it teaches, with the semesters, prerequisites and
final examinations behind each one. It is deliberately **public and read-only** —
a learner should not need a staff account to read what the school teaches, and a
public page must not be able to reach a gradebook. The JSON it answers with
(`/api/public/programs`, `/api/public/programs/<id>`, `/api/public/courses`)
drops enrolments, grades and the creating account before it leaves the process.

```text
STUDENT_BIND=192.168.1.59   STUDENT_PORT=8092   STUDENT_ROOT=/home/tutor/atheniq-generation
```

It runs as `atheniq-student.service`. The page is `web/student/` and wears the
same Unity palette as the console and the Studio chrome. **Live:** the edge
proxy host for `lms.innotel.us` now forwards to `192.168.1.59:8092` instead of
the LMS root (which only ever answered with a redirect to
`apps.learn.innotel.us/catalog/`), and `https://lms.innotel.us/` serves the
portal with `/api/public/programs` answering 200.

### Library — shared media shelves

The console's **Library** page (`web/generate/library.html`, `/api/library`)
records the shelves courses draw media from: one folder per library under
`library/<slug>/` with a `library.json` manifest, created by staff and listed
with its asset count. Files are put into a shelf through the storage host, so an
empty shelf says it is empty rather than pretending to hold content. The slug is
derived server-side from the name, so a name can never become a path.

### Studio chrome — `studio.innotel.us`

`contrib/atheniq-theme/cms/` is the CMS half of the theme overlay: a header
template that adds the **AthenIQ Platform Services** entry (and a learner-portal
link) beside the Studio logo, and `unity-cms.css`, which paints the Studio header
in Unity while leaving the course editor itself on the platform's light default.
The Tutor theme plugin copies both halves into `/openedx/themes/indigo/`. On a
running deployment the files can be copied into the CMS container and followed by
`./manage.py cms collectstatic --noinput --settings=tutor.production`; the theme
namespace makes the stylesheet answer at
`/static/studio/indigo/atheniq/unity-cms.css`.

### Stage 3b — OpenMAIC persistence Postgres (this repo)

Only needed when you point `DATABASE_URL` at it instead of the bundled service.

```bash
docker compose --profile openmaic up -d
```

## Stage 4 — Realtime (Convex, self-hosted)

Convex runs as a profile in this repo's [docker-compose.yml](../docker-compose.yml)
(`convex` + `convex-dashboard`) — the same shape as Atlas's self-hosted Convex.
This replaced a `curl` of the upstream compose file, so the services, ports,
volumes, healthcheck and env passthrough are reviewed here instead of arriving
from whatever upstream published that day.

Both images default to `latest` and are pinnable — **independently**:
`CONVEX_BACKEND_VERSION` and `CONVEX_DASHBOARD_VERSION` in `.env`. The two are
not tagged the same way (the backend publishes commit-sha tags; the dashboard
does not carry them), so a single shared version value pulls one image and 404s
the other. `.env.example` carries a verified backend value.

```bash
make convex-up     # backend :3210 (loopback) + dashboard :6791
make convex-key    # mint the admin key from the RUNNING backend
```

`make convex-key` prints a key signed by the live instance — only the backend
can mint a valid one, so it cannot be generated locally. Paste it into `.env`:

```env
CONVEX_SELF_HOSTED_URL=http://127.0.0.1:3210
CONVEX_SELF_HOSTED_ADMIN_KEY=<admin key from make convex-key>
```

Both services bind **loopback only** (the architecture keeps realtime, the
model gateway and Postgres off the public interface); the LMS reaches the
backend over the private network.

**File storage on ONYX (roadmap V2).** Convex stores files on its own volume
until buckets are configured. To move classroom media to ONYX's S3-compatible
endpoint, set `ONYX_S3_ENDPOINT`, `ONYX_S3_BUCKET_FILES`,
`ONYX_S3_BUCKET_EXPORTS` and the `ONYX_S3_ACCESS_KEY`/`ONYX_S3_SECRET_KEY` pair
in `.env` (`ONYX_S3_FORCE_PATH_STYLE=true` is the default and is what ONYX
expects), create the buckets, and re-run `make convex-up`:

```bash
make onyx-check      # verify ONYX is reachable + the credentials are accepted
make onyx-buckets    # create atheniq-files + atheniq-exports (idempotent)
```

`scripts/onyx-buckets.py` talks ONYX's S3 API directly (SigV4, no `aws`/`mc`
dependency); `make onyx-selftest` validates the configuration offline and
`--dry-run` shows the plan without calling ONYX. Leaving the endpoint blank is a
supported state, not a misconfiguration — Convex then keeps files on its own
data volume. See [docs/Integrations.md](Integrations.md#onyx--object-storage-storageops).

For production workloads, follow the upstream advanced guides to move the store
to Postgres/MySQL. Convex Auth is not supported self-hosted — keep app auth on
Authentik OIDC.

**Verify:**

```bash
docker compose --profile convex ps                 # both healthy
curl -fsS http://127.0.0.1:3210/version           # backend answers
```

## Stage 5 — Course media studio (Open Generative AI, optional)

Self-host the studio from https://github.com/anil-matcha/open-generative-ai and
set `OPEN_GENERATIVE_AI_URL`. Keep it author-only (LAN or a proxied
`media.<domain>` host) — learners do not need direct access.

## Stage 6 — Model gateway and agents

AthenIQ starts no gateway. The platform runs ONE OmniRoute, in Group 2
(`2-voice/`), inside Cerulean's edge host — `192.168.1.71`. Its own listener,
`:20128`, is not a routable target: Cerulean SSO is the gateway's only gate, so
that port answers on the edge host's loopback and bridge alone. Everything else
dials the identity-aware proxy in front of it, also `:20128`, whose `/v1` route
is exempt for API clients.

1. Open the OmniRoute dashboard at `http://192.168.1.71:20128` (the proxy sends
   you through Cerulean Authentik first) and connect the provider accounts the
   platform may use. The gateway accounts per API key, so create one per
   consumer and store it as `cerulean/<slug>#OMNIROUTE_API_KEY` in Cerulean Vault
   beside the rest of that project's secrets.
2. Set `OMNIROUTE_BASE_URL=http://192.168.1.71:20128/v1`, `OMNIROUTE_API_KEY`, and
   `OMNIROUTE_MODEL` in `.env`. The proxy exempts `/v1` for API clients, so that
   route needs no session; the dashboard behind it still requires one.
3. OpenMAIC reads the same endpoint, so classrooms and agents share the pool.
4. For chat-driven classrooms, run **OpenClaw** with the OpenMAIC skill, and
   point the **OpenClaude** CLI at the OmniRoute endpoint for authoring tasks
   (see [docs/Integrations.md](Integrations.md#openclaw--openclaude--omniroute--agent-layer)).

## Stage 7 — Signed certificates (Signara)

1. In the Signara portal, create the signature workflow/template for course
   certificates and an API token for AthenIQ.
2. Set `SIGNARA_API_URL` and `SIGNARA_API_KEY` in `.env`.
3. Completion events in AthenIQ flow to Signara and return signed certificates
   as described in [docs/Integrations.md](Integrations.md#signara--signed-course-certificates-documentops).

## Stage 8 — Paid courses (Magnate)

Magnate owns billing for the platform; AthenIQ gates paid courses on a Magnate
plan entitlement rather than running a price list. Set in `.env`:

- `MAGNATE_API_URL` — the Magnate storefront/service base URL
  (`https://app.magnate.innotel.us`),
- `MAGNATE_ENTITLEMENTS_TOKEN` — the same value as Magnate's
  `ENTITLEMENTS_API_TOKEN` (it gates both `/api/entitlements` and
  `/api/purchases`),
- `MAGNATE_PAID_PLAN` — the plan slug that unlocks paid courses.

Then verify the leg:

```bash
make magnate-probe     # reachability + token accepted
python3 scripts/magnate-entitlements.py check --user <username|email> --plan "$MAGNATE_PAID_PLAN"
```

`scripts/magnate-entitlements.py` also creates a one-off course Checkout
(`buy --course <key> --name <label> --amount-cents <n>`, `--dry-run` to preview)
and verifies Magnate's signed purchase callbacks (`verify-signature`). The
entitlement decision — not a local price — is what grants a learner access to a
paid course; see [docs/Integrations.md](Integrations.md#magnate--paid-courses--entitlements-revenueops).

Turn the entitlement into access, and keep it honest:

```bash
# grant one learner access to a paid course (idempotent); --revoke to remove it
python3 scripts/paid-enrollment.py --user learner@x.edu \
    --course course-v1:InnotelLabs+TEST101+2026_T1
python3 scripts/paid-enrollment.py --status       # enrollment ledger
```

The `learners` -> `paid_users` group membership converges on a timer, so a
missed Magnate webhook or a restored Authentik DB heals itself. Set
`AUTHENTIK_API_URL` / `AUTHENTIK_API_TOKEN` in `.env`, then install the unit:

```bash
sudo cp deploy/systemd/atheniq-entitlement-sync.service deploy/systemd/atheniq-entitlement-sync.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now atheniq-entitlement-sync.timer
make entitlement-status    # what it sees now, without writing
```

## Stage 8b — workforce track gating and track credentials

A workforce track is a ladder ([docs/WorkforceTracks.md](WorkforceTracks.md)).
Two operator steps turn the catalog into enforcement and a credential:

```bash
make gating          # print the derived prerequisite chain (read-only)
make gating-apply    # write it through the running CMS (course prerequisites)

# once a learner has passed every course in a track, sign the track credential:
python3 scripts/track-credential.py --learner learner@example.edu
python3 scripts/track-credential.py --learner learner@example.edu --sign
make track-credential-status
```

`gating-apply --dry-run` prints the CMS snippet instead of running it. The
course-level certificate bridge (Stage 7) issues track credentials
**automatically** on each pass — when a learner's certificates cover every course
in a track, the track credential is signed then (disable with
`--no-track-credentials`). On this deployment that pass is already driven by the
`atheniq-cert-bridge.timer` unit (every 2 minutes, `--once`), so track
credentials need no extra unit. The standalone `scripts/track-credential.py`
remains for on-demand checks and the `--sign` path; `make track-credential-status`
reads the ledger.

## Cerulean DNS and TLS

Public hosts are provisioned through Cerulean as usual for stack platforms:

- Cerulean writes DNS records (A/CNAME) into the zone it serves from
  Technitium (`/api/domains/:id/records`) and requests Let's Encrypt
  certificates (regular or wildcard) with DNS-01 through that same zone.
- NGINX Proxy Manager hosts are created automatically for each canonical
  subdomain, with TLS termination at NPM.

Canonical hosts for a reference deployment:

| Host | Backend |
| --- | --- |
| `atheniq.<domain>` | Product landing page — the `landing` compose service serving `web/landing/` |
| `learn.<domain>` | Tutor LMS — `LMS_HOST`, the canonical name |
| `apps.learn.<domain>` | Learner MFEs (`apps.<LMS_HOST>`) |
| `lms.<domain>` | Alias of `learn.<domain>` (NPM host, certificate, zone CNAME) |
| `apps.lms.<domain>` | Alias of `apps.learn.<domain>` |
| `studio.<domain>` | AthenIQ Studio |
| `classroom.<domain>` | OpenMAIC |
| `ai.lms.<domain>` | Course-generation console — staff only, behind its own oauth2-proxy |
| `cert.<domain>` | Signara portal (shared DocumentOps) |

Set the `CERULEAN_*` variables in `.env` (`CERULEAN_BASE_DOMAIN`,
`CERULEAN_ZONE`, API URL/password, WAN discovery) before running any
Cerulean provisioning. Docker/LAN addresses are never published to DNS; only
the public WAN address is used for records and the LAN address for NPM
upstreams.

`atheniq.<domain>` is the product's own name and it has to answer with the
product: `web/landing/` is the site (index, `/catalog/`, `/courses/*`), and the
`landing` service in [`docker-compose.yml`](../docker-compose.yml) serves that
directory straight out of the repo with Caddy's file server on
`LANDING_BIND:LANDING_PORT` (`192.168.1.59:8085` on this deployment). NPM
publishes it under the name with Cerulean's `atheniq.<domain>` certificate, and
the zone already carries the CNAME. The pages' canonical and Open Graph URLs are
the product domain rather than the GitHub Pages preview CI also publishes.

**Realized (2026-10):** `atheniq`, `learn`, `apps.learn`, `lms`, `apps.lms`,
`studio`, `classroom`, `ai.lms` (the generation console, its own
single-name certificate), and `meilisearch.learn` / `meilisearch.lms`
(`innotel.us`) are live.
DNS records are CNAMEs to the `innotel.us.` apex (A `73.68.203.71`, the edge's
WAN address), written through Cerulean's Technitium plane — the old
TSIG/`nsupdate` BIND zone at `192.168.1.80` is retired. The edge (nginx proxy
manager, admin API on `192.168.1.71:81`) forwards every host to
`http://192.168.1.59:18080` (Tutor caddy) and terminates TLS; each host carries
its own Let's Encrypt certificate issued by Cerulean (`learn` has `CN=learn.innotel.us`
plus `*.learn.innotel.us`, which is what covers `apps.learn`).

`learn.<domain>` is the canonical `LMS_HOST` and `apps.learn.<domain>` the
learner MFEs (`apps.<LMS_HOST>`); the MFEs read their configuration from the LMS
at runtime, so no MFE image is rebuilt when a name changes. Alongside
`LMS_HOST`, three things outside the Tutor config carry the name: the zone
record and NPM host for the MFE name, the Authentik provider's redirect URI
(`https://learn.<domain>/auth/complete/oidc/`), and the `django.contrib.sites`
row (`learn.<domain>`, which is what course emails use).

`lms.<domain>` and `apps.lms.<domain>` are kept as **aliases**: NPM hosts on the
same upstream as the canonical pair (`http://<tutor host>:18080`), a `lms` CNAME
in the zone, and the names in `ATHENIQ_LEGACY_LMS_HOSTS` / `ATHENIQ_LEGACY_MFE_HOSTS`
so Django answers them, trusts their forms and allows login to return to them. A
request to `https://lms.<domain>/` therefore lands on the canonical platform —
the LMS redirects it to `https://apps.learn.<domain>/catalog/` itself. Both
lists are data rather than defaults, which is why a `tutor config save` cannot
resurrect a name that was dropped.

```bash
pip install -e contrib/tutor-atheniq-hosts
tutor plugins enable atheniqhosts
tutor config save \
  --set LMS_HOST=learn.<domain> \
  --set 'ATHENIQ_LEGACY_LMS_HOSTS=["lms.<domain>"]' \
  --set 'ATHENIQ_LEGACY_MFE_HOSTS=["apps.lms.<domain>"]'
tutor local restart caddy lms lms-worker cms cms-worker mfe
```

Two values this deployment overrides by hand embed the hostname as well and
have to be rewritten with it: `MFE_CONFIG` (absolute MFE/login/logo URLs) and
`PARAGON_THEME_URLS` (the `brandOverride` stylesheet URLs). `tutor config save`
alone will not move them — they are plain strings in `config.yml`.

The [`contrib/tutor-atheniq-hosts`](../contrib/tutor-atheniq-hosts) plugin ships
both lists empty; keeping an alias alive is the `--set` above plus its NPM host
and zone record, and dropping the name again is the same edit in reverse.

Run [`scripts/provision-edge.sh`](../scripts/provision-edge.sh) to re-apply
(idempotent; pass hostnames to narrow it). It drives Cerulean's API for the
DNS record, the certificate, and the NPM host; `DRY_RUN=1` prints the plan.

> Scheme note: Tutor runs with `ENABLE_HTTPS=true` and `ENABLE_WEB_PROXY=false`
> (its own caddy stays plain HTTP on `:18080`; NPM terminates TLS). This makes
> AthenIQ emit `https://` absolute URLs — required, since the browser would
> otherwise block the MFEs' API calls as mixed content (this broke the catalog
> MFE at `https://apps.learn.innotel.us/catalog/` until flipped). To re-apply
> after a Tutor reinstall: `tutor config save --set ENABLE_HTTPS=true` then
> `docker compose -p tutor_local -f docker-compose.yml -f
> docker-compose.prod.yml restart lms cms mfe caddy`.

Each public name carries `Strict-Transport-Security: max-age=63072000; preload`
(`learn`, `apps.learn`, `lms`, `apps.lms`, `atheniq`); `includeSubDomains` is
deliberately off, because a sticky rule covering every subdomain would outlive
any one host's certificate.

The edge is one step removed from this repo, so it has a check of its own:

```bash
make cert-check          # or: python3 scripts/cert-check.py learn.innotel.us
python3 scripts/cert-check.py --http    # also GET / and fail on a 5xx (the deploy gate)
```

For every name it verifies the handshake against the system trust store, that the
certificate's SAN list covers the name (wildcards cover exactly one label), that
the **served chain carries an issuer as well as the leaf** — the failure this was
written after: a leaf-only chain verifies wherever the intermediate is already in
the store and shows as "not secure" everywhere else — and that the certificate is
not expired, warning inside 21 days. `--http` adds the other half of "the name
works": a request for `/` that fails on a 5xx or on no answer, which is how a
host left disabled or a container that never came back looks from outside. Exit
status is 1 on any failure, so it gates [`scripts/deploy.sh`](../scripts/deploy.sh).

## Stage 9 — Known fixes applied on this deployment (2026-09)

These were diagnosed live and must be re-applied after a Tutor reinstall or
volume wipe, or SSO and catalog search will break again.

### 9.1 Authentik provider needs a signing key

**Symptom:** SSO login completes at Authentik but the LMS callback 500s with
`KeyError: 'keys'`; `GET /application/o/<slug>/jwks/` returns `{}` instead of
`{"keys": [...]}`.

**Cause:** the `atheniq-lms` OIDC provider row had a NULL `signing_key`, so
Authentik issues no keys and python-social-core cannot validate the ID token.

**Fix (one-time, via Authentik DB — do not leave NULL):**

```sql
UPDATE authentik_providers_oauth2_oauth2provider
SET signing_key_id = (
  SELECT kp_uuid FROM authentik_crypto_certificatekeypair
  WHERE name = 'authentik Self-signed Certificate' LIMIT 1
)
WHERE client_id = 'atheniq-lms';
```

Verify: `curl -sk https://auth.<domain>/application/o/atheniq-lms/jwks/` returns
`{"keys":[...]}`. Prefer setting the signing key in the Authentik UI for new
providers.

### 9.2 Course catalog search: index + filterable attributes

**Symptoms:** catalog MFE at `apps.learn.<domain>/catalog/` loads but shows zero
courses even though `/api/courses/v1/courses/` lists them; the search API
`POST /search/unstable/v0/course_list_search/` returns `total:1, results:[]`.

**Causes (three):**
1. The course was never indexed into Meilisearch (created via modulestore shell
   bypasses the Studio reindex signal).
2. The course document lacked `enrollment_start`, which the search view
   requires (`enrollment_start <= now` is a hard filter when
   `SEARCH_SKIP_ENROLLMENT_START_DATE_FILTERING` is off) — Meilisearch drops
   docs missing a filtered attribute.
3. `search.meilisearch.INDEX_FILTERABLES` for `course_info` declares
   `enrollment_end` but **not** `enrollment_start`, so even with the field
   present Meilisearch rejects the filter on a non-filterable attribute.

**Fixes:**

```bash
# 1. index all courses (as the cms container, tutor user)
docker exec tutor_local-cms-1 sh -c 'cd /openedx/edx-platform && \
  ./manage.py cms reindex_course --all --setup'

# 2. give the course an enrollment window (draft-preferred branch), then reindex
#    e.g. via cms shell: course.enrollment_start = now - 30d; store.update_item

# 3. declare the attribute filterable in the live Meilisearch index
MEILI_KEY=$(sudo -u tutor -H bash -c '~/tutor-venv/bin/tutor config printvalue MEILISEARCH_MASTER_KEY')
docker exec tutor_local-meilisearch-1 sh -c "curl -s -X PUT \
  -H 'Authorization: Bearer $MEILI_KEY' -H 'Content-Type: application/json' \
  'http://localhost:7700/indexes/tutor_course_info/settings/filterable-attributes' \
  -d '[\"language\",\"modes\",\"org\",\"catalog_visibility\",\"enrollment_end\",\"enrollment_start\"]'"
```

Also patch the container so reindexing won't clobber it:
`/openedx/venv/lib/python3.12/site-packages/search/meilisearch.py` — add
`"enrollment_start",` to the `course_info` entry of `INDEX_FILTERABLES`.
(Upstream edx-search bug; tracked so a future upgrade removes this step.)

Verify with a real session (CSRF + Referer required):
`POST https://learn.<domain>/search/unstable/v0/course_list_search/` with
`page_size=9&page_index=0` → `results[0].data.content.display_name`.

### 9.3 Provider needs scope mappings (userinfo 403)

**Symptom:** SSO completes at Authentik and the token exchange succeeds, but
login still 500s: LMS log shows `403 Forbidden for url:
.../application/o/userinfo/` while Authentik logs the token POST as 200 and
the userinfo GET as 403. Authentik's `protected_resource_view` returns 403
(`insufficient_scope`) because the issued access token has **no scopes**.

**Cause:** the OIDC provider had no `ScopeMapping`s assigned, so Authentik's
`__check_scopes` intersected the requested scopes (`openid profile email`)
with an empty allowed set → access tokens were issued with empty scope.
Healthy providers carry `openid, profile, email, groups`.

**Fix (one-time, via Authentik DB):**

```sql
INSERT INTO authentik_core_provider_property_mappings (provider_id, propertymapping_id)
SELECT 20, propertymapping_ptr_id FROM authentik_providers_oauth2_scopemapping
WHERE scope_name IN ('openid','profile','email','groups')
ON CONFLICT DO NOTHING;
```

(replace `20` with the provider's `provider_ptr_id`). Prefer assigning the
standard scopes in the Authentik UI for new providers.

Verify: a fresh login yields an access token whose `_scope` contains
`openid` (`SELECT _scope FROM authentik_providers_oauth2_accesstoken ORDER
BY auth_time DESC LIMIT 1`), and `GET .../application/o/userinfo/` with that
token returns 200.

### 9.4 Studio (CMS) login: redirect-uri mismatch + missing CMS TPA machinery

**Symptom:** clicking Studio login redirects through Authentik but returns
`invalid_request / Mismatching redirect URI`; `/auth/complete/oidc/` on the CMS
was a 404; after wiring routes it 500'd on user creation / "Your account is
disabled"; and Studio's own `/login` 500'd with `Can't fetch setting of a
disabled backend/provider`.

**Root causes (four, all fixed in code + plugin):**

1. **Redirect-uri scheme mismatch** — the Tutor AthenIQ plugin's CMS settings
   template (`partials/common_cms.py`) hardcodes
   `SOCIAL_AUTH_REDIRECT_IS_HTTPS = False`, so the CMS builds the redirect_uri
   from the **request's scheme**. The CMS receives plain HTTP from the edge
   (TLS terminated at NPM/Caddy), so it sends
   `http://studio.innotel.us/auth/complete/oidc/` → does not match the
   registered `https://...` URI → `invalid_request`. The LMS is unaffected
   because its settings leave the flag unset (defaults to HTTPS).
2. **CMS never had the TPA urls.** Stock AthenIQ ships the TPA urlconf
   (`common.djangoapps.third_party_auth.urls`, which provides
   `/auth/login/<backend>/` and `/auth/complete/<backend>/`) in the **LMS
   only**; the CMS urlconf lacks it, so Studio's callback 404'd.
3. **CMS never had the TPA machinery.** `third_party_auth` is not in the CMS
   `INSTALLED_APPS`, `SOCIAL_AUTH_PIPELINE` is not defined there (LMS-only in
   `lms/envs/common.py`), and CMS lacks `TPA_PROVIDER_BURST_THROTTLE` /
   `TPA_PROVIDER_SUSTAINED_THROTTLE` / `PROFILE_MICROFRONTEND_URL`. Without the
   TPA pipeline, social-auth's raw `create_user` crashes on AthenIQ profile
   fields (`Column 'last_name' cannot be null`); with the pipeline but no
   client key/secret the provider looks disabled.
4. **Do NOT use `ConfigurationModelStrategy` in the CMS.** Studio's own login
   flows through the internal `edx-oauth2` backend (LMS OAuth), and that
   strategy requires an `OAuth2ProviderConfig` row for **every** OAuth backend
   — none exists for `edx-oauth2`, so `/login` 500s. The CMS OIDC provider
   credentials are injected directly in settings instead.

**Fixes:**

1. The Cerulean SSO plugin now ships the full CMS block in
   [`contrib/tutor-ceruleansso`](../contrib/tutor-ceruleansso):
   `SOCIAL_AUTH_REDIRECT_IS_HTTPS = True`, `third_party_auth` in
   `INSTALLED_APPS` + its `ExceptionMiddleware`, the AthenIQ
   `SOCIAL_AUTH_PIPELINE`, both TPA throttle settings, and
   `PROFILE_MICROFRONTEND_URL`. Re-render with `tutor config save` after any
   Tutor reinstall.
2. **One-time CMS urlconf patch** (not expressible via a settings plugin —
   re-apply if the CMS container is recreated): append to
   `/openedx/edx-platform/cms/urls.py`:

   ```python
   if settings.FEATURES.get("ENABLE_THIRD_PARTY_AUTH"):
       urlpatterns += [
           path("", include("common.djangoapps.third_party_auth.urls")),
           path("api/third_party_auth/",
                include("common.djangoapps.third_party_auth.api.urls")),
       ]
   ```

   then `docker restart tutor_local-cms-1`. (The API include needs the two TPA
   throttle settings from fix 1.)
3. **Client credentials** are injected into the rendered CMS settings
   (`SOCIAL_AUTH_OIDC_KEY`/`SECRET` = `atheniq-lms` / the provider secret from
   Cerulean). On the LMS these come from the TPA `ProviderConfig` row via
   `ConfigurationModelStrategy`; the CMS uses direct settings injection
   instead (see cause 4).
4. **First Studio login for an existing edx account** requires the account to
   have a usable password hash — TPA registration on the LMS sets one
   (`pbkdf2_sha256`); an account created via raw SQL with password `!` will be
   rejected with `403 "Your account is disabled"` by the
   `set_logged_in_cookies` pipeline step.

Verify (full browser flow): Studio login → `/auth/login/oidc/?next=/home` →
Authentik authorize (HTTPS `redirect_uri`) → login → callback
(`/auth/complete/oidc/`) → `/home` → `/authoring/home` with `edx-jwt-cookie-*`
and `edxloggedin` cookies set.

### 9.5 Studio legacy course-settings pages 500 for non-HTML clients

**Symptom:** after SSO completes, opening the legacy
`https://studio.<domain>/settings/details/<course>` link (e.g. Studio's
"View About Page") 500s with `Internal Server Error` whose traceback ends in
`AttributeError: 'NoneType' object has no attribute 'set_cookie'` from the CSRF
middleware — even though the authenticated user has course access.

**Root cause:** `cms/djangoapps/contentstore/views/course.py`
`settings_handler()` only returns a response when the request `Accept` header
contains `text/html` (GET → renders/redirects to the authoring MFE) or
`application/json` (GET/PUT → `JsonResponse`). Any other Accept (e.g. `*/*`,
which browser/SPA `fetch()` sends by default, or no Accept at all) falls
through the `if/elif` and returns `None`; Django's CSRF middleware then raises
on the None response. This is an upstream edx-platform bug on the Ulmo+ (new
React Studio) code path — browsers doing a plain top-level navigation are fine
(`text/html` → 302 to the authoring MFE at `apps.learn.<domain>/authoring/...`),
but the post-login landing or SPA re-fetch of the legacy URL hits the `*/*`
path and 500s.

**Fix (one-time, in-container — re-apply if the CMS container is recreated):**
insert a fallthrough guard before the end of `settings_handler()` in
`/openedx/edx-platform/cms/djangoapps/contentstore/views/course.py` (after the
`elif 'application/json' ...` block closes, still inside the
`with modulestore().bulk_operations(course_key):` block):

```python
        # Fallthrough guard: requests whose Accept header is neither
        # text/html nor application/json (e.g. Accept: */*) used to return
        # None here, which 500s in the CSRF middleware. Serve the same
        # browser view a normal navigation would get instead.
        if request.method == 'GET':
            if use_new_schedule_details_page(course_key):
                return redirect(get_schedule_details_url(course_key))
            settings_context = get_course_settings(request, course_key, course_block)
            return render_to_response('settings.html', settings_context)
```

then `docker restart tutor_local-cms-1`.

Verify: the full Studio flow for the course settings link lands on the authoring
MFE `200 Course Authoring` page (`apps.learn.<domain>/authoring/course/<course>/settings/details`)
with the studio session cookies set; `curl` with `Accept: */*` against the
legacy URL returns 302 to the MFE (not 500) and `Accept: application/json`
still returns the JSON payload.

### 9.6 TEST101 certificates enabled (LMS side)

**Status (2026-09):** `course-v1:InnotelLabs+TEST101+2026_T1` issues real AthenIQ
webview certificates, and the **Signara signing leg is live** via
[`scripts/cert-bridge.py`](../scripts/cert-bridge.py) — see §9.7 below.

One-time setup applied on this deployment (re-apply after a course rerun or
recreate):

1. **Global feature** — `FEATURES["CERTIFICATES_HTML_VIEW"]` must be `True`
   (default in this Tutor release; check `settings.FEATURES`).
2. **Course block** (CMS shell, then publish):
   `cert_html_view_enabled = True`, a certificate definition under
   `course.certificates["certificates"]` (with `is_active: True`, `course_title`,
   `signatories`), and `certificates_show_before_end = True` (the course has no
   end date, so without this the cert is never "viewable").
3. **CourseOverview refresh** (LMS shell):
   `CourseOverview.update_select_courses([course_key], force_update=True)` —
   the denormalized overview lags the modulestore publish and its
   `certificates_display_behavior` / `certificates_show_before_end` / `self_paced`
   values gate cert visibility (`should_certificate_be_visible`).
4. **Set the learner's display name** — the certificate webview renders the
   name from the `GeneratedCertificate.name` / `auth_userprofile.name` fields,
   and the bridge falls back to the **username** when both are empty (which
   produces a certificate with no recipient name). Ensure the learner's real
   name is set before issuing, e.g.:
   `UPDATE auth_userprofile SET name='<Full Name>' WHERE user_id=<id>;`
   (the bridge prefers profile name → certificate-record name → username;
   see §9.7).
5. **Issue a certificate** (LMS shell):
   `CourseEnrollment.get_or_create(user, course_id, mode="honor")` then
   `generate_course_certificate(user, course_key, status="downloadable",
   enrollment_mode="honor", course_grade="0.92", generation_mode="batch")`
   (bypasses the async eligibility queue; writes the `GeneratedCertificate` row
   directly). If the certificate was already issued with an empty name, update
   both the profile and the record:
   `UPDATE certificates_generatedcertificate SET name='<Full Name>' WHERE id=<cert_id>;`

Verified live: the public webview
`https://learn.<domain>/certificates/<verify_uuid>` renders the full certificate
(awarded-to name, course title, "Certificate of Completion", signatory,
issue date) and the learner's dashboard shows the "certificate is ready" link.

**Where the certificate screens are** (probed live — the legacy
`https://learn.<domain>/courses/<course>/instructor` 404s, the dashboard moved
to the MFE):

| What | URL |
| --- | --- |
| Issue / regenerate for learners (instructor dashboard → **Certificates** tab) | `https://apps.learn.<domain>/instructor/instructor-dashboard/<course_id>/certificates` |
| Define signatories (Studio → course → Settings → Certificates) | `https://apps.learn.<domain>/authoring/course/<course_id>/settings/certificates` |
| Certificate records (Django admin) | `https://learn.<domain>/admin/certificates/generatedcertificate/` |
| Per-course generation setting (Django admin) | `https://learn.<domain>/admin/certificates/certificategenerationcoursesetting/` |
| Generation switch (Django admin) | `https://learn.<domain>/admin/waffle/switch/` |

The instructor tab is a client-side route (`instructor-dashboard/:courseId/:tabId`,
the tab is `tabId: "certificates"`), so it answers 200 with the MFE shell for any
path — the evidence that it exists is the route table in the shipped bundle plus
its live API, `/api/instructor/v2/courses/<course_id>/certificates/{issued,
generation_history,invalidations,regenerate,toggle_generation}` (401 without a
session, i.e. present, not 404).

**Fixes applied 2026-10** (this deployment had drifted from the state above):

- The four TEST101 certificates were stored under the **stale course key**
  `course-v1:Innotel+TEST101+2026_T1` while the live course is
  `course-v1:InnotelLabs+TEST101+2026_T1`, so every public verify URL rendered
  "Invalid Certificate" (`webview.py` logs `Course not found`) even though the
  rows were `downloadable` and their Signara documents were signed. Repointing
  `course_id` with a queryset `.update()` (never `save()`) fixed all four;
  `verify_uuid` is untouched, so existing links stay valid.
- `CertificateGenerationCourseSetting` had **0 rows**, so per-course gating ran
  purely off the global switch. All 14 course overviews now have an explicit
  `self_generation_enabled=True` row, so disabling one course is a per-course
  change rather than a global one.
- The public names went **back to `learn.<domain>`** (with `lms.<domain>` kept as
  the alias): `LMS_HOST`, the `MFE_CONFIG` / `PARAGON_THEME_URLS` host strings,
  `django.contrib.sites`, the `apps.learn` edge host, and the OpenMAIC
  `ALLOWED_FRAME_ANCESTORS` allowlist. See
  [Cerulean DNS and TLS](#cerulean-dns-and-tls) for the full re-apply.

> A certificate row's `course_id` is a snapshot: after a course is re-created
> under a new org/slug (as TEST101 was), the row keeps the old key and the
> webview 404s the course. Check `GeneratedCertificate.course_id` against
> `CourseOverview.id` before assuming the TLS/feature-config side is at fault.

### 9.7 Signara signing leg (cert bridge)

**Status (2026-09):** live. The bridge
([`scripts/cert-bridge.py`](../scripts/cert-bridge.py)) watches the LMS for
`downloadable` certificates and pushes each completion through Signara's
signing workflow, so every AthenIQ certificate also exists as a **signed
Signara document** with its audit/evidence trail (see
[docs/Integrations.md](Integrations.md#signara--signed-course-certificates-documentops)).

How it works, per run:

1. Reads new completions from the LMS MySQL (`certificates_generatedcertificate`
   where `status = 'downloadable'`) joined to the learner and course overview.
2. Renders a certificate PDF (pure Python, no dependencies). The learner's
   name comes from `auth_userprofile.name`, then the name recorded on the
   certificate itself (`certificates_generatedcertificate.name`), then the
   username as a last resort — so a certificate never ships with a blank
   recipient name again.
3. Uploads it to Signara, creates a sequential signing request with the
   issuer/signatory (`CERT_SIGNER_*`) as the signer, and signs it via the
   signer's public token.
4. Records each submission in the LMS DB ledger table `atheniq_cert_sync`
   (created automatically) so re-runs are idempotent — a certificate is only
   ever signed once. Upload failures stay unledgered and are retried on the
   next pass; **PARTIAL rows** (document uploaded but the signing request or
   signature call failed) are **auto-resumed** on every pass — the bridge
   re-fetches the request, signs it when still pending (409 "already signed"
   is treated as done), and marks the ledger SIGNED, so a transient Signara
   error never parks a certificate permanently.

Run it on the group-1 (Primary) host next to Tutor and Signara:

```bash
# one pass over everything not yet signed (safe to re-run)
python3 scripts/cert-bridge.py --once
# keep watching for new completions (cron or systemd)
python3 scripts/cert-bridge.py --watch --interval 120
python3 scripts/cert-bridge.py --dry-run   # preview without calling Signara
python3 scripts/cert-bridge.py --status    # ledger health (MySQL only, no Signara calls)
```

**Scheduled service (this host):** a systemd timer runs the bridge every
2 minutes so signing is fully automatic — no manual passes needed:

```bash
sudo cp deploy/systemd/atheniq-cert-bridge.service deploy/systemd/atheniq-cert-bridge.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now atheniq-cert-bridge.timer
journalctl -u atheniq-cert-bridge.service -n 20   # watch runs
```

The unit runs `cert-bridge.py --once` (oneshot) each tick and exits; it needs
`docker` access and either `sudo -u tutor` (default) or `LMS_DB_PASSWORD` set
in the unit's `Environment=`.

Prerequisites (all in `.env`, documented in `.env.example`):
`SIGNARA_API_URL`, `SIGNARA_API_KEY` (a Signara API key scoped to
`documents.*` + `signing.send/read`), and `CERT_SIGNER_NAME/EMAIL/TITLE`.
The LMS MySQL root password is resolved via Tutor (`sudo -u tutor`); set
`LMS_DB_PASSWORD` to override. The bridge authenticates to Signara as a
**machine client** (`X-API-Key`) — no browser session required.

Verified live (2026-09):
- The TEST101 certificate for `darnel` was signed through Signara (request
  `COMPLETED`, signer `SIGNED`); the signed artifact retrieves from
  Signara/MinIO as a valid PDF containing the learner, course, grade,
  certificate UUID, and signatory, and appears on the Signara portal list.
- **Fully automatic pipeline verified end-to-end with a real submission:**
  learner `student.two` answered the graded problem correctly via the live
  `problem_check` endpoint → the LMS recomputed the course grade
  (`percent: 1.0, letter_grade: Pass, passed: True`) → `COURSE_GRADE_NOW_PASSED`
  → the cert worker auto-issued a `downloadable` certificate (`56b3a767…`,
  webview shows "Student Two") → the **scheduled** systemd bridge picked it up
  on the next 2-minute tick and signed it in Signara (doc `188f8dc0…`, SIGNED)
  with no manual step.

Cleanup note: a soft-deleted duplicate document may remain from early test runs
(idempotency was added right after); completed requests cannot be cancelled by
design.

Re-verified live after the PARTIAL auto-resume + `--status` change (2026-09):
`python3 scripts/cert-bridge.py --status` on the group-1 host reports **4/4
ledger rows SIGNED, 0 PARTIAL, 0 awaiting first sync**, and a `--dry-run`
pass finds nothing pending; Signara's own DB shows the matching **COMPLETED**
signing requests; the `atheniq-cert-bridge.timer` is active on its 2-minute
cadence (last run seconds ago).

### 9.8 Automatic certificate issuance on passing (course-completion trigger)

**Status (2026-09):** live. AthenIQ ships the completion trigger natively:
when a learner's grade is recomputed and crosses the course pass threshold
(`GRADE_CUTOFFS`, 0.5 for TEST101), `CourseGradeFactory` emits
`COURSE_GRADE_NOW_PASSED` and the certificates app enqueues the celery task
`lms.djangoapps.certificates.tasks.generate_certificate` (default queue — the
LMS worker picks it up), which writes a `downloadable` `GeneratedCertificate`.
No custom code is required; the only gate is the waffle switch
`certificates.auto_certificate_generation`, which defaults to **OFF**.

Enable it (re-apply after a fresh MySQL volume — the switch is DB-backed):

```bash
# inside the LMS container
cd /openedx/edx-platform && python /path/to/scripts/enable-auto-certificates.py
# or via Tutor
sudo -u tutor -H bash -c 'cd ~ && . tutor-venv/bin/activate && \
  tutor local run lms python manage.py lms shell < scripts/enable-auto-certificates.py'
```

Prerequisites per course (all already configured for TEST101, see §9.6):
`FEATURES["CERTIFICATES_HTML_VIEW"] = True`, `cert_html_view_enabled` on the
course, an active certificate definition with signatories, a passing
`GRADE_CUTOFFS` entry, and a **learner display name** set (profile or
certificate-record `name`) so the webview and signed PDF show the recipient
(see §9.6 step 4).

Verified live end-to-end, twice:
- **Signal-level** — a fresh learner (`student.one`) with a persisted passing
grade (the exact state `CourseGradeFactory._update` writes) fired
`COURSE_GRADE_NOW_PASSED` → the worker logged
`Generated certificate with status downloadable ... for 6 : course-v1:InnotelLabs+TEST101+2026_T1`
→ a `downloadable` certificate (`c5b4408f…`) appeared with recipient
**Student One** on the webview → the bridge pushed it through Signara
(`COMPLETED`, `SIGNED`, signed PDF contains `Student One`), and the learner's
dashboard shows the "certificate is ready" link.
- **Real submission** — learner `student.two` answered the course's graded
  problem via the live `problem_check` endpoint (HTTP, authenticated session);
  the LMS recomputed the grade (`passed: True`), auto-issued certificate
  `56b3a767…`, and the **scheduled** systemd bridge signed it in Signara on
  the next tick with no manual step (see §9.7).

### 9.9 Studio authoring outline crash — course structure must be chapter → sequential → vertical

**Status (2026-09):** fixed on TEST101. The authoring MFE course outline crashed
with `Cannot read properties of undefined (reading 'children')` when a
**vertical was placed directly under a chapter** (no sequential in between).
The outline reducer maps `subsection.childInfo.children` for every section
(`course_structure.child_info.children`), but `create_xblock_info` deliberately
omits `child_info` for verticals, so the MFE read `.children` of `undefined`.

The outline API (`/api/contentstore/v1/course_index/{course_id}`) is the
source of truth — check it before debugging the browser:

```bash
# as a staff user (signed session) — every level must carry child_info
curl -b "studio_session_id=$COOKIE" \
  https://studio.<domain>/api/contentstore/v1/course_index/course-v1:InnotelLabs+TEST101+2026_T1
```

Fix: insert a sequential between the chapter and the vertical (CMS shell,
`xmodule.modulestore`):

```python
with store.bulk_operations(ck):
    course = store.get_course(ck)
    chapter = course.get_children()[0]
    seq = store.create_item(1, ck, "sequential", fields={"display_name": "Introduction"})
    chapter.children = list(chapter.children) + [seq.location]
    store.update_item(chapter, 1)
    seq.children = [v.location for v in chapter.get_children() if v.category == "vertical"]
    store.update_item(seq, 1)
    chapter.children = [seq.location]
    store.update_item(chapter, 1)
    store.publish(course.location, 1)
```

TEST101 is now a full, importable **demo course** authored in
[`courses/demo-course/`](../courses/demo-course/README.md): five chapters
(Welcome, Text/Images/Video, Problem Types, Grading & Certificates, Final
Assessment), six text components, and seven problems covering multiple choice,
checkbox, dropdown, numerical, text, and math expression. Its grading policy is
`Homework` 0.4 / `Final Exam` 0.6 with `GRADE_CUTOFFS: {Pass: 0.5}`. A learner
who answers the graded problems and the final exam correctly passes and
auto-issues a certificate; the auto-issue chain was re-verified with this
policy (learner `student.three`, grade 0.9, cert `c5cfe2b5…`, signed by the
scheduled bridge). Only the structure (chapter → sequential → vertical) is
required for the outline to render — the policy can be anything.

## Operations

- **Backups:** Tutor volumes and the OpenMAIC/Convex Postgres databases are the
  state you must protect. Dump Postgres (`pg_dump`) on a schedule and mirror
  dumps plus courseware media to **ONYX** object storage (off-host).
- **Logs:** `docker compose logs -f` for this repo's services; `tutor local
  logs` for the LMS; retain learner-access audit trails per your policy.
- **Health:** check `/healthz` surfaces where available; confirm NPM hosts and
  certificate renewal via Cerulean's compliance view, and that every public name
  still has a valid certificate of its own with `make cert-check`.
- **Host deploys:** run [`scripts/deploy.sh`](../scripts/deploy.sh) from the
  host's checkout. It refuses to pull over a dirty tree, fast-forwards, reports
  the commits it crossed, `docker compose up -d --remove-orphans`, and finishes
  with the certificate gate. `--no-pull` restarts what is on disk;
  `--no-cert-check` skips the gate. The checkout is a normal `git clone` (its
  `.env` is gitignored and copied in once), which is what keeps
  `docker-compose.yml` and `web/landing/` from drifting away from the repo.
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
  apply to every deployment. In particular, AthenIQ never signs certificates
  itself — Signara does — and no `.env`, key, or token is ever committed.
