"""Cerulean (Authentik) OIDC single sign-on for Open edX (AthenIQ)."""
from tutor import hooks as _tutor_hooks

# Shared settings applied to BOTH the LMS (learn) and CMS (studio). These make
# the Open edX OIDC social-auth backend point at the Cerulean Authentik
# provider (client "atheniq-lms") and force HTTPS redirect_uri construction.
#
# NOTE on the client secret: it is intentionally NOT hardcoded here. Set it in
# the Tutor config (e.g. `tutor config save --set CERULEAN_OIDC_CLIENT_SECRET=...`)
# or in the plugin config defaults so the rendered settings receive it via
# {{ CERULEAN_OIDC_CLIENT_SECRET }}. The value must match the client secret of
# the "AthenIQ LMS" provider in Cerulean/Authentik.
_SSO_SETTINGS = """
# ── Cerulean SSO (Authentik OIDC, AthenIQ) ──────────────────────────
FEATURES["ENABLE_THIRD_PARTY_AUTH"] = True
AUTHENTICATION_BACKENDS = list(AUTHENTICATION_BACKENDS) + [
    "social_core.backends.open_id_connect.OpenIdConnectAuth",
]
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = "https://auth.cerulean.innotel.us/application/o/atheniq-lms"
# The Tutor Open edX plugin hardcodes SOCIAL_AUTH_REDIRECT_IS_HTTPS=False in the
# CMS (studio) settings template. With that off, the CMS builds the redirect_uri from
# the REQUEST scheme (HTTP, because the Caddy/NPM edge terminates TLS and proxies
# HTTP into the container), which does not match the registered
# https://studio.innotel.us/auth/complete/oidc/ URI on Cerulean ->
# "Mismatching redirect URI". Force HTTPS so both LMS and CMS redirect_uri match.
SOCIAL_AUTH_REDIRECT_IS_HTTPS = True
"""

# CMS (Studio) extra settings. Stock Open edX leaves the CMS without the
# third_party_auth machinery ("LMS only, not CMS") and Studio's own login uses
# the internal `edx-oauth2` backend, so several LMS-only pieces must be
# replicated here for Cerulean SSO to complete in Studio:
#   * SOCIAL_AUTH_PIPELINE  - Open edX TPA pipeline (profile-aware user create,
#     email association, logged-in cookies). Without it the CMS falls back to
#     social-auth's raw pipeline, which fails to create Open edX users.
#   * INSTALLED_APPS/MIDDLEWARE - third_party_auth must be installed for the
#     pipeline + its ExceptionMiddleware (turns social errors into redirects).
#   * TPA_PROVIDER_*_THROTTLE - only defined in lms/envs/common.py; the TPA API
#     views import them at class-definition time and crash without them.
#   * PROFILE_MICROFRONTEND_URL - read by user_authn.cookies in the
#     set_logged_in_cookies pipeline step.
# Deliberately NOT ConfigurationModelStrategy: Studio's own login goes through
# the internal 'edx-oauth2' backend, and that strategy requires an
# OAuth2ProviderConfig row for EVERY OAuth backend (none exists for
# edx-oauth2), so /login 500s. Settings-injected key/secret work fine here.
_CMS_SSO_SETTINGS = """
# ── Cerulean SSO: Studio/CMS additions (mirror the LMS TPA machinery) ────────
if 'common.djangoapps.third_party_auth' not in INSTALLED_APPS:
    INSTALLED_APPS = list(INSTALLED_APPS) + ['common.djangoapps.third_party_auth']
if 'common.djangoapps.third_party_auth.middleware.ExceptionMiddleware' not in MIDDLEWARE:
    MIDDLEWARE = list(MIDDLEWARE) + ['common.djangoapps.third_party_auth.middleware.ExceptionMiddleware']
TPA_PROVIDER_BURST_THROTTLE = '10/min'
TPA_PROVIDER_SUSTAINED_THROTTLE = '50/hr'
PROFILE_MICROFRONTEND_URL = 'https://apps.learn.innotel.us/profile/u/'
SOCIAL_AUTH_LOGIN_ERROR_URL = '/'
SOCIAL_AUTH_LOGIN_REDIRECT_URL = '/home'
SOCIAL_AUTH_SANITIZE_REDIRECTS = False
SOCIAL_AUTH_PROTECTED_USER_FIELDS = ['email']
SOCIAL_AUTH_RAISE_EXCEPTIONS = False
SOCIAL_AUTH_CLEAN_USERNAME_FUNCTION = 'common.djangoapps.third_party_auth.models.clean_username'
SOCIAL_AUTH_INACTIVE_USER_LOGIN = True
SOCIAL_AUTH_INACTIVE_USER_URL = '/auth/inactive'
SOCIAL_AUTH_UUID_LENGTH = 10
FIELDS_STORED_IN_SESSION = ['auth_entry', 'next']
SOCIAL_AUTH_PIPELINE = [
    'common.djangoapps.third_party_auth.pipeline.parse_query_params',
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'common.djangoapps.third_party_auth.pipeline.associate_by_email_if_login_api',
    'common.djangoapps.third_party_auth.pipeline.associate_by_email_if_saml',
    'common.djangoapps.third_party_auth.pipeline.associate_by_email_if_oauth',
    'common.djangoapps.third_party_auth.pipeline.get_username',
    'common.djangoapps.third_party_auth.pipeline.set_pipeline_timeout',
    'common.djangoapps.third_party_auth.pipeline.ensure_user_information',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    'common.djangoapps.third_party_auth.pipeline.user_details_force_sync',
    'common.djangoapps.third_party_auth.pipeline.set_id_verification_status',
    'common.djangoapps.third_party_auth.pipeline.set_logged_in_cookies',
    'common.djangoapps.third_party_auth.pipeline.login_analytics',
    'common.djangoapps.third_party_auth.pipeline.ensure_redirect_url_is_safe',
]
"""

for _patch_name in (
    "openedx-lms-production-settings",
    "openedx-cms-production-settings",
):
    _tutor_hooks.Filters.ENV_PATCHES.add_item((_patch_name, _SSO_SETTINGS))

_tutor_hooks.Filters.ENV_PATCHES.add_item(
    ("openedx-cms-production-settings", _CMS_SSO_SETTINGS)
)

# Declarative hooks surface expected by tutors plugin loader (v0).
hooks: dict = {}
