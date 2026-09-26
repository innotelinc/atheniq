#!/usr/bin/env python3
"""AthenIQ → ONYX (StorageOps) bucket provisioning and verification.

Roadmap V2 moves classroom media off Convex's local volume and onto ONYX's
S3-compatible object store. This script is the operator step that makes that
possible: it creates the two buckets Convex expects and verifies they are
reachable with the configured credentials — before `make convex-up` is told to
use them.

It talks the S3 REST API directly (AWS SigV4, path- or virtual-host style) with
nothing but the Python standard library, matching the rest of this repo's
scripts. It never prints a secret.

Configuration comes from `.env` (see .env.example §ONYX):

    ONYX_S3_ENDPOINT          http://<onyx-host>:9000
    ONYX_S3_REGION            us-east-1
    ONYX_S3_FORCE_PATH_STYLE  true
    ONYX_S3_ACCESS_KEY        <access key>
    ONYX_S3_SECRET_KEY        <secret key>
    ONYX_S3_BUCKET_FILES      atheniq-files
    ONYX_S3_BUCKET_EXPORTS    atheniq-exports

Usage:
    python3 scripts/onyx-buckets.py --check     # verify buckets exist + are reachable
    python3 scripts/onyx-buckets.py --create    # create any missing bucket, then verify
    python3 scripts/onyx-buckets.py --dry-run   # show the plan; make no calls
    python3 scripts/onyx-buckets.py --selftest  # validate config + signing, no network

Flags: --endpoint URL, --region R, --bucket NAME (repeatable), --insecure.

Leaving the ONYX_* values blank is a supported state (Convex keeps files on its
own volume); this script is only run when an operator chooses to move media to
ONYX. See docs/Deployment.md §Stage 4 and docs/Integrations.md §ONYX.
"""
import argparse
import hashlib
import hmac
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "ONYX_S3_REGION": "us-east-1",
    "ONYX_S3_FORCE_PATH_STYLE": "true",
    "ONYX_S3_BUCKET_FILES": "atheniq-files",
    "ONYX_S3_BUCKET_EXPORTS": "atheniq-exports",
}

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
ALGORITHM = "AWS4-HMAC-SHA256"


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


def truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------
# AWS SigV4 (stdlib)
# --------------------------------------------------------------------------

def _hmac(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret, datestamp, region, service):
    key = _hmac(("AWS4" + secret).encode("utf-8"), datestamp)
    key = _hmac(key, region)
    key = _hmac(key, service)
    return _hmac(key, "aws4_request")


def _uri_encode(path):
    # S3 canonical URI: encode each segment but keep '/'.
    return urllib.parse.quote(path, safe="/-_.~")


def build_auth(method, host, path, access_key, secret_key, region, now=None):
    """Return the SigV4 Authorization header for an empty-body S3 request."""
    now = now or time.gmtime()
    amzdate = time.strftime("%Y%m%dT%H%M%SZ", now)
    datestamp = time.strftime("%Y%m%d", now)

    canonical_headers = f"host:{host}\nx-amz-content-sha256:{EMPTY_SHA256}\nx-amz-date:{amzdate}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([
        method,
        _uri_encode(path),
        "",  # canonical query string
        canonical_headers,
        signed_headers,
        EMPTY_SHA256,
    ])

    scope = f"{datestamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join([
        ALGORITHM,
        amzdate,
        scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    signature = hmac.new(
        signing_key(secret_key, datestamp, region, "s3"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return (
        f"{ALGORITHM} Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}",
        amzdate,
    )


def s3_request(method, endpoint, bucket, access_key, secret_key, region,
               path_style=True, insecure=False):
    """Perform an empty-body S3 bucket request; return (status, body)."""
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in ("http", "https"):
        raise SystemExit(f"ONYX_S3_ENDPOINT must be an http(s) URL, got: {endpoint}")

    netloc = parsed.netloc
    base_path = parsed.path.rstrip("/")
    if not bucket:
        # Service root (ListBuckets) — no bucket to address, either style.
        host, path = netloc, base_path or "/"
    elif path_style:
        host = netloc
        path = f"{base_path}/{bucket}" if base_path else f"/{bucket}"
    else:
        host = f"{bucket}.{netloc}"
        path = base_path or "/"

    auth, amzdate = build_auth(method, host, path, access_key, secret_key, region)
    url = urllib.parse.urlunparse((parsed.scheme, host, path, "", "", ""))
    req = urllib.request.Request(url, method=method, data=b"" if method == "PUT" else None)
    req.add_header("Authorization", auth)
    req.add_header("x-amz-content-sha256", EMPTY_SHA256)
    req.add_header("x-amz-date", amzdate)

    ctx = None
    if insecure and parsed.scheme == "https":
        import ssl
        ctx = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach ONYX at {endpoint}: {e.reason}")


# --------------------------------------------------------------------------
# buckets
# --------------------------------------------------------------------------

def buckets_from_args(args):
    if args.bucket:
        return list(dict.fromkeys(args.bucket))
    names = [
        cfg("ONYX_S3_BUCKET_FILES", DEFAULTS["ONYX_S3_BUCKET_FILES"]),
        cfg("ONYX_S3_BUCKET_EXPORTS", DEFAULTS["ONYX_S3_BUCKET_EXPORTS"]),
    ]
    return list(dict.fromkeys(n for n in names if n))


def resolve(args):
    endpoint = (args.endpoint or cfg("ONYX_S3_ENDPOINT")).rstrip("/")
    access_key = cfg("ONYX_S3_ACCESS_KEY")
    secret_key = cfg("ONYX_S3_SECRET_KEY")
    region = args.region or cfg("ONYX_S3_REGION", DEFAULTS["ONYX_S3_REGION"])
    path_style = args.path_style if args.path_style is not None else truthy(
        cfg("ONYX_S3_FORCE_PATH_STYLE", DEFAULTS["ONYX_S3_FORCE_PATH_STYLE"])
    )
    return endpoint, access_key, secret_key, region, path_style


def selftest(args):
    endpoint, access_key, secret_key, region, path_style = resolve(args)
    print("ONYX S3 configuration self-test")
    print(f"  endpoint            : {endpoint or '(unset)'}")
    print(f"  region              : {region}")
    print(f"  path style          : {path_style}")
    print(f"  access key          : {'set' if access_key else 'MISSING'}")
    print(f"  secret key          : {'set' if secret_key else 'MISSING'}")
    host = urllib.parse.urlparse(endpoint).netloc if endpoint else "example.com"
    auth, amzdate = build_auth("HEAD", host, "/selftest", access_key or "AKID",
                               secret_key or "SECRET", region)
    ok = auth.startswith("AWS4-HMAC-SHA256 Credential=") and f"/{region}/s3/aws4_request" in auth
    print(f"  signing             : {'ok' if ok else 'FAILED'} ({amzdate})")
    missing = not endpoint or not access_key or not secret_key
    return 0 if (ok and not missing) else 1


def run(args):
    endpoint, access_key, secret_key, region, path_style = resolve(args)
    names = buckets_from_args(args)

    if not endpoint or not access_key or not secret_key:
        raise SystemExit(
            "ONYX is not configured. Set ONYX_S3_ENDPOINT, ONYX_S3_ACCESS_KEY and "
            "ONYX_S3_SECRET_KEY in .env (see .env.example). Leaving ONYX blank is "
            "supported — Convex then keeps files on its own volume."
        )

    print(f"ONYX buckets @ {endpoint} (region {region}, path-style={path_style})")

    # Credential probe first: S3 answers a bad signature with 401/403 and a
    # missing bucket with 404, so checking auth up front keeps "wrong key" from
    # being read as "bucket absent".
    probe, body = s3_request("GET", endpoint, "", access_key, secret_key,
                             region, path_style, args.insecure)
    if probe != 200:
        reason = "rejected" if probe in (401, 403) else f"HTTP {probe}"
        detail = ""
        for line in body.splitlines():
            if "<Message>" in line:
                detail = " — " + line.split("<Message>", 1)[1].split("</Message>", 1)[0]
                break
        print(f"  credentials              {reason}{detail}")
        print("\nONYX refused the configured credentials — check ONYX_S3_ACCESS_KEY/"
              "ONYX_S3_SECRET_KEY against the ONYX deployment.")
        return 2
    print("  credentials              ok")

    failures = 0
    would_create = 0
    for name in names:
        status, _ = s3_request("HEAD", endpoint, name, access_key, secret_key,
                               region, path_style, args.insecure)
        if status == 200:
            print(f"  {name:<24} present")
        elif status == 404:
            if args.create and not args.dry_run:
                created, body = s3_request("PUT", endpoint, name, access_key, secret_key,
                                           region, path_style, args.insecure)
                if created in (200, 201):
                    print(f"  {name:<24} created")
                else:
                    print(f"  {name:<24} create failed (HTTP {created}) {body[:200]}")
                    failures += 1
            elif args.dry_run:
                print(f"  {name:<24} missing (would create)")
                would_create += 1
            else:
                print(f"  {name:<24} missing")
                failures += 1
        elif status in (401, 403):
            print(f"  {name:<24} forbidden (credentials lack access)")
            failures += 1
        else:
            print(f"  {name:<24} error (HTTP {status})")
            failures += 1

    if args.dry_run:
        print(f"\ndry run — {would_create} bucket(s) would be created; nothing changed.")
        return 0
    if failures:
        print(f"\n{failures} bucket(s) not ready.")
        return 1
    print("\nOK — ONYX is ready for classroom media.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="verify buckets (default)")
    ap.add_argument("--create", action="store_true", help="create missing buckets, then verify")
    ap.add_argument("--dry-run", action="store_true", help="show the plan; make no calls")
    ap.add_argument("--selftest", action="store_true", help="validate config + signing, no network")
    ap.add_argument("--endpoint", help="override ONYX_S3_ENDPOINT")
    ap.add_argument("--region", help="override ONYX_S3_REGION")
    ap.add_argument("--bucket", action="append", help="restrict to this bucket (repeatable)")
    ap.add_argument("--path-style", dest="path_style", action="store_true", default=None)
    ap.add_argument("--virtual-host", dest="path_style", action="store_false")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification")
    args = ap.parse_args()

    env = load_dotenv(os.path.join(REPO, ".env"))
    for k, v in env.items():
        os.environ.setdefault(k, v)

    if args.selftest:
        sys.exit(selftest(args))
    sys.exit(run(args))


if __name__ == "__main__":
    main()
