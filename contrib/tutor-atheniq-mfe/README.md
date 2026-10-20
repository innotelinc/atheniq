# tutor-atheniq-mfe

A Tutor plugin for the learner MFEs:

1. a white-labelled **footer** (below), and
2. an **AI Classroom link** in the header nav that opens `ai.lms.innotel.us`,
3. a **browserslist refresh** so builds stop compiling against a stale
   `caniuse-lite` snapshot.

The header link is one widget appended to the desktop and mobile main-menu
slots, registered for the `all` wildcard only: tutor-mfe renders `all`
*unguarded* in the `env.config.jsx` every legacy MFE builds with, so naming the
MFEs as well would insert the same link twice (it did, until that was measured
in a browser).

The refresh is a Dockerfile patch at the `mfe-dockerfile-pre-npm-build` and
`mfe-dockerfile-pre-npm-build-site` hooks: it fetches the current `caniuse-lite`
tarball and unpacks it over the working directory's `node_modules`. Not
`npm install caniuse-lite@latest` — that re-resolves the whole peer graph and
fails with `ERESOLVE` on these apps, and it would rewrite the
package.json/lockfile upstream pinned.

Both hooks matter, and the target has to be `$(pwd)`: the per-app stages build
in `/openedx/app` while the *site* stage — the one that compiles the bundles the
header link lives in — builds in `/openedx/site`. A hard-coded `/openedx/app`
there creates an orphan `node_modules` and leaves the real one stale, so webpack
still warns:

```
Browserslist: browserslist data updates from caniuse-lite … Please run:
  npx update-browserslist-db@latest
```

Verified in a `node:24.14.1-bullseye-slim` container laid out like the site
stage: the warning prints before the unpack and is gone after it.

## The footer

A Tutor plugin that white-labels the **learner-MFE footer** as AthenIQ.

The Tutor Indigo theme installs its own footer into the frontend-plugin-framework
footer slot (`org.openedx.frontend.layout.footer.v1`). That footer is compiled
into the MFE bundles and still renders "Powered by" with the Tutor and Open edX
logos, linking to `open.edx.org` — no LMS theme template can reach it.

This plugin hides those widgets at the same slot and inserts an AthenIQ footer,
using the same mechanism Indigo uses to install its own (an env-config runtime
component definition plus a `PLUGIN_SLOTS` entry). It is inert when `tutor-mfe`
is not installed.

The LMS footer itself is replaced without a rebuild by
[`contrib/atheniq-theme`](../atheniq-theme); this plugin is only for the MFEs.

## Install

```bash
tutor plugins enable atheniqmfe
tutor config save
tutor images build mfe       # the footer and the header link are compiled in
```

**Build one app, not all thirteen.** `tutor images build mfe` compiles every MFE
in one buildx run, in parallel; on a small host that has taken a production
node down. The safe shape is a per-app target plus a wrapper image:

```bash
cd ~/.local/share/tutor/env/plugins/mfe/build/mfe
docker build --build-arg NODE_IMAGE=atheniq/node-bullseye-slim:24.14.1 \
  --target catalog-prod -t atheniq/mfe-catalog:new .
docker tag overhangio/openedx-mfe:${MFE_VERSION}-indigo overhangio/openedx-mfe:${MFE_VERSION}-indigo.pre
printf 'FROM overhangio/openedx-mfe:%s-indigo.pre\nRUN rm -rf /openedx/dist/catalog\nCOPY --from=atheniq/mfe-catalog:new /openedx/app/dist /openedx/dist/catalog\n' "$MFE_VERSION" \
  | docker build -f - -t overhangio/openedx-mfe:${MFE_VERSION}-indigo .
tutor local start -d mfe
```

The apps most learners see are `catalog`, `learning` and `learner-dashboard`;
each target (`<app>-prod`) is one webpack build. Keep the `.pre` tag — it is the
rollback.

Requires Tutor Indigo (the theme and the slot machinery). If a future Indigo
renames its footer widget id, add it to the `Hide` list in `plugin.py`.
