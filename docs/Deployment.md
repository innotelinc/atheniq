# AthenIQ — Deployment

This runbook brings up the AthenIQ learning platform on one self-hosted host.
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
git clone https://github.com/innotelinc/atheniq.git
cd atheniq
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
| `atheniq-lms` | Tutor LMS + Studio OAuth callback |
| `atheniq-classroom` | OpenMAIC sign-in callback |
| `atheniq-studio` | Media studio (optional) |

**Realized (2026-09):** `atheniq-lms` is live on Cerulean's Authentik
(`auth.cerulean.innotel.us`, client id `atheniq-lms`). Open edX is enabled via
the Tutor plugin in [`contrib/tutor-ceruleansso`](../contrib/tutor-ceruleansso)
(installed as `tutor-ceruleansso` in the tutor venv): it sets
`FEATURES["ENABLE_THIRD_PARTY_AUTH"]`, registers python-social-auth's
`OpenIdConnectAuth` backend (`oidc`), and points
`SOCIAL_AUTH_OIDC_OIDC_ENDPOINT` at
`https://auth.cerulean.innotel.us/application/o/atheniq-lms`. The TPA
`ProviderConfig` row (site = default, backend `oidc`) holds the client id/secret;
Authentik redirect URIs are `https://learn.innotel.us/auth/complete/oidc/` and
`https://studio.innotel.us/auth/complete/oidc/` (strict). LMS verified:
auth entry redirects to Authentik authorize and returns to the login flow; the
container reaches Authentik discovery over the edge. Full browser sign-in needs
the `learn`/`studio.innotel.us` NPM edge hosts + DNS (see [Cerulean DNS and TLS](#cerulean-dns-and-tls)).

Use the Authentik authorization/`userinfo` endpoints in `.env` (`OIDC_*`) and
apply the same group claims (`learners`, `instructors`, `atheniq-admins`,
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
   certificates and an API token for AthenIQ.
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

**Realized (2026-09):** `learn`, `studio`, `apps.learn`, and
`meilisearch.learn` (`innotel.us`) are live. DNS records are CNAMEs to the
`innotel.us.` apex (A `73.68.203.71`, the NPM edge) in the authoritative BIND
zone, written via TSIG `nsupdate` (key `cerulean`, BIND at `192.168.1.80`).
NPM hosts forward to `http://192.168.1.46:18080` (Tutor caddy): `learn` and
`studio` attach the existing `*.innotel.us` wildcard (NPM cert 110);
`apps.learn` and `meilisearch.learn` use single-name Let's Encrypt certs
(HTTP-01) because NPM's own wildcard issuance (`rfc2136` DNS provider)
currently returns 500 — request a `*.learn.innotel.us` wildcard once that is
fixed. Run [`scripts/provision-edge.sh`](../scripts/provision-edge.sh) to
re-apply (idempotent). Public HTTPS verified for all four hosts.

> Scheme note: Tutor runs with `ENABLE_HTTPS=true` and `ENABLE_WEB_PROXY=false`
> (its own caddy stays plain HTTP on `:18080`; NPM terminates TLS). This makes
> Open edX emit `https://` absolute URLs — required, since the browser would
> otherwise block the MFEs' API calls as mixed content (this broke the catalog
> MFE at `https://apps.learn.innotel.us/catalog/` until flipped). To re-apply
> after a Tutor reinstall: `tutor config save --set ENABLE_HTTPS=true` then
> `docker compose -p tutor_local -f docker-compose.yml -f
> docker-compose.prod.yml restart lms cms mfe caddy`.

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

1. **Redirect-uri scheme mismatch** — the Tutor Open edX plugin's CMS settings
   template (`partials/common_cms.py`) hardcodes
   `SOCIAL_AUTH_REDIRECT_IS_HTTPS = False`, so the CMS builds the redirect_uri
   from the **request's scheme**. The CMS receives plain HTTP from the edge
   (TLS terminated at NPM/Caddy), so it sends
   `http://studio.innotel.us/auth/complete/oidc/` → does not match the
   registered `https://...` URI → `invalid_request`. The LMS is unaffected
   because its settings leave the flag unset (defaults to HTTPS).
2. **CMS never had the TPA urls.** Stock Open edX ships the TPA urlconf
   (`common.djangoapps.third_party_auth.urls`, which provides
   `/auth/login/<backend>/` and `/auth/complete/<backend>/`) in the **LMS
   only**; the CMS urlconf lacks it, so Studio's callback 404'd.
3. **CMS never had the TPA machinery.** `third_party_auth` is not in the CMS
   `INSTALLED_APPS`, `SOCIAL_AUTH_PIPELINE` is not defined there (LMS-only in
   `lms/envs/common.py`), and CMS lacks `TPA_PROVIDER_BURST_THROTTLE` /
   `TPA_PROVIDER_SUSTAINED_THROTTLE` / `PROFILE_MICROFRONTEND_URL`. Without the
   TPA pipeline, social-auth's raw `create_user` crashes on Open edX profile
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
   `INSTALLED_APPS` + its `ExceptionMiddleware`, the Open edX
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

**Status (2026-09):** `course-v1:Innotel+TEST101+2026_T1` issues real Open edX
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

### 9.7 Signara signing leg (cert bridge)

**Status (2026-09):** live. The bridge
([`scripts/cert-bridge.py`](../scripts/cert-bridge.py)) watches the LMS for
`downloadable` certificates and pushes each completion through Signara's
signing workflow, so every Open edX certificate also exists as a **signed
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

### 9.8 Automatic certificate issuance on passing (course-completion trigger)

**Status (2026-09):** live. Open edX ships the completion trigger natively:
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
`Generated certificate with status downloadable ... for 6 : course-v1:Innotel+TEST101+2026_T1`
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
  https://studio.<domain>/api/contentstore/v1/course_index/course-v1:Innotel+TEST101+2026_T1
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

Also added to TEST101: **graded problems** (`problem_check`-style
multiple-choice) under each unit, and the course grading policy is the
realistic multi-assignment set (`Homework` 0.2 / `Lab` 0.2 / `Midterm Exam`
0.25 / `Final Exam` 0.35, `GRADE_CUTOFFS: {Pass: 0.5}`) — the same shape a
real course uses. The current catalog: section *Welcome* → **Final Exam**
(1 problem), **Homework 1** (2 problems), **Lab 1** (1 problem), **Midterm
Exam** (1 problem). A learner who answers them all correctly passes (~0.9) and
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
  apply to every deployment. In particular, AthenIQ never signs certificates
  itself — Signara does — and no `.env`, key, or token is ever committed.
