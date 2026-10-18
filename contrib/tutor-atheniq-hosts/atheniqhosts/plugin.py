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
""",
    )
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
