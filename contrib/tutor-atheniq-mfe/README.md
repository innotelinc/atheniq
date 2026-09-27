# tutor-atheniq-mfe

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
tutor images build mfe       # the footer is compiled — a config change is not enough
tutor local launch
```

Requires Tutor Indigo (the theme and the slot machinery). If a future Indigo
renames its footer widget id, add it to the `Hide` list in `plugin.py`.
