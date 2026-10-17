#!/usr/bin/env python3
"""cert-check.py — does the edge still hold a certificate for every public name?

WHY THIS EXISTS. AthenIQ's public names answer through Cerulean's NGINX Proxy
Manager, which terminates TLS and holds a certificate per name. That is one
step away from anything in this repo, which is exactly why it can rot without a
commit: a name can lose its host, keep a certificate that covers a *different*
name, or — the failure this was written after — be served a **chain with only
the leaf in it**. A leaf-only chain verifies for every client whose trust store
already holds the issuer and for none whose does not, so curl on a machine with
the intermediate cached says "ok" while a browser shows "not secure".

WHAT IT CHECKS. For each name: the TLS handshake verifies against the system
trust store (which catches an untrusted, expired or mismatched certificate, and
a leaf-only chain), the certificate's own SAN list covers the name, the served
chain carries at least an issuer as well as the leaf, and the certificate is not
expired — with a warning window before it is.

    make cert-check                       # the platform's public names
    python3 scripts/cert-check.py lms.innotel.us studio.innotel.us
    python3 scripts/cert-check.py --json --warn-days 30

Exit status is 0 when every name passes and 1 when any does not, so it can gate
a deploy (scripts/deploy.sh runs it) or a cron.
"""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

#: The names the platform publishes, in the order a person meets them. Each is
#: read as a hostname and checked on 443.
PLATFORM_HOSTS: tuple[str, ...] = (
    "atheniq.innotel.us",
    "lms.innotel.us",
    "apps.lms.innotel.us",
    "learn.innotel.us",
    "studio.innotel.us",
    "classroom.innotel.us",
    "meilisearch.lms.innotel.us",
)

#: A certificate inside this window is reported but does not fail the check:
#: Cerulean renews 30 days out, so nothing here should ever come close.
WARN_DAYS = 21

#: Chain depth a complete chain has: the leaf plus at least its issuer.
MIN_CHAIN = 2


@dataclass
class Result:
    """One name's verdict. `failures` empty means the name is trustworthy."""

    host: str
    ok: bool = False
    detail: str = ""
    chain: int | None = None
    days_left: float | None = None
    subject: str = ""
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def line(self) -> str:
        state = "FAIL" if self.failures else ("WARN" if self.warnings else "OK")
        chain = "?" if self.chain is None else str(self.chain)
        days = "?" if self.days_left is None else f"{self.days_left:.0f}d"
        note = "; ".join(self.failures + self.warnings) or self.detail
        return f"{state:<4} {self.host:<30} chain={chain:<2} expires={days:<5} {note}".rstrip()


def host_matches(pattern: str, host: str) -> bool:
    """Does one SAN entry cover `host`?

    DNS names are case-insensitive, and a wildcard stands for exactly one label:
    `*.example.com` covers `a.example.com` but neither `example.com` nor
    `a.b.example.com` (RFC 6125).
    """
    pattern, host = pattern.lower().rstrip("."), host.lower().rstrip(".")
    if pattern.startswith("*."):
        suffix = pattern[1:]                      # ".example.com"
        return host.endswith(suffix) and host.count(".") == suffix.count(".")
    return pattern == host


def certificate_covers(host: str, san_entries) -> bool:
    """Whether any SAN entry covers `host` (`ssl` yields `("DNS", name)` pairs)."""
    return any(
        kind.upper() == "DNS" and host_matches(str(value), host)
        for kind, value in (entry for entry in san_entries or ())
    )


def count_certificates(pem_text: str) -> int:
    """How many certificates a PEM bundle carries — a leaf-only chain is 1."""
    return pem_text.count("-----BEGIN CERTIFICATE-----")


def parse_openssl_time(value: str) -> datetime:
    """`notAfter` as Python reports it: `Sep 15 06:53:38 2026 GMT`."""
    return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)


def days_until(when: datetime, now: datetime | None = None) -> float:
    return (when - (now or datetime.now(timezone.utc))).total_seconds() / 86400


def chain_depth(host: str, port: int, timeout: float, pem_text: str) -> int | None:
    """How many certificates the server actually sent.

    Python exposes the chain natively from 3.13; before that the count comes from
    `openssl s_client`, and a host without openssl reports `None` (unknown) rather
    than a pass — an unmeasurable chain is not a complete one.
    """
    if pem_text:
        return count_certificates(pem_text)
    try:
        out = subprocess.run(
            ["openssl", "s_client", "-connect", f"{host}:{port}", "-servername", host,
             "-showcerts"],
            input=b"", capture_output=True, timeout=max(timeout, 10),
        ).stdout.decode("utf-8", "replace")
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return count_certificates(out) or None


def check_host(host: str, port: int = 443, timeout: float = 15.0,
               warn_days: float = WARN_DAYS) -> Result:
    """Verify one name end to end. Never raises: a failure is a Result."""
    result = Result(host=host)
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    pem = ""
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
                chain = getattr(tls, "get_unverified_chain", None)
                if callable(chain):                    # Python 3.13+
                    der = chain()
                    pem = "\n".join(
                        ssl.DER_cert_to_PEM_cert(item.public_bytes(ssl.Encoding.DER))
                        if hasattr(item, "public_bytes") else ssl.DER_cert_to_PEM_cert(item)
                        for item in (der or [])
                    )
                result.subject = dict(x[0] for x in cert.get("subject", ())).get("commonName", "")
    except ssl.SSLCertVerificationError as exc:
        result.failures.append(f"TLS verification failed: {exc.verify_message}")
        result.detail = "handshake rejected the certificate"
        return _finish(result, host, port, timeout, warn_days, pem)
    except (ssl.SSLError, socket.timeout, OSError) as exc:
        result.failures.append(f"{type(exc).__name__}: {exc}")
        result.detail = "unreachable"
        return _finish(result, host, port, timeout, warn_days, pem)

    san = cert.get("subjectAltName", ())
    if not san:
        result.failures.append("certificate names no hosts (no SAN)")
    elif not certificate_covers(host, san):
        names = ", ".join(value for _, value in san)
        result.failures.append(f"certificate does not cover {host} (SAN: {names})")

    return _finish(result, host, port, timeout, warn_days, pem, cert)


def _finish(result: Result, host: str, port: int, timeout: float, warn_days: float,
            pem: str, cert: dict | None = None) -> Result:
    result.chain = chain_depth(host, port, timeout, pem)
    if result.chain is None:
        result.warnings.append("chain depth unknown (no openssl)")
    elif result.chain < MIN_CHAIN:
        result.failures.append(f"incomplete chain: {result.chain} certificate(s) sent")

    not_after = (cert or {}).get("notAfter")
    if not_after:
        try:
            left = days_until(parse_openssl_time(not_after))
        except ValueError:
            result.warnings.append(f"unparsable notAfter {not_after!r}")
        else:
            result.days_left = left
            if left < 0:
                result.failures.append(f"expired {abs(left):.0f}d ago")
            elif left < warn_days:
                result.warnings.append(f"renews in {left:.0f}d")

    result.ok = not result.failures
    if result.ok and not result.detail:
        result.detail = f"CN={result.subject}"
    return result


def summarize(results) -> int:
    """Print the table and return the exit status: 1 when anything failed."""
    for result in results:
        print(result.line())
    failed = [r for r in results if r.failures]
    warned = [r for r in results if r.warnings and not r.failures]
    print(f"\n{len(results)} name(s): {len(results) - len(failed) - len(warned)} ok, "
          f"{len(warned)} warning(s), {len(failed)} failure(s)")
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify the platform's public certificates.")
    parser.add_argument("hosts", nargs="*", help="names to check (default: the platform's)")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--warn-days", type=float, default=WARN_DAYS,
                        help="report a renewal this many days out (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    hosts = args.hosts or list(PLATFORM_HOSTS)
    results = [check_host(h, port=args.port, timeout=args.timeout, warn_days=args.warn_days)
               for h in hosts]
    if args.json:
        print(json.dumps([{
            "host": r.host, "ok": r.ok, "chain": r.chain,
            "days_left": None if r.days_left is None else round(r.days_left, 1),
            "subject": r.subject, "failures": r.failures, "warnings": r.warnings,
        } for r in results], indent=2))
        return 1 if any(r.failures for r in results) else 0
    return summarize(results)


if __name__ == "__main__":
    sys.exit(main())
