# tutor-atheniq-copy

AthenIQ white-label copy overrides for the legacy MFEs.

Currently one override: the heading above the third-party auth buttons on the
**signup page** reads *"Or register with:"* upstream and *"Or enroll with
AthenIQ:"* here.

## Why it has to be a Dockerfile patch

The signup page is the legacy **authn MFE**, served straight from
`/openedx/dist/authn` inside the `overhangio/openedx-mfe` image. The text is the
i18n message `registration.other.options.heading`, defined as
`defaultMessage: 'Or register with:'` in `src/common-components/messages.jsx`
and rendered by `src/common-components/ThirdPartyAuth.jsx`. No LMS setting, theme
template or frontend-plugin slot reaches it.

Tutor renders that MFE's Dockerfile from a template with a per-MFE hook after the
webpack build, `mfe-dockerfile-post-npm-build-<mfe_name>`. This plugin patches two
of those hooks:

| Patch key | What it does |
| --- | --- |
| `mfe-dockerfile-pre-npm-build-authn` | corrects the message at its source |
| `mfe-dockerfile-post-npm-build-authn` | rewrites the built bundle, then **asserts** the old wording is gone |

Patching the template hooks — rather than editing
`env/plugins/mfe/build/mfe/Dockerfile` — is what makes the change survive
`tutor config save`, which re-renders that file from the template and would
otherwise silently discard a hand edit.

The post-build assertion matters: an `en` translation pulled by
`pull_translations` overrides the source default at runtime, so the build fails
loudly rather than shipping the old wording.

## Install

```bash
cd /home/tutor/atheniq/contrib/tutor-atheniq-copy
/home/tutor/tutor-venv/bin/pip install -e .
/home/tutor/tutor-venv/bin/tutor plugins enable atheniqcopy
/home/tutor/tutor-venv/bin/tutor config save
/home/tutor/tutor-venv/bin/tutor images build mfe
/home/tutor/tutor-venv/bin/tutor local start -d --force-recreate
```

## Verify

`tutor config save` only changes what the *next* build produces. To confirm the
rendered Dockerfile carries the hook before you spend an hour on the build:

```bash
grep -n "Or enroll with AthenIQ" \
  /home/tutor/.local/share/tutor/env/plugins/mfe/build/mfe/Dockerfile
```

After the build, check the bundle itself:

```bash
docker run --rm overhangio/openedx-mfe:22.0.0-indigo \
  grep -rl 'Or enroll with AthenIQ:' /openedx/dist/authn
```

## Adding another override

Add a `(patch_key, dockerfile_snippet)` pair to `ENV_PATCHES` in
`atheniqcopy/plugin.py`. Use the `<mfe_name>` suffix to target one MFE
(`-authn`, `-account`, `-learning`, …) or omit it to hit every MFE. Watch the
sibling keys on `messages.jsx` — *"Register with institution/campus
credentials"* (`institution.login.button`) also contains "register with" and is
deliberately left alone.
