#!/usr/bin/env python3
"""Drop an **expired** JWT cookie in the MFE shell, before the app reads it.

WHY THIS EXISTS
---------------
A learner whose `edx-jwt-cookie-header-payload` has expired does not get signed
out — they get an error page:

    An unexpected error occurred. Please click the button below to refresh the page.
    Axios Error (Response): 405 - See custom attributes for details.

and the "Try again" button does not clear it. Measured on `atheniq.courses`,
2026-10-29, on `/catalog/` and `/dashboard` alike:

1. the shell loads and the app asks the LMS for its config,
   `GET /api/mfe_config/v1?mfe=…`, with the expired token attached;
2. the LMS answers **401** for that invalid credential — even though the config
   endpoint is public — because DRF's authentication rejects the request before
   the view's permissions are consulted;
3. with no config the app's own token refresh has no URL to call, so it posts to
   the empty path — `POST /catalog/` — and gets **405** from the static file
   server;
4. the app renders its error boundary, and "Try again" repeats steps 1–3, so the
   page stays broken until the cookie is removed by hand.

The estate cannot stop (2) without rebuilding the LMS image, but (1) is entirely
in our hands: an expired cookie carries no authority, so removing it before the
app boots makes the config call anonymous, the app initialise, and its own
`login_refresh` install a fresh token. A learner with a lapsed session then sees
the signed-out page instead of an error.

WHAT IT DOES
------------
Inserts one inline `<script>` immediately before `</head>` of an MFE's
`index.html`. It removes `edx-jwt-cookie-header-payload` and
`edx-jwt-cookie-signature` **only** when the payload is missing, unparsable,
expired, or has no signature cookie beside it; a valid token is left untouched.
App bundles are `defer`red, so a classic inline script in `<head>` runs first.

Idempotent: the marker line is checked, so re-running over a patched tree is a
no-op. `--check` reports without writing (exit 1 when something is unpatched).

Usage:
    scripts/patch-mfe-stale-jwt.py /openedx/dist/*/index.html
    scripts/patch-mfe-stale-jwt.py --check /openedx/dist/*/index.html

The same step belongs in `deploy-mfe-brand.sh` — a rebuilt MFE image loses this
patch exactly as it loses the brand patch.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARKER = "<!-- atheniq:stale-jwt v1 -->"

#: The cookie the app boots from and the one that must sit beside it. Dropping
#: only the payload would leave a signature with nothing to verify.
PAYLOAD_COOKIE = "edx-jwt-cookie-header-payload"
SIGNATURE_COOKIE = "edx-jwt-cookie-signature"

SCRIPT = """<script>(function () {
  try {
    var name = "edx-jwt-cookie-header-payload";
    var match = document.cookie.match(new RegExp("(?:^|;\\\\s*)" + name + "=([^;]*)"));
    if (!match) return;
    var signed = document.cookie.indexOf("edx-jwt-cookie-signature=") !== -1;
    var payload = match[1].split(".")[1];
    if (!payload || !signed) throw new Error("incomplete token");
    payload = payload.replace(/-/g, "+").replace(/_/g, "/");
    while (payload.length % 4) payload += "=";
    var claims = JSON.parse(atob(payload));
    if (claims && typeof claims.exp === "number" && claims.exp * 1000 > Date.now()) return;
    if (claims && typeof claims.exp !== "number") return;
  } catch (error) {
    /* unparsable is the same as expired here: it cannot authenticate anything */
  }
  var gone = "; Max-Age=0; path=/";
  var names = ["edx-jwt-cookie-header-payload", "edx-jwt-cookie-signature"];
  for (var i = 0; i < names.length; i += 1) document.cookie = names[i] + "=" + gone;
  var host = location.hostname.split(".");
  for (var j = 0; j < host.length - 1; j += 1) {
    var domain = "; domain=." + host.slice(j).join(".");
    for (var k = 0; k < names.length; k += 1) document.cookie = names[k] + "=" + gone + domain;
  }
})();</script>"""


def patch_html(text: str) -> tuple[str, bool]:
    """`(html, changed)` — the shell with the guard first inside its `<head>`.

    It goes immediately after `<head>` (or `<head …>`) rather than before
    `</head>`: the bundles are declared in the head, and while their `defer`
    means a classic inline script would still win, being **first** is the
    property that does not depend on how a later build orders the tags.

    A file with no `<head>` is left alone: guessing where it starts is how a page
    ends up booting in the wrong order.
    """
    if MARKER in text:
        return text, False
    lowered = text.lower()
    opened = lowered.find("<head")
    if opened == -1:
        return text, False
    close = lowered.find(">", opened)
    if close == -1:
        return text, False
    insertion = f"\n{MARKER}\n{SCRIPT}"
    return text[: close + 1] + insertion + text[close + 1 :], True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", help="index.html files to patch")
    parser.add_argument("--check", action="store_true", help="report unpatched files instead of writing")
    args = parser.parse_args(argv)

    unpatched = 0
    for name in args.paths:
        path = Path(name)
        if not path.is_file():
            print(f"patch-mfe-stale-jwt: {path} is not a file", file=sys.stderr)
            return 2
        text = path.read_text(encoding="utf-8")
        patched, changed = patch_html(text)
        if not changed and MARKER not in text:
            print(f"patch-mfe-stale-jwt: {path} has no </head> — left alone", file=sys.stderr)
            unpatched += 1
            continue
        if args.check:
            if changed:
                print(f"UNPATCHED {path}")
                unpatched += 1
            continue
        if changed:
            path.write_text(patched, encoding="utf-8")
            print(f"patched {path}")
        else:
            print(f"already patched {path}")

    if args.check and unpatched:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
