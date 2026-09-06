"""Cerulean (Authentik) OIDC single sign-on for Open edX (AuthenIQ)."""
from tutor import hooks as _tutor_hooks

_SSO_SETTINGS = """
# ── Cerulean SSO (Authentik OIDC, AuthenIQ) ──────────────────────────
FEATURES["ENABLE_THIRD_PARTY_AUTH"] = True
AUTHENTICATION_BACKENDS = list(AUTHENTICATION_BACKENDS) + [
    "social_core.backends.open_id_connect.OpenIdConnectAuth",
]
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = "https://auth.cerulean.innotel.us/application/o/authentiq-lms"
"""

for _patch_name in (
    "openedx-lms-production-settings",
    "openedx-cms-production-settings",
):
    _tutor_hooks.Filters.ENV_PATCHES.add_item((_patch_name, _SSO_SETTINGS))

# Declarative hooks surface expected by tutors plugin loader (v0).
hooks: dict = {}
