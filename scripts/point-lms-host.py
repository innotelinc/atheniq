#!/usr/bin/env python3
"""Point `lms.innotel.us` at the learner portal.

The LMS hostname has only ever answered with a redirect to
`apps.learn.innotel.us/catalog/`. The learner portal (`student-portal.py`, port
8092) is the page that should answer there now: programs and courses, in Unity,
before sign-in.

This tool changes the edge, not the application. It talks to Nginx Proxy
Manager's API, finds the host whose domain is `lms.innotel.us`, and either
reports what it would change (`--check`, the default) or changes it (`--apply`).
Before an apply it prints the host's current settings as JSON, so the change is
reversible from the output alone.

The upstream keeps the scheme and certificate the host already uses; only the
forward address moves. If the host is a *redirection* host (a 301 to the
catalog), it is replaced by a proxy host with the same domains and certificate,
because a redirect cannot forward to a page.

Configuration (environment):

    NPM_API_URL        http://127.0.0.1:81 (the NPM admin API)
    NPM_ADMIN_EMAIL    an NPM account that may edit hosts
    NPM_ADMIN_PASSWORD its password
    NPM_VERIFY_TLS     "1" to verify the API's certificate (default: off on LAN)

Usage:

    python3 scripts/point-lms-host.py --check
    python3 scripts/point-lms-host.py --apply
    python3 scripts/point-lms-host.py --apply --upstream 192.168.1.60 --port 8092
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

DOMAIN = "lms.innotel.us"
FORWARD_HOST = "192.168.1.59"
FORWARD_PORT = 8092


class NpmError(RuntimeError):
    """The edge refused or could not be reached."""


def _context() -> ssl.SSLContext:
    verify = os.environ.get("NPM_VERIFY_TLS", "") in ("1", "true", "yes")
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def call(url: str, method: str = "GET", body=None, headers=None, timeout: int = 30):
    data = None
    req_headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        req_headers["Content-Type"] = "application/json"
    req_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_context()) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", "replace")[:300]
        raise NpmError(f"{method} {url} -> {err.code}: {payload}") from err
    except urllib.error.URLError as err:
        raise NpmError(f"cannot reach NPM at {url}: {err.reason}") from err


class Npm:
    def __init__(self, base: str, email: str, password: str):
        self.base = base.rstrip("/")
        status, payload = call(f"{self.base}/api/tokens", "POST",
                               {"identity": email, "secret": password})
        token = (payload or {}).get("token")
        if status not in (200, 201) or not token:
            raise NpmError("NPM refused the credentials")
        self.headers = {"Authorization": f"Bearer {token}"}

    def hosts(self, kind: str):
        return call(f"{self.base}/api/nginx/{kind}", headers=self.headers)[1] or []

    def delete(self, kind: str, host_id: int):
        return call(f"{self.base}/api/nginx/{kind}/{host_id}", "DELETE",
                    headers=self.headers)

    def create(self, kind: str, body: dict):
        return call(f"{self.base}/api/nginx/{kind}", "POST", body,
                    headers=self.headers)

    def update(self, kind: str, host_id: int, body: dict):
        return call(f"{self.base}/api/nginx/{kind}/{host_id}", "PUT", body,
                    headers=self.headers)


def _domains(host: dict) -> list[str]:
    value = host.get("domain_names") or []
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    return [str(domain).strip().lower() for domain in value]


def find(npm: Npm) -> tuple[str, dict] | tuple[None, None]:
    for kind in ("proxy-hosts", "redirection-hosts"):
        for host in npm.hosts(kind):
            if DOMAIN in _domains(host):
                return kind, host
    return None, None


#: The keys NPM's update endpoint refuses. It validates the body strictly, so a
#: host read from the API cannot simply be written back: `id`, the timestamps and
#: the owner are managed by NPM, and a PUT carrying them answers
#: `400 data must NOT have additional properties`.
READ_ONLY_KEYS = ("id", "created_on", "modified_on", "owner_user_id")


def writable(host: dict) -> dict:
    return {key: value for key, value in host.items() if key not in READ_ONLY_KEYS}


def proxy_body(existing: dict | None, forward_host: str, forward_port: int) -> dict:
    existing = existing or {}
    return {
        "domain_names": [DOMAIN],
        "forward_scheme": "http",
        "forward_host": forward_host,
        "forward_port": forward_port,
        "access_list_id": 0,
        "certificate_id": existing.get("certificate_id", 0),
        "ssl_forced": True,
        "caching_enabled": False,
        "block_exploits": True,
        "advanced_config": "",
        "meta": {"letsencrypt_agree": False, "dns_challenge": False},
        "allow_websocket_upgrade": False,
        "http2_support": True,
        "forward_scheme_default": "http",
        "enabled": True,
        "locations": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="report only (the default)")
    parser.add_argument("--apply", action="store_true",
                        help="make the change")
    parser.add_argument("--upstream", default=FORWARD_HOST,
                        help=f"portal address (default {FORWARD_HOST})")
    parser.add_argument("--port", type=int, default=FORWARD_PORT,
                        help=f"portal port (default {FORWARD_PORT})")
    args = parser.parse_args()

    env = os.environ
    base = env.get("NPM_API_URL", "http://127.0.0.1:81")
    email = env.get("NPM_ADMIN_EMAIL", "")
    password = env.get("NPM_ADMIN_PASSWORD", "")
    if not (email and password):
        print("NPM_ADMIN_EMAIL and NPM_ADMIN_PASSWORD must be set", file=sys.stderr)
        return 2

    npm = Npm(base, email, password)
    kind, host = find(npm)
    target = f"{args.upstream}:{args.port}"

    if kind is None:
        print(f"{DOMAIN} is not hosted in NPM; nothing to point.")
        return 1

    print(f"found {DOMAIN} as {kind} id={host.get('id')}")
    print(json.dumps({key: host.get(key) for key in
                      ("id", "domain_names", "forward_host", "forward_port",
                       "forward_scheme", "certificate_id", "enabled")},
                     indent=2, sort_keys=True))

    if kind == "proxy-hosts":
        already = (host.get("forward_host") == args.upstream
                   and int(host.get("forward_port") or 0) == args.port)
        if already:
            print(f"already forwards to {target}; nothing to do")
            return 0
        body = proxy_body(host, args.upstream, args.port)
        if not args.apply:
            print(f"would update proxy host {host['id']} -> {target}")
            return 0
        npm.update("proxy-hosts", host["id"], {**writable(host), **body})
        print(f"updated proxy host {host['id']} -> {target}")
        return 0

    # A redirection host cannot forward to a page: replace it with a proxy host,
    # reusing its domains and certificate so TLS is unchanged.
    body = proxy_body(host, args.upstream, args.port)
    if not args.apply:
        print(f"would replace {kind} {host['id']} with a proxy host -> {target}")
        return 0
    npm.create("proxy-hosts", body)
    npm.delete(kind, host["id"])
    print(f"replaced {kind} {host['id']} with a proxy host -> {target}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NpmError as err:
        print(f"error: {err}", file=sys.stderr)
        raise SystemExit(1) from err
