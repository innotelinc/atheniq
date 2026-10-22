#!/usr/bin/env python3
"""patch-mfe-trailing-slash.py — redirect an MFE path without its slash to the slash.

Every learner MFE is mounted with a router basename of its own path
(`/learner-dashboard`, `/learning`, `/profile`, ...). A request for
`/learner-dashboard` therefore normalises to an empty route inside the app: the
shell loads, `initialize()` completes, and the router matches nothing, so the
page stays blank with no error anywhere. `/learner-dashboard/` renders.

Nothing upstream redirects the slash in, so the fix belongs in the MFE's own
Caddy site block: one rule that sends every bare app path to the slashed one.
It is applied in two places, because they have different lifetimes:

  * the tutor-mfe **template** (`tutormfe/templates/mfe/apps/mfe/Caddyfile`),
    so a later `tutor config save` renders the rule instead of dropping it; and
  * the **rendered** env file the running container mounts
    (`$TUTOR_ROOT/env/plugins/mfe/apps/mfe/Caddyfile`), so the fix is live
    after a `caddy reload` without a full `tutor local launch`.

Idempotent: a second run finds the rule and changes nothing.

Usage:
    python3 scripts/patch-mfe-trailing-slash.py            # apply
    python3 scripts/patch-mfe-trailing-slash.py --check     # report only
"""

from __future__ import annotations

import argparse
import glob
import pathlib
import sys

#: The apps the image serves. Kept as one expression so the redirect and the
#: blocks it shadows cannot drift.
APPS = (
    "account",
    "admin-console",
    "authn",
    "authoring",
    "catalog",
    "communications",
    "discussions",
    "gradebook",
    "learner-dashboard",
    "learning",
    "ora-grading",
    "profile",
    "site",
)

MARKER = "@mfe_no_trailing_slash"

RULE = f"""\
    # An MFE path without its trailing slash is not the app's own URL: the
    # router's basename strips the prefix and the path left over is "", which
    # matches no route - the shell loads and stays blank. Send the bare path to
    # the slashed one so the page the user asked for is the page that renders.
    {MARKER} path_regexp mfe_noslash ^/({'|'.join(APPS)})$
    redir {MARKER} /{{re.mfe_noslash.1}}/ 308

"""

#: Where the rule goes: before the runtime-config block, which every rendering
#: of this template carries.
ANCHOR = "    @runtime_config {"


def targets() -> list[pathlib.Path]:
    """Every Caddyfile this box serves the MFEs from, template first."""
    found: list[pathlib.Path] = []
    for pattern in (
        "/home/tutor/tutor-venv/lib/python*/site-packages/tutormfe/templates/mfe/apps/mfe/Caddyfile",
        "/home/tutor/.local/share/tutor/env/plugins/mfe/apps/mfe/Caddyfile",
        "/root/.local/share/tutor/env/plugins/mfe/apps/mfe/Caddyfile",
    ):
        found.extend(pathlib.Path(p) for p in sorted(glob.glob(pattern)))
    return [p for p in found if p.is_file()]


def apply(path: pathlib.Path, check: bool) -> str:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return "already patched"
    if ANCHOR not in text:
        return "anchor missing — left alone"
    if check:
        return "needs patch"
    path.write_text(text.replace(ANCHOR, RULE + ANCHOR, 1), encoding="utf-8")
    return "patched"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()

    files = targets()
    if not files:
        print("no tutor-mfe Caddyfile found (is tutor-mfe installed here?)")
        return 1
    pending = 0
    for path in files:
        result = apply(path, args.check)
        if result == "needs patch":
            pending += 1
        print(f"{result:<35} {path}")
    if args.check and pending:
        print(f"\n{pending} file(s) would be patched; run without --check.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
