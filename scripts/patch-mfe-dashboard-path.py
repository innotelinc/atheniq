#!/usr/bin/env python3
"""patch-mfe-dashboard-path.py — serve the learner dashboard at `/dashboard`.

The learner dashboard is the one app whose name in the platform and whose path in
the `mfe` container disagree. The platform links to `/dashboard`
(`student_dashboard`, the account page, every emailed course link); the app was
built for `/learner-dashboard`, and its public path — the router's basename and
the URL its chunks are fetched from — is `/learner-dashboard/` in the bundle.

`patch-mfe-brand.py` moves that public path to `/dashboard/`. This script moves
the two edges to match, so the address the platform links to is the address the
app renders at:

  * **the `mfe` container** (`:8002`) serves the dashboard out of
    `/openedx/dist/learner-dashboard` — the directory keeps the name the app was
    built as — under `/dashboard`, and sends the old path to it. Applied to the
    tutor-mfe **template** (so a later `tutor config save` renders it) and to the
    **rendered** env file the running container mounts. It goes in ahead of
    tutor-mfe's per-app loop, which still emits a `/learner-dashboard` block:
    Caddy matches `handle`s in the order written, so the redirect here wins over
    the block the loop writes below it.

  * **the LMS site block** proxies `/dashboard*` to the `mfe` container — a
    `handle` for the app path, the same shape the other learner apps get — and
    sends `/learner-dashboard*` to it. `atheniqhosts/plugin.py` renders the same
    two rules; this script is what applies them to the file the running `caddy`
    container mounts, without a `tutor local launch`.

The trailing-slash rule is re-pointed in the same pass: a bare `/dashboard` is
the app's path with its basename stripped and nothing left over, which matches no
route and renders blank, so the bare path has to arrive with its slash.

Idempotent: a second run finds the rules and changes nothing.

Usage:
    python3 scripts/patch-mfe-dashboard-path.py            # apply
    python3 scripts/patch-mfe-dashboard-path.py --check     # report only
"""

from __future__ import annotations

import argparse
import glob
import pathlib

#: The app the dashboard's files are built as, and the path it is served at.
DIST_APP = "learner-dashboard"
SERVED_AT = "dashboard"

#: What the injected block is identified by, in either file.
MARKER = "@atheniq_dashboard"

#: The block for the `mfe` container, indented for its site block. It sits before
#: tutor-mfe's per-app loop, whose `/learner-dashboard` handle would otherwise
#: serve a shell whose router basename no longer matches the address.
MFE_BLOCK = f"""\
    # AthenIQ: the dashboard is served at /{SERVED_AT}. Its dist is still named
    # for the app it was built as, and the app's own public path is moved to this
    # address by patch-mfe-brand.py — the two have to agree, or the shell loads
    # and every route in it matches nothing.
    {MARKER} path /{SERVED_AT} /{SERVED_AT}/*
    handle {MARKER} {{
        uri strip_prefix /{SERVED_AT}
        root * /openedx/dist/{DIST_APP}
        try_files /{{path}} /index.html
        file_server
    }}
    # A link from before the move still opens the page it named.
    @atheniq_old_dashboard path_regexp ^/{DIST_APP}(/.*)?$
    redir @atheniq_old_dashboard /{SERVED_AT}{{re.atheniq_old_dashboard.1}} 302

"""

#: The trailing-slash rule's app list, as one path is swapped for the other.
TRAILING_OLD = f"|{DIST_APP}|"
TRAILING_NEW = f"|{SERVED_AT}|"

#: Every rendering of the `mfe` site block carries the trailing-slash rule right
#: after the patch point, so its comment is the anchor the block goes above.
MFE_ANCHOR = "    # An MFE path without its trailing slash"

#: The LMS site block's two rules, as the plugin used to write them and as they
#: have to read now.
LMS_PROXY_OLD = f"    handle /{DIST_APP}* {{\n        reverse_proxy mfe:8002\n    }}"
LMS_PROXY_NEW = f"    handle /{SERVED_AT}* {{\n        reverse_proxy mfe:8002\n    }}"
LMS_REDIR_OLD = (
    "    # AthenIQ: /dashboard is the URL the platform links to; the app is served\n"
    f"    # at /{DIST_APP} in the mfe container.\n"
    "    @atheniq_dashboard path_regexp ^/dashboard(/.*)?$\n"
    f"    redir @atheniq_dashboard /{DIST_APP}{{re.atheniq_dashboard.1}} 302"
)
LMS_REDIR_NEW = (
    "    # AthenIQ: the dashboard is served at /dashboard. The app was built for\n"
    f"    # /{DIST_APP}; a link from before the move goes there.\n"
    f"    @atheniq_old_dashboard path_regexp ^/{DIST_APP}(/.*)?$\n"
    f"    redir @atheniq_old_dashboard /{SERVED_AT}{{re.atheniq_old_dashboard.1}} 302"
)


def mfe_targets() -> list[pathlib.Path]:
    """Every `mfe` Caddyfile this box serves the dashboard from, template first."""
    found: list[pathlib.Path] = []
    for pattern in (
        "/home/tutor/tutor-venv/lib/python*/site-packages/tutormfe/templates/mfe/apps/mfe/Caddyfile",
        "/home/tutor/.local/share/tutor/env/plugins/mfe/apps/mfe/Caddyfile",
        "/root/.local/share/tutor/env/plugins/mfe/apps/mfe/Caddyfile",
    ):
        found.extend(pathlib.Path(p) for p in sorted(glob.glob(pattern)))
    return [p for p in found if p.is_file()]


def lms_targets() -> list[pathlib.Path]:
    """The LMS site block's Caddyfile, as the `caddy` container mounts it."""
    found: list[pathlib.Path] = []
    for pattern in (
        "/home/tutor/.local/share/tutor/env/apps/caddy/Caddyfile",
        "/root/.local/share/tutor/env/apps/caddy/Caddyfile",
    ):
        found.extend(pathlib.Path(p) for p in sorted(glob.glob(pattern)))
    return [p for p in found if p.is_file()]


def patch_mfe(text: str) -> tuple[str, str]:
    """The `mfe` site block: serve at the new path, redirect the old one."""
    if MARKER in text:
        return text, "already patched"
    if MFE_ANCHOR not in text:
        return text, "anchor missing — left alone"
    text = text.replace(MFE_ANCHOR, MFE_BLOCK + MFE_ANCHOR, 1)
    if TRAILING_OLD in text:
        text = text.replace(TRAILING_OLD, TRAILING_NEW, 1)
    return text, "patched"


def patch_lms(text: str) -> tuple[str, str]:
    """The LMS site block: proxy the new path, redirect the old one."""
    if "@atheniq_old_dashboard" in text and LMS_PROXY_NEW in text:
        return text, "already patched"
    if LMS_PROXY_OLD not in text or LMS_REDIR_OLD not in text:
        return text, "anchor missing — left alone"
    text = text.replace(LMS_PROXY_OLD, LMS_PROXY_NEW, 1)
    text = text.replace(LMS_REDIR_OLD, LMS_REDIR_NEW, 1)
    return text, "patched"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()

    # Two families, each of which has to move: the `mfe` container's site block
    # and the LMS's. A box can hold more than one rendered env — the deployment's
    # and an older one under another TUTOR_ROOT — and only the live tree carries
    # the text this patch knows; an untouched stale copy is not a failure, a
    # family where nothing matched is.
    families = (("mfe", mfe_targets(), patch_mfe), ("lms", lms_targets(), patch_lms))
    pending = 0
    moved: dict[str, int] = {}
    for name, targets, patch in families:
        for path in targets:
            new, result = patch(path.read_text(encoding="utf-8"))
            if result == "patched" and args.check:
                pending += 1
                result = "needs patch"
            elif result == "patched":
                path.write_text(new, encoding="utf-8")
            if result != "anchor missing — left alone":
                moved[name] = moved.get(name, 0) + 1
            print(f"{name:<4} {result:<34} {path}")

    if not any(targets for _name, targets, _patch in families):
        print("no tutor Caddyfile found (is tutor installed here?)")
        return 1
    missing = [name for name, targets, _ in families if targets and not moved.get(name)]
    if missing:
        # The block did not match, so it did not land: `/dashboard` would either
        # 404 or serve the app at a path its router no longer matches. Saying so
        # is the difference between a broken dashboard and a refused deploy.
        print(f"\n{', '.join(missing)} Caddyfile did not match — the routing was NOT moved.")
        return 1
    if args.check and pending:
        print(f"\n{pending} file(s) would be patched; run without --check.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
