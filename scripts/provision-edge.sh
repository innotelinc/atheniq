#!/usr/bin/env bash
# provision-edge.sh — make AthenIQ's Open edX surfaces reachable publicly.
#
# Idempotent. Does three things:
#   1. DNS: adds CNAME records (learn/studio/apps.learn/meilisearch.learn ->
#      innotel.us apex) to the authoritative BIND zone via TSIG nsupdate.
#   2. NPM edge: creates/updates the proxy hosts forwarding
#      https://<domain> -> http://192.168.1.46:18080 (Tutor caddy).
#   3. Certificates: learn/studio attach the existing *.innotel.us wildcard;
#      apps.learn + meilisearch.learn get single-name Let's Encrypt certs via
#      NPM (HTTP-01). NPM's own wildcard issuance (rfc2136) currently 500s, so
#      no *.learn.innotel.us wildcard is requested here.
#
# Reads cerulean-dns-platform/.env for BIND TSIG + NPM credentials, or the
# CERULEAN_ENV / NPM_API_URL / NPM_EMAIL / NPM_PASSWORD env vars.
set -euo pipefail

CERULEAN_ENV="${CERULEAN_ENV:-/usr/src/projects/complete/cerulean-dns-platform/.env}"
[ -f "$CERULEAN_ENV" ] && set -a && . "$CERULEAN_ENV" && set +a

BIND_SERVER="${BIND_SERVER:-192.168.1.80}"
BIND_TSIG_NAME="${BIND_TSIG_NAME:-cerulean}"
FORWARD_HOST="${FORWARD_HOST:-192.168.1.46}"
FORWARD_PORT="${FORWARD_PORT:-18080}"
NPM_API_URL="${NPM_API_URL:-http://192.168.1.71:81}"
WILDCARD_CERT_ID="${WILDCARD_CERT_ID:-110}"   # *.innotel.us already on the edge
ACME_EMAIL="${ACME_EMAIL:-admin@innotel.us}"
DOMAINS=(learn.innotel.us studio.innotel.us apps.learn.innotel.us meilisearch.learn.innotel.us)

echo "== 1/3 DNS CNAMEs (TSIG nsupdate -> $BIND_SERVER) =="
if [ -n "${BIND_TSIG_SECRET:-}" ]; then
  keyfile=$(mktemp)
  chmod 600 "$keyfile"
  printf 'key "%s" { algorithm hmac-sha256; secret "%s"; };\n' "$BIND_TSIG_NAME" "$BIND_TSIG_SECRET" > "$keyfile"
  { echo "server $BIND_SERVER"; echo "zone innotel.us.";
    for d in "${DOMAINS[@]}"; do
      echo "update delete ${d}. CNAME"
      echo "update add ${d}. 300 CNAME innotel.us."
    done
    echo send; } | nsupdate -k "$keyfile"
  rm -f "$keyfile"
  echo "   DNS records set: ${DOMAINS[*]} -> innotel.us"
else
  echo "   BIND_TSIG_SECRET unset — skipping DNS (records must already exist)"
fi

echo "== 2/3 NPM proxy hosts + certs -> http://${FORWARD_HOST}:${FORWARD_PORT} =="
NPM_API_URL="$NPM_API_URL" NPM_EMAIL="$NPM_EMAIL" NPM_PASSWORD="$NPM_PASSWORD" \
WILDCARD_CERT_ID="$WILDCARD_CERT_ID" ACME_EMAIL="$ACME_EMAIL" \
FORWARD_HOST="$FORWARD_HOST" FORWARD_PORT="$FORWARD_PORT" \
python3 - <<'PY'
import json, os, urllib.request, urllib.error

api = os.environ["NPM_API_URL"].rstrip("/")
def req(method, path, body=None):
    r = urllib.request.Request(api + path, method=method,
        data=json.dumps(body).encode() if body is not None else None)
    r.add_header("Content-Type", "application/json")
    if getattr(req, "token", None):
        r.add_header("Authorization", "Bearer " + req.token)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"NPM {method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")

token_resp = req("POST", "/api/tokens", {"identity": os.environ["NPM_EMAIL"], "secret": os.environ["NPM_PASSWORD"]})
req.token = token_resp["token"]

hosts = req("GET", "/api/nginx/proxy-hosts") or []
by_domain = {h["domain_names"][0]: h for h in hosts}
wild_id = int(os.environ["WILDCARD_CERT_ID"])
le_meta = {"letsencrypt_agree": True, "dns_challenge": False,
           "letsencrypt_email": os.environ["ACME_EMAIL"], "letsencrypt_force": True,
           "hsts": False, "hsts_subdomains": False}
plain_meta = {"letsencrypt_agree": False, "dns_challenge": False}

plan = [
    ("learn.innotel.us", wild_id, plain_meta),
    ("studio.innotel.us", wild_id, plain_meta),
    ("apps.learn.innotel.us", "new", le_meta),
    ("meilisearch.learn.innotel.us", "new", le_meta),
]
for domain, cert, meta in plan:
    payload = {"domain_names": [domain], "forward_scheme": "http",
               "forward_host": os.environ["FORWARD_HOST"],
               "forward_port": int(os.environ["FORWARD_PORT"]),
               "certificate_id": cert, "ssl_forced": True, "http2_support": True,
               "block_exploits": True, "caching_enabled": False,
               "allow_websocket_upgrade": True, "access_list_id": 0,
               "advanced_config": "", "locations": [], "meta": meta,
               "enabled": True}
    existing = by_domain.get(domain)
    if existing:
        payload["id"] = existing["id"]
        out = req("PUT", f"/api/nginx/proxy-hosts/{existing['id']}", payload)
        print(f"   updated {domain} (host {existing['id']})")
    else:
        out = req("POST", "/api/nginx/proxy-hosts", payload)
        print(f"   created {domain} (host {out['id']})")
PY

echo "== 3/3 verify =="
for d in "${DOMAINS[@]}"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://${d}/" || true)
  echo "   https://${d} -> ${code}"
done
