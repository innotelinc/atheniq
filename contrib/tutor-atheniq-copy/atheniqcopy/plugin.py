"""AthenIQ — white-label copy overrides for the legacy MFEs.

WHY A DOCKERFILE PATCH AND NOT A SETTING. The signup page is the legacy authn
MFE, served straight from `/openedx/dist/authn` inside the
`overhangio/openedx-mfe` image (see the `@mfe_authn` route in
`env/plugins/mfe/apps/mfe/Caddyfile`). Nothing in the LMS, the Indigo theme or
the frontend-plugin-framework reaches its text: the heading above the
third-party auth buttons is the i18n message `registration.other.options.heading`,
defined as `defaultMessage: 'Or register with:'` in
`src/common-components/messages.jsx` and rendered by
`src/common-components/ThirdPartyAuth.jsx`. Both live in the MFE's own source.

Tutor renders that MFE's Dockerfile from a template carrying a per-MFE hook
immediately after the webpack build, `mfe-dockerfile-post-npm-build-<mfe_name>`.
Patching that hook — rather than editing `env/plugins/mfe/build/mfe/Dockerfile`,
which `tutor config save` regenerates from the template and would discard — is
what makes the change survive both a re-render and a rebuilt image.

TWO PATCHES, DELIBERATELY. The `pre-npm-build` one corrects the message at its
source so the app's own default is right. The `post-npm-build` one rewrites the
built bundle and then *asserts* the result, because an `en` translation pulled
by `pull_translations` would otherwise win over the source default at runtime,
and a silent mismatch is the failure this plugin exists to prevent: the build
fails loudly rather than shipping the old wording.

REQUIRES A REBUILT IMAGE. This changes what the next build produces, not what is
already running:

    tutor plugins enable atheniqcopy
    tutor config save
    tutor images build mfe
    tutor local start -d --force-recreate

`tutor images build mfe` compiles every enabled MFE. To confirm the change
landed without re-running the whole site, check the built bundle directly:

    docker run --rm <mfe-image> grep -rl 'Or enroll with AthenIQ:' /openedx/dist/authn
"""

from tutor import hooks as _tutor_hooks

#: What the heading above the third-party auth buttons should say.
_SIGNUP_HEADING_FROM = "Or register with:"
_SIGNUP_HEADING_TO = "Or enroll with AthenIQ:"

#: The source that defines the message, relative to the authn app root.
_AUTHN_MESSAGES = "/openedx/app/src/common-components/messages.jsx"

_tutor_hooks.Filters.ENV_PATCHES.add_items(
    [
        (
            # Fix the app's own default before webpack sees it.
            "mfe-dockerfile-pre-npm-build-authn",
            f"""RUN sed -i "s/{_SIGNUP_HEADING_FROM}/{_SIGNUP_HEADING_TO}/" {_AUTHN_MESSAGES} \\
    && grep -q "{_SIGNUP_HEADING_TO}" {_AUTHN_MESSAGES}
""",
        ),
        (
            # Rewrite the built bundle too, then prove the old wording is gone.
            # An `en` translation from Atlas would otherwise override the source
            # default at runtime, so the assertion is the point of this patch.
            "mfe-dockerfile-post-npm-build-authn",
            f"""RUN find /openedx/app/dist -name '*.js' -exec sed -i "s/{_SIGNUP_HEADING_FROM}/{_SIGNUP_HEADING_TO}/g" {{}} + \\
    && grep -rq "{_SIGNUP_HEADING_TO}" /openedx/app/dist \\
    && ! grep -rq "{_SIGNUP_HEADING_FROM}" /openedx/app/dist
""",
        ),
    ]
)
