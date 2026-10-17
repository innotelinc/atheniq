#!/usr/bin/env bash
# provision-edge.sh — put AthenIQ's public hosts on Cerulean's DNS + edge.
#
# Idempotent. For each host it does three things, all through Cerulean:
#   1. DNS: a CNAME to the `innotel.us.` apex (the edge's A record), written to
#      the zone Cerulean serves from Technitium (POST /api/domains/:id/records).
#      No TSIG/nsupdate: Cerulean replaced the BIND plane.
#   2. Certificate: a Let's Encrypt cert for the name via DNS-01 through the same
#      zone (POST /api/certificates). An already-issued cert is reused, so
#      re-running does not burn an issuance.
#   3. NPM: the cert is exported to nginx proxy manager and the proxy host is
#      created or updated to forward https://<host> -> the Tutor caddy
#      (http://<tutor-host>:18080), TLS terminated on the edge.
#
# Cerulean's password sign-in is disabled once SSO is on, so authenticate with a
# session token from the portal (CERULEAN_TOKEN), or point CERULEAN_ENV at the
# cerulean repo's .env and set BREAKGLASS_LOGIN=1 there for the run.
#
#   ./scripts/provision-edge.sh                  # all hosts
#   ./scripts/provision-edge.sh lms.innotel.us   # just one (or several)
#   DRY_RUN=1 ./scripts/provision-edge.sh        # print the plan, change nothing
set -euo pipefail

CERULEAN_ENV="${CERULEAN_ENV:-/usr/src/projects/complete/1-primary/cerulean/.env}"

# Read only the variable we need. Sourcing the file (as the older BIND flow did)
# executes it, and its values are shell-unquoted text like `Cerulean DNS`, which
# then runs as a command. The zone is deliberately not taken from that file: it
# names the box's private lab zone, while the public hosts live in the
# registered zone below.
if [ -z "${CERULEAN_ADMIN_PASSWORD:-}" ] && [ -f "$CERULEAN_ENV" ]; then
  password=$(grep -m1 '^CERULEAN_ADMIN_PASSWORD=' "$CERULEAN_ENV" | cut -d= -f2-)
  password=${password%\"}; password=${password#\"}
  password=${password%\'}; password=${password#\'}
  CERULEAN_ADMIN_PASSWORD=$password
  export CERULEAN_ADMIN_PASSWORD
fi

CERULEAN_URL="${CERULEAN_URL:-http://192.168.1.71:3003}"
ZONE="${CERULEAN_ZONE:-innotel.us}"
# The Tutor caddy: plain HTTP on :18080 (ENABLE_HTTPS=true, ENABLE_WEB_PROXY=false,
# so the LMS emits https:// URLs while the edge terminates TLS).
FORWARD_HOST="${FORWARD_HOST:-192.168.1.59}"
FORWARD_PORT="${FORWARD_PORT:-18080}"
# Students use lms.<zone>; learn keeps the canonical LMS name the MFEs are built on.
HOSTS=("$@")
if [ "${#HOSTS[@]}" -eq 0 ]; then
  HOSTS=(lms.$ZONE learn.$ZONE studio.$ZONE apps.learn.$ZONE meilisearch.learn.$ZONE)
fi

echo "== Cerulean edge: ${HOSTS[*]} -> $FORWARD_HOST:$FORWARD_PORT =="

CERULEAN_URL="$CERULEAN_URL" ZONE="$ZONE" DRY_RUN="${DRY_RUN:-0}" \
FORWARD_HOST="$FORWARD_HOST" FORWARD_PORT="$FORWARD_PORT" HOSTS="${HOSTS[*]}" \
python3 - <<'PY'
import json, os, time, urllib.error, urllib.request

base = os.environ["CERULEAN_URL"].rstrip("/")
zone = os.environ["ZONE"]
hosts = os.environ["HOSTS"].split()
forward_host = os.environ["FORWARD_HOST"]
forward_port = int(os.environ["FORWARD_PORT"])
dry = os.environ["DRY_RUN"] == "1"
token = os.environ.get("CERULEAN_TOKEN", "").strip()


def req(method, path, body=None, auth=True):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if auth and token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Cerulean {method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")


if not token:
    password = os.environ.get("CERULEAN_ADMIN_PASSWORD", "")
    if not password:
        raise SystemExit("No CERULEAN_TOKEN and no CERULEAN_ADMIN_PASSWORD — cannot authenticate")
    token = req("POST", "/api/auth/login", {"password": password}, auth=False)["token"]

zones = req("GET", "/api/domains") or []
match = [z for z in zones if z.get("name") == zone]
if not match:
    raise SystemExit(f"Zone {zone} is not registered in Cerulean (manage it under Domains)")
zone_id = match[0]["id"]

records = req("GET", f"/api/domains/{zone_id}/records") or []
certs = req("GET", "/api/certificates") or []
npm_hosts = req("GET", "/api/npm/hosts") or []

for host in hosts:
    label = host[: -len(zone) - 1] if host.endswith("." + zone) else host

    # 1. DNS
    cnames = [r for r in records if str(r.get("name")) in (label, host) and str(r.get("type")) == "CNAME"]
    if cnames and any(str(r.get("value")).rstrip(".") == zone for r in cnames):
        print(f"   dns   {host}: already CNAME {zone}")
    elif dry:
        print(f"   dns   {host}: would add CNAME {zone}")
    else:
        out = req("POST", f"/api/domains/{zone_id}/records",
                  {"type": "CNAME", "name": label, "value": zone + ".", "ttl": 300})
        print(f"   dns   {host}: CNAME {zone}" if out and not out.get("_error") else f"   dns   {host}: {out}")

    # 2. Certificate (ACME DNS-01 through the same zone)
    cert = next((c for c in certs if c.get("domain") == host and c.get("status") == "issued"), None)
    if cert:
        print(f"   cert  {host}: reusing {cert['id']}")
    elif dry:
        print(f"   cert  {host}: would request a Let's Encrypt cert")
    else:
        created = req("POST", "/api/certificates", {"domain": host})
        cert_id = created["id"]
        for _ in range(90):
            cert = req("GET", f"/api/certificates/{cert_id}")
            if cert.get("status") in ("issued", "error", "failed"):
                break
            time.sleep(4)
        if cert.get("status") != "issued":
            raise SystemExit(f"cert  {host}: {cert.get('status')} — {cert.get('error')}")
        print(f"   cert  {host}: issued {cert_id} (expires {cert.get('expiresAt')})")

    # 3. NPM host
    existing = next((h for h in npm_hosts if host in (h.get("domain_names") or [])), None)
    if existing and existing.get("forward_host") == forward_host and existing.get("forward_port") == forward_port:
        print(f"   npm   {host}: already forwards to {forward_host}:{forward_port}")
        continue
    if dry:
        print(f"   npm   {host}: would point at {forward_host}:{forward_port}")
        continue
    exported = req("POST", "/api/npm/export-cert",
                   {"certificate_id": cert["id"], "nice_name": f"cerulean-{host}"})
    npm_cert = exported["npmCertificateId"]
    body = {"forward_host": forward_host, "forward_port": forward_port,
            "forward_scheme": "http", "certificate_id": npm_cert, "ssl_forced": True}
    if existing:
        req("PUT", f"/api/npm/hosts/{existing['id']}", body)
        print(f"   npm   {host}: updated host {existing['id']} (cert {npm_cert})")
    else:
        out = req("POST", "/api/npm/hosts", {"domain": host, **body})
        print(f"   npm   {host}: created host {out['id']} (cert {npm_cert})")
PY

echo "== verify =="
for d in "${HOSTS[@]}"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://${d}/" || true)
  echo "   https://${d} -> ${code:-no answer}"
done
