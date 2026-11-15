# AthenIQ — Course & School Management Console

The registrar console behind [atheniq.institute](https://atheniq.institute) and
[atheniq.courses](https://atheniq.courses): create and generate courses, publish
them with their price and catalog placement, manage degree plans, and award
certificates and degrees through Signara.

It is a self-hosted Next.js app (Node, no external services required) that speaks
the same shapes the AthenIQ platform already publishes — runtime keys
`course-v1:InnotelLabs+CODE+TERM`, `config/course-prices.json`,
`config/workforce-tracks.json`, the program plans, and OLX course packages.

```bash
npm install
npm run dev        # http://localhost:3100
```

### Hosting

The console is published at `https://registrar.atheniq.institute` through the
Cerulean stack on `192.168.1.71`:

- **DNS** — Technitium, zone `atheniq.institute`. A 300-second A record for
  `registrar` points at the edge's public address, `73.68.203.71` (the same
  address the apex uses).
- **TLS and proxying** — Nginx Proxy Manager host 331 holds a Let's Encrypt
  certificate for the name (renewed automatically) and forwards to
  `http://192.168.1.17:3100`, the console host on the LAN, with WebSocket
  upgrades enabled. TLS is forced; HTTP redirects.
- **Production build behind the edge** — that upstream is `npm run build` then
  `npm run start` on port 3100, not `next dev`; restart `npm start` after a
  deploy so the new build is served.
- **Console address** — `CONSOLE_ORIGIN` (default
  `https://registrar.<brand domain>`) is the origin alert email links back to;
  the brand domain itself serves the public site, so `/staff` links must not use
  it.
- **Security headers** — host 331 sets HSTS (one year, `includeSubDomains`),
  `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`,
  `Permissions-Policy` and `Cross-Origin-Opener-Policy` through the
  headers-more module's `more_set_headers`. A plain server-level `add_header`
  would not reach the browser: NPM's `proxy.conf` sets one inside `location /`,
  and a location-level `add_header` suppresses server-level inheritance.

`next.config.mjs` still lists the origin in `allowedDevOrigins`, so HMR and
server actions keep working when developing against the hostname with
`npm run dev`.

First boot seeds the store from the live AthenIQ catalog: the 16 priced workforce
courses with their real chapter maps, the three published degree plans (BBA, BS
Criminal Justice, ASN Nursing) and the four workforce tracks.

## What it does

### 1. Courses — create, price, publish

- `/courses` — the catalog, filtered by status, program and track. Every row is a
  runtime course key.
- `/courses/new` — author a course record directly.
- `/courses/[id]` — the course editor: overview, curriculum (modules, lesson
  types and minutes, assessments), price and catalog placement.
- **Publish** runs checks (key format, credits, curriculum, grading weights
  summing to 100%, price, placement, summary length, OLX validity) and then:

  1. builds the complete **OLX package** (`course.xml`, run file, chapters,
     sequentials, verticals, HTML lessons, problems, about pages, grading policy);
  2. writes the importable **`.tar.gz`** archive;
  3. writes merge-ready **catalog patches** — `course-prices.patch.json`,
     `workforce-tracks.patch.json`, `program-plans.patch.json`, the LMS
     `listing.json` (the exact shape `atheniq.courses` serves) and
     `olx-import.txt`;
  4. if an LMS import endpoint + token are configured, POSTs the archive;
  5. marks the course published and records it in the activity log.

  Everything lands in `data/published/<CODE>-<TERM>/`. If no import endpoint is
  configured the console says so — the bundle and patches are the hand-off to the
  repo's `scripts/import-courses.py` / `scripts/publish-courses.py` pipeline
  rather than a silent no-op.

### 2. Course studio — generate from an idea, then refine it

`/generate` turns a sentence into a complete course draft: outcomes, 3–6 modules,
lessons by type and length, assessment per module and a grading mix that sums to
100%. Each further instruction ("make it practical", "add a compliance module",
"3 credits", "for front-desk staff", "rigorous, with seminars", "rename it to…")
produces a **new version** with a changelog. When it is right, accept it into the
catalog — it gets the next free course code, term, price plan and placement, and
either opens in the course editor as a draft or, with **publish immediately**
ticked, runs the publish checks and goes live in the same step.

Two engines, same output contract:

- **Model gateway** — any OpenAI-compatible endpoint. In the AthenIQ stack that is
  OmniRoute (`OMNIROUTE_BASE_URL`, `OMNIROUTE_MODEL`, `OMNIROUTE_API_KEY`). The
  response is coerced back into the draft schema and validated, so a malformed
  reply cannot reach the catalog.
- **Curriculum rules** — deterministic, dependency-free. Used when no key is
  configured or the gateway fails. Produces a structurally complete, publishable
  course; the UI states which engine wrote the draft.

### 3. School — degrees, tracks, tuition

- `/programs` — the three published plans with credits, semesters, tuition
  (credits × rate) and conferral readiness.
- `/programs/[id]` — edit the plan: semesters, the courses in each, total credits,
  per-credit rate, status, accreditation statement, and the conferral queue with
  each learner's earned credit and GPA.

Tuition follows the institute's published rate: **$325 per credit**, one rate for
every program (BBA/BS 120 credits = $39,000; ASN 75 credits = $24,375).

### 4. Credentials — Signara award management

`/credentials` is the award center for three credential types: course
certificates, workforce track credentials and degree conferrals.

Issuing one:

1. **Eligibility is checked first** — a passing completion for the course, every
   course in the track, or every credit on the degree plan. A registrar can
   override, and the override is recorded.
2. The certificate is **rendered to PDF** server-side (no dependencies) with the
   learner, subject, evidence, verification id and evidence hash.
3. It is submitted to **Signara** exactly as the platform's cert bridge does:
   `POST /api/v1/documents/upload` (multipart) → `POST /api/v1/signatures/requests`
   → `POST /api/v1/signatures/public/{token}/sign` (typed signature), all with
   `X-API-Key`.
4. The award is **issued to the learner record** with its document id, request id,
   timeline and evidence hash.

Without a Signara key, awards are rendered and **held locally** (`queued_local`)
with the reason shown — re-submitting after the key is set picks up exactly where
it stopped. Awards can be re-submitted, marked issued, or revoked with a reason;
a revocation is visible on the public verification page.

`/verify/[verificationId]` is the public check an employer or licensure board
uses: valid, revoked, or not yet issued, with the award record, evidence hash and
signed PDF.

## Configuration

Everything is set in **Integrations** (`/integrations`) and stored server-side in
`data/store.json`; secrets are never returned to the browser.

| Setting | Purpose |
| --- | --- |
| `lms.baseUrl` / `lms.catalogUrl` | The course engine and its catalog |
| `lms.importUrl` / `lms.apiToken` | Optional import endpoint; blank = build the bundle only |
| `signara.baseUrl` / `signara.apiKey` / `signara.autoSign` | Signing workflow |
| `signer.*` | The signatory on signing requests |
| `ai.baseUrl` / `ai.apiKey` / `ai.model` | Model gateway for the course studio |
| `org`, `orgShort`, `defaultTerm` | Publication identity and the key org |
| `tuitionPerCreditCents`, fees | Tuition arithmetic |

Environment variables are optional defaults for a first boot:

```env
OMNIROUTE_BASE_URL=http://192.168.1.71:20128/v1
OMNIROUTE_API_KEY=
OMNIROUTE_MODEL=auto
SIGNARA_API_URL=https://api.signara.innotel.us
SIGNARA_API_KEY=
CERT_SIGNER_NAME="D. Hunter"
CERT_SIGNER_TITLE="Founder - Innotel"
CERT_SIGNER_EMAIL=dhunter@innotel.us
AUTH_PASSWORD=          # bootstraps the first registrar; empty leaves the console open
AUTH_EMAIL=dhunter@innotel.us   # the bootstrap account's sign-in address
AUTH_NAME="D. Hunter"
AUTH_SECRET=            # optional dedicated session-signing secret
```

`Test LMS`, `Test Signara` and `Test gateway` probe the saved values and report
the actual HTTP outcome — a rejected key is reported as rejected, not as
"unavailable".

## Layout

```
app/                    pages (dashboard, courses, studio, programs, credentials, verify, integrations)
app/api/                route handlers for every mutation
components/             client editors, publish panel, studio, credential actions
lib/types.ts            the domain model
lib/seed.ts             the live catalog, plans and tracks
lib/store.ts            single-writer JSON store with atomic writes
lib/curriculum.ts       deterministic draft synthesis + revision rules
lib/ai.ts               OpenAI-compatible client, schema coercion, fallback
lib/publish.ts          OLX package, tar.gz, catalog patches, LMS push
lib/signara.ts          PDF renderer + Signara client
lib/eligibility.ts      completion, track and degree eligibility
lib/session.ts          password check, session cookie signing
middleware.ts           gates console routes, leaves /verify public
data/                   store, published bundles, certificates (gitignored)
```

## Notes and limits

- **Storage is a JSON store** (`data/store.json`, atomic writes, serialised
  mutations) because this is a single-operator registrar surface. The domain
  types are the migration boundary: swapping in Postgres/D1 means reimplementing
  `lib/store.ts`, nothing else.
- **Staff accounts, each with their own password.** Set `AUTH_PASSWORD` (and
  preferably a separate `AUTH_SECRET`) and `middleware.ts` requires a signed
  session cookie for every console page and API route. `AUTH_PASSWORD` seeds a
  single bootstrap registrar (`AUTH_EMAIL`); open **Staff** to add everyone else,
  change roles, reset a password, or disable an account, and the sidebar shows
  who is signed in. Sessions name their account, so every publish, award and
  settings change records **who did it** on the activity trail. Two roles:
  registrars do everything; publishers create, revise and publish courses but
  cannot award credentials or change integrations — enforced in the route
  handlers, not just hidden in the UI. The last active registrar cannot be
  removed or demoted. `/verify` and `/api/verify/*` stay public so an employer
  can check a credential without an account. Unset `AUTH_PASSWORD` and the
  console is open, which is the local-development default. For SSO, keep
  Authentik / oauth2-proxy in front as well — it only adds a layer.
- **Two-factor and domain-locked accounts.** Two-factor is required by
  default: an unenrolled account is walked through enrolment at its first
  sign-in — a QR code, the setup key and the `otpauth://` URI, then eight
  single-use recovery codes once a code confirms the app. Any TOTP app works;
  in Vaultwarden or Bitwarden, scan the code or paste the key into a login
  item's authenticator field. `/security` offers the same **Set up
  authenticator** flow to a signed-in account, and `AUTH_REQUIRE_2FA=off` makes
  the password sufficient until the person enrols. Set `AUTH_REQUIRE_2FA=on` to force enrolment at the first sign-in
  instead, and a freshly reset account then re-enrols the same way. Staff emails must end with a registered domain
  (`STAFF_EMAIL_DOMAINS`, editable on the Staff page as the sign-in policy),
  enforced both when an account is created and when it signs in; subdomains
  count, look-alike domains do not. Registrars can reset an account's
  two-factor, after which it signs in with the password again.
- **Passkeys.** Signed-in staff can add a passkey from `/security`; the login
  page then offers passkey sign-in beside the password form. There is no
  WebAuthn dependency: the server checks the attestation object (CBOR), the
  COSE key, origin, RP ID, challenge and signature itself (ES256 and RS256),
  and refuses a passkey whose signature counter does not advance. Passkeys
  need a secure origin with a domain — use `http://localhost:3100`, not an IP —
  and a successful assertion counts as a complete two-factor sign-in. A passkey
  is bound to the host that created it, so one registered on `localhost` will
  not appear on `registrar.atheniq.institute`.
- **Vaultwarden accounts.** Creating a staff account also registers that
  address on the vault (`VAULTWARDEN_URL`) with the password the console was
  given, and stores the vault's user id on the staff record — the row shows a
  **Vault** chip. An approved access request gets a generated vault password
  instead, shown once to the approving registrar, because the request only kept
  a hash. The console never stores a vault master key; a failure to reach the
  vault leaves the console account in place and records the reason.
- **Security page.** `/security` shows your own factors, and for registrars the
  accounts table (two-factor enrolled or pending, passkey counts), the failed
  sign-in log (wrong password, blocked domain, rejected code, rejected passkey)
  and the access-request queue. Passwords are never written to that log.
- **Access requests.** `/request-access` is public: someone on a registered
  domain asks for an account and chooses a password, which is stored hashed
  until a registrar approves the request on the Staff page. Approval creates a
  publisher account that enrols two-factor at its first sign-in; declining
  leaves no account behind. `/staff` keeps the last eight decisions with who
  made them.
- **Registrar alerts.** With mail configured (either SMTP submission via
  `MAIL_SMTP_HOST`/`MAIL_SMTP_USER`/`MAIL_SMTP_PASS` or an HTTP relay via
  `MAIL_API_KEY`, plus `MAIL_FROM`), registrars get an email for each new access
  request, and one alert when an address fails three times within fifteen
  minutes. A dedicated address set under Health → Operations digest receives
  them instead of every registrar; `ALERT_TO` seeds that value on first boot.
  Alerts are best-effort: an unconfigured or unreachable relay never changes the
  answer the person signing in receives.
- **Sign-in throttle.** Five refusals for one address inside fifteen minutes
  pause its password and authenticator-code sign-in until the oldest refusal
  ages out, answered with `429` and a retry time. A single source gets ten
  refusals in the same window, so one address spraying many accounts stops too.
  The window is derived from the sign-in log, so a restart does not clear it,
  and passkeys stay available — otherwise anyone could lock the owner out of
  their strongest factor. `/security` lists everything currently paused with an
  Unlock button for registrars.
- **Session cap.** A source can hold at most three live sessions; a fourth
  sign-in ends the oldest, so nobody is refused because of old tabs. Sessions
  are signed cookies plus a registry row, so sign-out and eviction stop a
  cookie working on the next request that resolves the account. Middleware's
  signature check alone is stateless, so a revoked cookie may still load a page
  shell before the page redirects. `/security` lists every live session with
  its source, start time and time left before it expires on its own, can end one
  of them, and offers registrars a **Sign out everywhere** that ends them all —
  including the registrar's own browser — with the act recorded in the activity
  trail. A session opened from an address that person has never signed in from
  is marked **new source**; the list of seen sources lives on the account, so
  clearing the sign-in log does not erase it. Each person's page (`/staff/<id>`)
  lists their own sessions with an **End all for …** action. Ending any session
  other than your own — a single one, a person's set, or sign out everywhere —
  asks for a fresh authenticator code first when the registrar has one enrolled,
  so a borrowed browser cannot throw everyone else out. `/security` keeps the
  last eight ended sessions with the reason and who ended them. Disabling an
  account, resetting a second factor and removing an account each ask for a
  fresh code too — or a passkey assertion, which is offered as **Use a passkey**
  in the same prompt and returns a two-minute ticket the server accepts in place
  of the code — so a browser left signed in elsewhere cannot take someone's
  access away. One confirmation covers further destructive actions in the same
  session for up to five minutes and only while the browser stays open — it is a
  session cookie, so closing the browser ends it early — so tidying up several
  accounts is one code or one passkey, not one per row. The security page, the
  staff list and each person's page show how long it has left, the security page
  can forget it early, and clearing it is recorded on the activity trail; any of
  them ends every live session it
  holds, and a sign-in from a new network source or a change to someone's access
  emails the registrar list once mail is configured (`MAIL_SMTP_*` or
  `MAIL_API_KEY`, with `MAIL_FROM`) —
  best-effort, and never able to delay or fail a sign-in.
- **Health and rotation.** `/health` (registrars) probes Signara, the model
  gateway and the LMS on every load, and counts down to the Signara key's
  expiry — record the expiry there when you paste a new key, and the dashboard
  raises a banner inside the last 30 days. `/api/health` returns the same thing
  as JSON for monitoring. Each staff account also has an audit page
  (`/staff/<id>`) listing everything that account published, awarded or
  revised. Both the staff page and each person's page export that trail as CSV
  (`/api/audit/export`, optionally `?staffId=`), and `/health` can mint a
  replacement Signara key in place (needs `SIGNARA_ADMIN_SECRET`; the new key
  requests the award scopes in `SIGNARA_KEY_SCOPES`, and is proven against
  Signara before it replaces anything) and email the
  digest (needs `MAIL_SMTP_*` or `MAIL_API_KEY`, plus `MAIL_FROM`; `DIGEST_TOKEN` lets a scheduler
  POST `/api/health/digest?token=…`).
- **The public website.** `/website` (registrars) owns the front-facing site:
  name, tagline, logo image or monogram, logo placement, accent colour, support
  address, domain and the section toggles. `/site` is the live preview, and any
  host in `PUBLIC_SITE_HOSTS` (default `atheniq.institute`) is rewritten to it
  with no staff session. The site is derived, never copied: published courses,
  active programs and signed credentials appear from the platform, and every
  price is USD, formatted from the same cents the console bills. Because the
  brand is data, the same console can serve another school under another
  domain — that is the white-label path. Point DNS at the console host, set the
  domain, and `poweredBy` controls the AthenIQ credit line. The console itself
  answers on its own host — `registrar.atheniq.institute` in production — because
  any host not in `PUBLIC_SITE_HOSTS` is treated as the console; `next.config.mjs`
  lists that origin for `next dev`, so browsing through the real hostname keeps
  HMR and server actions working. On the console host the name resolves to
  `192.168.1.71` so the LAN path goes through the Cerulean edge and gets the
  public certificate. `http://localhost:3100` stays a secure context for
  passkeys; a bare LAN address over plain HTTP is not.
- **The LMS import is optional.** Open edX imports normally run in the CMS
  container (`python3 scripts/import-courses.py … --execute`); point
  `lms.importUrl` at an endpoint if one is exposed, otherwise use the generated
  archive and patches.
- **Signara's API is used as the repo's cert bridge uses it.** If your Signara
  build exposes a different route list, the probe reports the HTTP status and the
  ledger keeps the document so nothing is lost.
