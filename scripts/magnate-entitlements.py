#!/usr/bin/env python3
"""AthenIQ → Magnate (RevenueOps): paid-course entitlements.

Magnate owns revenue for the whole platform; AthenIQ never touches Stripe or a
price. This client is how a paid course is sold and checked:

  * `probe`              — is the entitlement API reachable and creds accepted?
  * `check`              — is a learner entitled to a plan? (the gate)
  * `buy`                — open a hosted Stripe Checkout for a course (one-off;
                           `--dry-run` prints the request without calling)
  * `verify-signature`   — validate a MAGNATE fulfillment callback (HMAC-SHA256)

The contract is Magnate's server-to-server v2.1 API:
  GET  /api/entitlements?plan=<slug>&user=<username|email>&phone=<e164>
       → {entitled: true|false|null, reason, plan, slug, status, expires_at}
  POST /api/purchases  {item:{slug,name,unitAmountCents}, metadata, ...}
       → {url, id, item}   (hosted Checkout)
       and on completion Magnate POSTs `purchase.completed` to its configured
       fulfillment hook with `X-Magnate-Signature` = hex(HMAC-SHA256(body, secret)).

Authentication is the shared bearer token Magnate calls `ENTITLEMENTS_API_TOKEN`
(same token gates `/api/purchases`). Unset on Magnate = open (trusted network).

Configuration comes from `.env` (see .env.example §Magnate):

    MAGNATE_API_URL=https://app.magnate.innotel.us
    MAGNATE_ENTITLEMENTS_TOKEN=<Magnate's ENTITLEMENTS_API_TOKEN>
    MAGNATE_PAID_PLAN=<plan slug that gates paid courses, e.g. premium>

Usage:
    python3 scripts/magnate-entitlements.py probe
    python3 scripts/magnate-entitlements.py check --user learner@x.edu --plan premium
    python3 scripts/magnate-entitlements.py buy --course course-v1:Innotel+TEST101+2026_T1 \\
        --name "TEST101 — certificate" --amount-cents 4900 --email learner@x.edu
    python3 scripts/magnate-entitlements.py verify-signature --secret "$SECRET" --body-file payload.json

Exit codes: 0 entitled/valid, 1 not entitled/invalid, 2 API or usage error.
"""
import argparse
import hashlib
import hmac
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "MAGNATE_API_URL": "https://app.magnate.innotel.us",
}


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

def load_dotenv(path):
    env = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip("'\"")
    except FileNotFoundError:
        pass
    return env


def cfg(name, default=""):
    if os.environ.get(name):
        return os.environ[name]
    return DEFAULTS.get(name, default)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _opener(insecure):
    ctx = ssl._create_unverified_context() if insecure else None
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def api(method, url, path, params=None, body=None, token="", insecure=False):
    """Call Magnate; return (status, parsed-json-or-{})."""
    query = ""
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        if clean:
            query = "?" + urllib.parse.urlencode(clean)
    full = url.rstrip("/") + path + query

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(full, method=method, data=data)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)

    try:
        with _opener(insecure).open(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw[:300]}
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach Magnate at {url}: {e.reason}")


def resolved(args):
    url = args.url or cfg("MAGNATE_API_URL", DEFAULTS["MAGNATE_API_URL"])
    token = args.token if args.token is not None else cfg("MAGNATE_ENTITLEMENTS_TOKEN")
    return url, token


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_probe(args):
    url, token = resolved(args)
    status, body = api("GET", url, "/api/entitlements", token=token, insecure=args.insecure)
    if status == 200:
        print(f"Magnate entitlement API reachable at {url}"
              f" (auth: {'bearer' if token else 'open'})")
        return 0
    if status in (401, 403):
        print(f"Magnate rejected the token (HTTP {status}) — check MAGNATE_ENTITLEMENTS_TOKEN.",
              file=sys.stderr)
        return 2
    print(f"Magnate returned HTTP {status}: {body}", file=sys.stderr)
    return 2


def cmd_check(args):
    url, token = resolved(args)
    plan = args.plan or cfg("MAGNATE_PAID_PLAN")
    if not plan:
        raise SystemExit("no plan given: pass --plan <slug> or set MAGNATE_PAID_PLAN in .env")
    status, body = api("GET", url, "/api/entitlements",
                       params={"plan": plan, "user": args.user, "phone": args.phone},
                       token=token, insecure=args.insecure)

    if args.json:
        print(json.dumps(body, indent=2, sort_keys=True))
    else:
        entitled = body.get("entitled")
        verdict = {True: "ENTITLED", False: "NOT ENTITLED", None: "UNKNOWN"}[entitled] \
            if entitled in (True, False, None) else str(entitled)
        print(f"{verdict}  user={body.get('user') or args.user or '-'} "
              f"plan={body.get('slug') or plan} reason={body.get('reason')}")
        if body.get("status"):
            print(f"  status={body['status']} expires_at={body.get('expires_at')}")

    if status == 200 and body.get("entitled") is True:
        return 0
    if status == 404:
        return 2
    return 1


def cmd_buy(args):
    url, token = resolved(args)
    item = {"slug": args.slug, "name": args.name, "unitAmountCents": args.amount_cents}
    body = {"item": item}
    metadata = dict(args.meta or [])
    if args.course:
        metadata["course_key"] = args.course
    if args.user:
        metadata["username"] = args.user
    if metadata:
        body["metadata"] = metadata
    if args.email:
        body["customerEmail"] = args.email
    if args.success_url:
        body["successUrl"] = args.success_url
    if args.cancel_url:
        body["cancelUrl"] = args.cancel_url

    if args.dry_run:
        print(json.dumps(body, indent=2, sort_keys=True))
        return 0

    status, resp = api("POST", url, "/api/purchases", body=body, token=token,
                       insecure=args.insecure)
    if status != 200:
        print(f"purchase failed (HTTP {status}): {resp}", file=sys.stderr)
        return 2
    print(resp.get("url", ""))
    if not args.quiet:
        print(f"[checkout session {resp.get('id')} for '{args.name}']", file=sys.stderr)
    return 0


def cmd_verify_signature(args):
    secret = args.secret or cfg("MAGNATE_PURCHASE_FULFILLMENT_SECRET")
    if not secret:
        raise SystemExit("no secret: pass --secret or set MAGNATE_PURCHASE_FULFILLMENT_SECRET")
    if args.body_file and args.body_file != "-":
        with open(args.body_file, "rb") as fh:
            raw = fh.read()
    else:
        raw = sys.stdin.buffer.read()
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(expected, (args.signature or "").strip().lower())
    print("VALID" if ok else "INVALID")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="override MAGNATE_API_URL")
    ap.add_argument("--token", help="override MAGNATE_ENTITLEMENTS_TOKEN")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", help="check the API is reachable and creds are accepted")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("check", help="check a learner's entitlement to a plan")
    p.add_argument("--user", help="learner username or email")
    p.add_argument("--plan", help="plan slug (defaults to MAGNATE_PAID_PLAN)")
    p.add_argument("--phone", help="E.164 phone identity (optional)")
    p.add_argument("--json", action="store_true", help="print the raw API response")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("buy", help="create a hosted Checkout for a course")
    p.add_argument("--course", help="Open edX course key (goes to metadata.course_key)")
    p.add_argument("--slug", default="course", help="item slug (default: course)")
    p.add_argument("--name", required=True, help="item name shown at checkout")
    p.add_argument("--amount-cents", type=int, required=True, dest="amount_cents")
    p.add_argument("--email", help="prefill the buyer's email")
    p.add_argument("--user", help="learner username (goes to metadata.username)")
    p.add_argument("--meta", action="append", metavar="K=V", help="extra metadata (repeatable)")
    p.add_argument("--success-url", dest="success_url")
    p.add_argument("--cancel-url", dest="cancel_url")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="print the request body; do not call Magnate")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_buy)

    p = sub.add_parser("verify-signature", help="verify an X-Magnate-Signature over a payload")
    p.add_argument("--secret", help="fulfillment secret (defaults to .env)")
    p.add_argument("--signature", required=True, help="the X-Magnate-Signature value")
    p.add_argument("--body-file", default="-", help="payload file (default: stdin)")
    p.set_defaults(func=cmd_verify_signature)

    args = ap.parse_args()
    env = load_dotenv(os.path.join(REPO, ".env"))
    for k, v in env.items():
        os.environ.setdefault(k, v)

    if getattr(args, "meta", None):
        parsed = []
        for pair in args.meta:
            key, _, val = pair.partition("=")
            parsed.append((key, val))
        args.meta = parsed

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
