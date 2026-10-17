"""AthenIQ — the LMS answers for the names it carried before the move.

WHAT THIS PLUGIN IS. `LMS_HOST` names one hostname, and Tutor bakes that one
name into the caddy config, the LMS settings and the MFEs. Moving the platform
from `learn.<domain>` to `lms.<domain>` therefore stops the old name answering
on the next deploy — right when every link, bookmark, course email and QR code
written before the move still names it.

WHY A PLUGIN. `apps/openedx/settings/lms/production.py` and
`apps/caddy/Caddyfile` are regenerated from templates on every
`tutor config save`; an edit made by hand survives until the next deploy and
then disappears, which is the same failure `contrib/tutor-atheniq-theme`
exists to prevent. This makes the legacy names part of the configuration
instead of part of a container's writable layer.

WHAT IT DOES. For every host in `ATHENIQ_LEGACY_LMS_HOSTS`:

1. it is appended to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, because
   Django answers 400 to a host it was not told about and 403 to a form post
   from an origin it does not trust; and
2. it gets a caddy site block that proxies to the LMS, so the name reaches the
   same application the canonical one does.

The list is data, not code: drop a host from `config.yml` and `tutor config
save`, and that name stops answering. The canonical host is not listed — Tutor
already emits it.

INSTALL

    pip install -e contrib/tutor-atheniq-hosts
    tutor plugins enable atheniqhosts
    tutor config save
    tutor local restart caddy lms

Nothing is rebuilt: both patches are text in files the containers mount.
"""

from __future__ import annotations

from tutor import hooks

#: Hostnames the LMS still answers for after the rename. `learn.<domain>` is the
#: name the platform was built under; a deployment that never renamed it keeps an
#: empty list, and the plugin then does nothing at all.
hooks.Filters.CONFIG_DEFAULTS.add_item(
    ("ATHENIQ_LEGACY_LMS_HOSTS", ["learn.innotel.us"])
)

#: Hostnames the learner MFEs still answer on. They are served by the `mfe`
#: container, not the LMS, so they need their own blocks — an MFE reached on a
#: stale hostname still loads, and it reads its configuration from the LMS, so
#: it follows the rename without being rebuilt.
hooks.Filters.CONFIG_DEFAULTS.add_item(
    ("ATHENIQ_LEGACY_MFE_HOSTS", ["apps.learn.innotel.us"])
)

#: Django-side: the host is answerable and its forms are trusted. Appended rather
#: than assigned so Tutor's own `ALLOWED_HOSTS` (and anything another plugin adds)
#: stays exactly as configured.
hooks.Filters.ENV_PATCHES.add_item(
    (
        "openedx-lms-production-settings",
        """
{% for host in ATHENIQ_LEGACY_LMS_HOSTS %}
# AthenIQ: a hostname the platform answered on before the rename.
ALLOWED_HOSTS.append("{{ host }}")
CSRF_TRUSTED_ORIGINS.append("https://{{ host }}")
{% endfor %}
""",
    )
)

#: Edge-side: the same name reaches the LMS. The `caddyfile` patch point sits
#: after Tutor's own site blocks, so these are additional hosts, never overrides.
hooks.Filters.ENV_PATCHES.add_item(
    (
        "caddyfile",
        """
{% for host in ATHENIQ_LEGACY_LMS_HOSTS %}
# AthenIQ: legacy LMS hostname, kept in front of the same application.
{{ host }}{$default_site_port} {
    import proxy "lms:8000"
}
{% endfor %}
{% for host in ATHENIQ_LEGACY_MFE_HOSTS %}
# AthenIQ: legacy MFE hostname. The bundle is host-agnostic and reads its
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
