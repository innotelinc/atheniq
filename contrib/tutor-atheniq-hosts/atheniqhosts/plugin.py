"""AthenIQ — the platform answers on more than one name.

WHAT THIS PLUGIN IS. `LMS_HOST` names one hostname, and Tutor bakes that one
name into the caddy config, the LMS settings and the MFEs. Renaming the
platform therefore stops the other name answering on the next deploy — right
when every link, bookmark, course email and QR code written before the rename
still names it. The deployment has moved twice (`learn.<domain>` → `lms.<domain>`
→ back to `learn.<domain>`, with `lms.<domain>` now the alias), so which name is
canonical is configuration, not something to patch by hand.

WHY A PLUGIN. `apps/openedx/settings/lms/production.py` and
`apps/caddy/Caddyfile` are regenerated from templates on every
`tutor config save`; an edit made by hand survives until the next deploy and
then disappears, which is the same failure `contrib/tutor-atheniq-theme`
exists to prevent. This makes the extra names part of the configuration
instead of part of a container's writable layer.

WHAT IT DOES. For every host in `ATHENIQ_LEGACY_LMS_HOSTS`:

1. it is appended to `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
   `CORS_ORIGIN_WHITELIST` and `LOGIN_REDIRECT_WHITELIST`, because Django
   answers 400 to a host it was not told about, 403 to a form post from an
   origin it does not trust, and refuses to redirect back to a host it was not
   told is ours; and
2. it gets a caddy site block that proxies to the LMS, so the name reaches the
   same application the canonical one does.

For every host in `ATHENIQ_LEGACY_MFE_HOSTS` the same is true except
`ALLOWED_HOSTS`: the learner MFEs are static bundles served by the `mfe`
container, so the LMS only has to trust their origin — the bundle itself is
host-agnostic and reads its configuration from the LMS, so it follows a rename
without being rebuilt.

It also moves the learner apps onto the LMS host under their own paths
(`/catalog`, `/learning`, `/learner-dashboard`, `/authn`, …) and proxies the
bundles those pages ask for. Both halves are needed: the path returns the app's
HTML, and the bundles at the app's origin root are what make it render. Pointing
only the paths at the MFE serves an empty `<div id="root">` — the page loads and
stays blank, because the LMS answers 404 to `/app.<hash>.js`.

`/dashboard` is the exception: the platform links to that path, the `mfe`
container serves the app at `/learner-dashboard`, and anything else lands on the
container's root shell, which renders nothing. It redirects instead.

It also carries `ATHENIQ_SESSION_COOKIE_DOMAIN`, which is session unification
rather than host naming: set to `.innotel.us`, the LMS and the CMS both write
`sessionid`/`csrftoken` for the whole domain, so Studio and the MFEs open on the
session the learner already has instead of each starting a second sign-in. Empty
by default — one cookie on every name under the domain is a deployment decision.

Both lists are data, not code: drop a host from `config.yml` and `tutor config
save`, and that name stops answering. The canonical host is not listed — Tutor
already emits it. Both lists ship empty, so a fresh install answers only on its
canonical hostnames. Keeping another name alive is a deliberate `--set` (and,
for public reachability, its own edge host), not something the plugin does on
its own.

INSTALL

    pip install -e contrib/tutor-atheniq-hosts
    tutor plugins enable atheniqhosts
    tutor config save
    tutor local restart caddy lms

Nothing is rebuilt: both patches are text in files the containers mount.
"""

from __future__ import annotations

from tutor import hooks

#: LMS hostnames the platform answers on beyond the canonical `LMS_HOST`. Empty
#: by default: a name is only kept while something still links to it, and the
#: list is data, so naming a host is a deliberate decision rather than a
#: leftover of a rename.
hooks.Filters.CONFIG_DEFAULTS.add_item(
    ("ATHENIQ_LEGACY_LMS_HOSTS", [])
)

#: Learner-MFE hostnames beyond the canonical `apps.<LMS_HOST>`. They are served
#: by the `mfe` container, not the LMS, so they need their own blocks and the
#: LMS needs to trust their origins. Empty by default, like the list above.
hooks.Filters.CONFIG_DEFAULTS.add_item(
    ("ATHENIQ_LEGACY_MFE_HOSTS", [])
)

#: The cookie domain every Open edX service should agree on, e.g. `.innotel.us`.
#: Empty by default, which leaves Tutor's per-host cookies exactly as they are.
#: Setting it is *session unification*: the LMS sets its session cookie for the
#: whole domain, so Studio (`studio.<domain>`) and the MFEs read the session the
#: learner already has instead of each asking for a second sign-in. It is a
#: deployment decision because it means one cookie is sent to every name under
#: the domain — including names that are not the LMS — so the value belongs in
#: `config.yml`, not in this plugin.
#:
#: The services must share a `SECRET_KEY` and session backend for this to work;
#: Tutor already does both for the LMS, CMS and the workers.
hooks.Filters.CONFIG_DEFAULTS.add_item(
    ("ATHENIQ_SESSION_COOKIE_DOMAIN", "")
)

#: Django-side: the host is answerable, its forms are trusted, XHR from it is
#: allowed and login may return to it. Appended rather than assigned so Tutor's
#: own values (and anything another plugin adds) stay exactly as configured.
hooks.Filters.ENV_PATCHES.add_item(
    (
        "openedx-lms-production-settings",
        """
{% for host in ATHENIQ_LEGACY_LMS_HOSTS %}
# AthenIQ: another LMS hostname — same application, so the same trust.
ALLOWED_HOSTS.append("{{ host }}")
CSRF_TRUSTED_ORIGINS.append("https://{{ host }}")
CORS_ORIGIN_WHITELIST.append("https://{{ host }}")
LOGIN_REDIRECT_WHITELIST.append("{{ host }}")
{% endfor %}
{% for host in ATHENIQ_LEGACY_MFE_HOSTS %}
# AthenIQ: another MFE hostname. Django never serves it, but the bundle there
# posts to this LMS with the learner's session, so its origin has to be trusted.
CSRF_TRUSTED_ORIGINS.append("https://{{ host }}")
CORS_ORIGIN_WHITELIST.append("https://{{ host }}")
LOGIN_REDIRECT_WHITELIST.append("{{ host }}")
{% endfor %}
{% if ATHENIQ_SESSION_COOKIE_DOMAIN %}
# AthenIQ: one session across every name the platform answers on. Studio and
# the MFEs then open on the session the LMS already set, instead of each one
# starting a second sign-in under its own hostname.
SESSION_COOKIE_DOMAIN = "{{ ATHENIQ_SESSION_COOKIE_DOMAIN }}"
CSRF_COOKIE_DOMAIN = "{{ ATHENIQ_SESSION_COOKIE_DOMAIN }}"
SESSION_COOKIE_SAMESITE = "Lax"
{% endif %}
""",
    )
)

#: The CMS (Studio) side of the same decision. Studio reads the LMS session
#: cookie, so it must trust the same domain and the same origins, or the cookie
#: arrives and Django still refuses the POST.
hooks.Filters.ENV_PATCHES.add_item(
    (
        "openedx-cms-production-settings",
        """
{% if ATHENIQ_SESSION_COOKIE_DOMAIN %}
# AthenIQ: the same session as the LMS, so authoring does not ask again.
SESSION_COOKIE_DOMAIN = "{{ ATHENIQ_SESSION_COOKIE_DOMAIN }}"
CSRF_COOKIE_DOMAIN = "{{ ATHENIQ_SESSION_COOKIE_DOMAIN }}"
SESSION_COOKIE_SAMESITE = "Lax"
{% endif %}
""",
    )
)

#: The learner apps served on the LMS host itself, under their own paths. Tutor
#: otherwise names them on `MFE_HOST` (default `apps.<LMS_HOST>`), which fragments
#: the university across two origins: the catalog and dashboard live on one,
#: sign-in and the landing page on the other.
#:
#: The `mfe` container already routes each app by its path (`/catalog/...`), so a
#: plain `handle` (no prefix stripping) forwards them unchanged. These are added
#: to the LMS site block *before* its catch-all `handle_path /*`, so a request for
#: `/catalog/courses` reaches the MFE while everything else — `/login`, `/api`,
#: `/static`, `/courses` — still goes to the LMS.
MFE_PATHS = (
    "catalog", "learning", "learner-dashboard", "profile", "account",
    "discussions", "authoring", "communications", "gradebook", "ora-grading",
    "admin-console",
    # The LMS redirects /login and /register here; without the proxy the
    # redirect lands on the LMS's 404.
    "authn",
)
hooks.Filters.ENV_PATCHES.add_item(
    (
        "caddyfile-lms",
        "\n".join(
            '# AthenIQ: the learner app lives on the university host, not a second domain.\n'
            f'handle /{path}* {{\n    reverse_proxy mfe:8002\n}}'
            for path in MFE_PATHS
        ),
    )
)

#: The learner dashboard is the one app whose name in the platform and whose path
#: in the `mfe` container disagree. Everything links to `/dashboard`
#: (`student_dashboard`, the account page, every emailed course link), while the
#: container serves the app at `/learner-dashboard` — its own base path, which is
#: what its chunks and its router are built against. `/dashboard` matches no app
#: path there, so the container falls back to its root site shell, whose only
#: route is `/`: a 200 response, `<div id="root">`, and nothing inside it. A
#: redirect rather than a rewrite, so the address bar ends up on the path the app
#: believes it is on and its own links keep working.
DASHBOARD_FROM = "dashboard"
DASHBOARD_TO = "learner-dashboard"
hooks.Filters.ENV_PATCHES.add_item(
    (
        "caddyfile-lms",
        "# AthenIQ: /dashboard is the URL the platform links to; the app is served\n"
        f"# at /{DASHBOARD_TO} in the mfe container.\n"
        # A capture group rather than `uri strip_prefix`: a `redir` reads
        # `{uri}` as the request arrived, so stripping first would still emit
        # `/learner-dashboard/dashboard`.
        f"@atheniq_dashboard path_regexp ^/{DASHBOARD_FROM}(/.*)?$\n"
        "redir @atheniq_dashboard "
        f"/{DASHBOARD_TO}{{re.atheniq_dashboard.1}} 302",
    )
)

#: The app paths above return the MFE's `index.html`; they do not return the
#: files that page is made of. An MFE is a single-page app built to sit at the
#: *root* of its own origin: its shell asks for `/runtime.<hash>.js`,
#: `/app.<hash>.js`, `/cssLayerOrder.<hash>.css`, one chunk per route and the
#: Unity skin at `/site/atheniq-unity.css` — all absolute, none of them under
#: `/dashboard`. On `apps.<LMS_HOST>` that is invisible, because the whole site
#: block proxies to `mfe:8002`. Here they match no `handle`, so they fall through
#: to the LMS's catch-all and Django answers 404: the HTML arrives, every script
#: it names does not, and the page renders as an empty `<div id="root">`.
#:
#: So the MFE's own files are proxied too. The matcher is deliberately narrow —
#: a root-level `.js`/`.css`, the `/site/` prefix, `asset-manifest.json` and
#: `/static/mfe/` — because everything else on this host (`/static/atheniq/…`
#: course photographs, `/theming/`, `/api`, `/login`, `/courses`) belongs to the
#: LMS and must keep going there.
MFE_ASSET_PATTERN = r"^/(?:[^/]+\.(?:js|css)|site/.*|asset-manifest\.json|static/mfe/.*)$"

hooks.Filters.ENV_PATCHES.add_item(
    (
        "caddyfile-lms",
        "# AthenIQ: the bundles the MFE's own shell asks for, from the MFE's dist\n"
        "# root rather than an app path. Without these the app paths above return a\n"
        "# page whose scripts 404 and render nothing.\n"
        f"@atheniq_mfe_assets path_regexp {MFE_ASSET_PATTERN}\n"
        "handle @atheniq_mfe_assets {\n    reverse_proxy mfe:8002\n}",
    )
)

#: The MFE configuration is generated from `MFE_HOST`; every absolute URL in it
#: therefore points at `apps.<LMS_HOST>`. Re-point those values at the LMS host so
#: the bundles' links, redirects and API callbacks all stay on one domain. The
#: bundles are host-agnostic — they read this configuration at runtime — so no
#: MFE image is rebuilt.
hooks.Filters.ENV_PATCHES.add_item(
    (
        "openedx-lms-production-settings",
        """
def _atheniq_one_domain(value):
    if isinstance(value, str):
        return value.replace("https://{{ MFE_HOST }}", "https://{{ LMS_HOST }}")
    if isinstance(value, list):
        return [_atheniq_one_domain(item) for item in value]
    if isinstance(value, dict):
        return {key: _atheniq_one_domain(item) for key, item in value.items()}
    return value

MFE_CONFIG = _atheniq_one_domain(MFE_CONFIG)
FRONTEND_SITE_CONFIG = _atheniq_one_domain(FRONTEND_SITE_CONFIG)
FRONTEND_SITE_CONFIG.setdefault("commonAppConfig", {})["MFE_CONFIG"] = MFE_CONFIG

# The MFE settings also live in individual module-level URLs (the LMS templates
# and Studio redirects read these, not MFE_CONFIG). Rewrite every public string
# that still names the apps host, so no link leaves the university domain.
for _atheniq_name, _atheniq_value in list(globals().items()):
    if (_atheniq_name.isupper() and isinstance(_atheniq_value, str)
            and "https://apps.learn.innotel.us" in _atheniq_value):
        globals()[_atheniq_name] = _atheniq_value.replace(
            "https://apps.learn.innotel.us", "https://learn.innotel.us")
""",
    ),
    priority=hooks.priorities.LOW,
)

#: Studio's own links to the authoring and catalog apps are generated from
#: `MFE_HOST` too; they must land on the same host as the learner.
hooks.Filters.ENV_PATCHES.add_item(
    (
        "openedx-cms-production-settings",
        """
COURSE_AUTHORING_MICROFRONTEND_URL = COURSE_AUTHORING_MICROFRONTEND_URL.replace(
    "https://{{ MFE_HOST }}", "https://{{ LMS_HOST }}"
)
CATALOG_MICROFRONTEND_URL = CATALOG_MICROFRONTEND_URL.replace(
    "https://{{ MFE_HOST }}", "https://{{ LMS_HOST }}"
)
""",
    ),
    priority=hooks.priorities.LOW,
)

#: Edge-side: the same name reaches the same application. The `caddyfile` patch
#: point sits after Tutor's own site blocks, so these are additional hosts,
#: never overrides.
hooks.Filters.ENV_PATCHES.add_item(
    (
        "caddyfile",
        """
{% for host in ATHENIQ_LEGACY_LMS_HOSTS %}
# AthenIQ: another LMS hostname, kept in front of the same application.
{{ host }}{$default_site_port} {
    import proxy "lms:8000"
}
{% endfor %}
{% for host in ATHENIQ_LEGACY_MFE_HOSTS %}
# AthenIQ: another MFE hostname. The bundle is host-agnostic and reads its
# config from the LMS, so it serves the renamed platform correctly.
{{ host }}{$default_site_port} {
    import proxy "mfe:8002"
}
{% endfor %}
""",
    )
)

# Declarative hooks surface expected by the Tutor plugin loader (v0).
hooks: dict = {}
