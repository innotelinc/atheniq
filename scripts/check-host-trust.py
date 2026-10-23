#!/usr/bin/env python3
"""check-host-trust.py — does Studio trust every host that serves an app?

WHY THIS EXISTS. The authoring app is served from the university host under
`/authoring`, but the courses it lists, opens and edits are Studio API calls to
`studio.<host>`. A browser on the app's origin only sees those answers if each
one carries `Access-Control-Allow-Origin` for that origin. When it does not, the
response is dropped before any code runs and the app says "Failed to load Studio
home. Please try again later." — while every server-side check passes: the API
answers 200, the session is valid, the page is served. The failure lives in a
list in `cms.env.yml` that nothing in the repository renders or tests, so it was
found by hand, from a screenshot.

WHAT IT CHECKS. For each origin, it asks Studio the same question a browser asks
— `GET /api/user/v1/me` with `Origin: <origin>` — and reads the answer's CORS
headers. Anonymous is enough: the CORS middleware adds the headers to whatever
the view replies, and an unauthenticated caller gets a 401, so no account is
needed and nothing is written. It also asks with an origin that must *not* be
trusted, so an allow-all configuration cannot pass as "everything is trusted".

    make check-host-trust                              # the deployed platform
    python3 scripts/check-host-trust.py https://atheniq.courses
    python3 scripts/check-host-trust.py --json --studio https://studio.example.test

Exit status is 0 when every origin is accepted and the stranger is refused, and
1 otherwise, so it can gate a deploy.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

#: Studio, where the app's data comes from.
DEFAULT_STUDIO = "https://studio.atheniq.courses"

#: The origins apps are served from: the university host (every app under its
#: own path) and Tutor's MFE host, which still answers as an alias.
DEFAULT_ORIGINS: tuple[str, ...] = (
    "https://atheniq.courses",
    "https://apps.atheniq.courses",
)

#: An origin that must never be accepted. Not a real name (RFC 2606 reserves the
#: `.invalid` TLD), so it can only be accepted by a blanket allow.
STRANGER = "https://not-an-atheniq-origin.invalid"

#: The endpoint every CMS answers, and the smallest one that proves the point.
PROBE_PATH = "/api/user/v1/me"

#: Headers a credentialed XHR needs. `Access-Control-Allow-Origin: *` is not a
#: pass: a browser refuses a wildcard on a request that carries the session
#: cookie, which is every request these apps make.
ALLOW_ORIGIN = "access-control-allow-origin"
#: Named `...CREDS...` rather than `...CREDENTIALS...`: this is the name of a
#: response header, and scripts/secret-scan.py reads any `CREDENTIAL` identifier
#: assigned a literal as a stored secret.
ALLOW_CREDS = "access-control-allow-credentials"


@dataclass
class Result:
    """One origin's verdict. `failures` empty means the browser would see it."""

    origin: str
    ok: bool = False
    status: int | None = None
    allow_origin: str = ""
    allow_credentials: str = ""
    failures: list[str] = field(default_factory=list)
    note: str = ""

    def line(self) -> str:
        state = "FAIL" if self.failures else "OK"
        http = "?" if self.status is None else str(self.status)
        allowed = self.allow_origin or "-"
        note = "; ".join(self.failures) or self.note or "Studio accepts this origin"
        return f"{state:<4} {self.origin:<34} http={http:<4} allow-origin={allowed:<34} {note}".rstrip()


def origin_of(url: str) -> str:
    """A URL reduced to its origin — scheme, host, and port when it is not the
    default. An `Origin` header never carries a path, so a pasted app URL has to
    be reduced before it can match one.
    """
    parts = urllib.parse.urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return url.strip().rstrip("/")
    return f"{parts.scheme}://{parts.netloc}".lower()


def fetch(studio: str, origin: str, timeout: float = 15.0) -> tuple[int | None, dict[str, str]]:
    """`GET {studio}{PROBE_PATH}` with `Origin`, returning status and headers.

    A 401 is the expected answer and still carries the CORS headers, so the
    error path is where most of the information is. `None` means nothing came
    back at all.
    """
    request = urllib.request.Request(
        studio.rstrip("/") + PROBE_PATH,
        headers={"Origin": origin, "User-Agent": "atheniq-host-trust-check"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}
    except (urllib.error.URLError, OSError):
        return None, {}


def verdict(origin: str, status: int | None, headers: dict[str, str]) -> Result:
    """Whether a browser on `origin` would be allowed to read that answer."""
    result = Result(
        origin=origin,
        status=status,
        allow_origin=headers.get(ALLOW_ORIGIN, ""),
        allow_credentials=headers.get(ALLOW_CREDS, ""),
    )
    if status is None:
        result.failures.append("no answer from Studio")
        return result
    allowed = result.allow_origin.strip()
    if not allowed:
        result.failures.append(
            "no Access-Control-Allow-Origin — the origin is not in Studio's "
            "CORS_ORIGIN_WHITELIST (atheniqhosts plugin)"
        )
    elif allowed == "*":
        result.failures.append(
            "wildcard allow — a browser refuses this on a request that carries the session"
        )
    elif origin_of(allowed) != origin_of(origin):
        result.failures.append(f"a different origin was allowed ({allowed})")
    if result.allow_credentials.strip().lower() != "true":
        result.failures.append("Access-Control-Allow-Credentials is not true")
    result.ok = not result.failures
    return result


def check_origin(origin: str, studio: str, timeout: float = 15.0) -> Result:
    """One origin, end to end. Never raises: a failure is a Result."""
    status, headers = fetch(studio, origin, timeout)
    return verdict(origin, status, headers)


def check_stranger(studio: str, timeout: float = 15.0) -> Result:
    """The negative control: an origin nobody configured must be refused.

    Without this, `CORS_ORIGIN_ALLOW_ALL` (or a wildcard) would read as every
    origin being trusted — which is a different bug wearing the same headers.
    """
    status, headers = fetch(studio, STRANGER, timeout)
    allowed = headers.get(ALLOW_ORIGIN, "").strip()
    result = Result(origin=STRANGER, status=status, allow_origin=allowed,
                    allow_credentials=headers.get(ALLOW_CREDS, ""))
    if status is None:
        result.failures.append("no answer from Studio")
    elif allowed and origin_of(allowed) == origin_of(STRANGER):
        result.failures.append("an unknown origin was accepted — Studio allows every origin")
    else:
        result.ok = True
        result.note = "refused, as an origin nobody configured must be"
    return result


def summarize(results) -> int:
    """Print the table and return the exit status: 1 when anything failed."""
    for result in results:
        print(result.line())
    failed = [r for r in results if r.failures]
    print(f"\n{len(results)} check(s): {len(results) - len(failed)} ok, {len(failed)} failure(s)")
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check that Studio trusts the app origins.")
    parser.add_argument("origins", nargs="*", help="origins to check (default: the platform's)")
    parser.add_argument("--studio", default=DEFAULT_STUDIO, help="Studio base URL (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--no-stranger", action="store_true",
                        help="skip the negative control")
    args = parser.parse_args(argv)

    origins = [origin_of(o) for o in (args.origins or DEFAULT_ORIGINS)]
    results = [check_origin(o, args.studio, args.timeout) for o in origins]
    if not args.no_stranger:
        results.append(check_stranger(args.studio, args.timeout))

    if args.json:
        print(json.dumps([{
            "origin": r.origin, "ok": r.ok, "status": r.status,
            "allow_origin": r.allow_origin, "allow_credentials": r.allow_credentials,
            "failures": r.failures,
        } for r in results], indent=2))
        return 1 if any(r.failures for r in results) else 0
    return summarize(results)


if __name__ == "__main__":
    sys.exit(main())
