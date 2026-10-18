#!/usr/bin/env python3
"""Publish `ai.lms.<domain>` — the course-generation console — on the edge.

Runs on the edge host (inside the `proxy` container, which holds Cerulean's
env, the NPM admin credentials and the Technitium token). Three idempotent
steps:

1. the zone CNAME (`ai.lms.innotel.us` -> `innotel.us.`), because the edge's
   public address is the apex A record;
2. the NPM certificate that covers the name — created by Cerulean's ACME path
   and uploaded with `scripts/npm-upload-cert.py`, since NPM is what terminates
   TLS;
3. the NPM proxy host in front of the console's SSO proxy, copying the shape of
   the classroom's own host (HTTP upstream, websockets on, block exploits).

    python3 scripts/ai-lms-edge.py            # apply
    DRY_RUN=1 python3 scripts/ai-lms-edge.py  # plan only

Unlike `scripts/provision-edge.sh` (which drives Cerulean's API for the Tutor
names, all of which forward to caddy on :18080) this one hard-codes the console
pair — a different upstream — and is the template to copy when another
staff-only surface joins the edge. `learn-edge.py` is the same story for the
`learn.` / `meilisearch.learn.` names.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV = "/usr/src/projects/complete/1-primary/cerulean/.env"
ZONE = "innotel.us"
APEX = ZONE + "."
HOST = "ai.lms." + ZONE
UPSTREAM = ("192.168.1.59", 8091)  # the console's oauth2-proxy
MODEL_HOST_ID = 214  # classroom.innotel.us — another SSO proxy in front of an app
DRY = os.environ.get("DRY_RUN") == "1"

env = {}
for line in open(ENV):
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line.rstrip("\n"))
    if match:
        env[match.group(1)] = match.group(2).strip().strip('"').strip("'")


def call(url, method="GET", body=None, headers=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as err:
        raise SystemExit(f"{method} {url} -> HTTP {err.code}: {err.read().decode()[:300]}")


# ---------------------------------------------------------------- Technitium
technitium = env["TECHNITIUM_URL"].rstrip("/")
token = call(f"{technitium}/api/user/login?user=admin&pass=" +
             urllib.parse.quote(env["TECHNITIUM_ADMIN_PASSWORD"], safe=""))["token"]

found = call(f"{technitium}/api/zones/records/get?token={token}&zone={ZONE}&domain={HOST}")
records = (found.get("response") or {}).get("records") or []
cnames = [r for r in records if r.get("type") == "CNAME"]
if cnames:
    print(f"  dns   {HOST}: already {(cnames[0].get('rData') or {}).get('cname')}")
elif DRY:
    print(f"  dns   {HOST}: would add CNAME {APEX}")
else:
    out = call(f"{technitium}/api/zones/records/add?token={token}&domain={HOST}&zone={ZONE}"
               f"&type=CNAME&cname={APEX}&ttl=300")
    print(f"  dns   {HOST}: {out.get('status')} -> {APEX}")

# -------------------------------------------------------------------- NPM
npm = env.get("NPM_PUBLIC_API_URL", "http://127.0.0.1:81").rstrip("/")
jwt = call(f"{npm}/api/tokens", "POST",
           {"identity": env["NPM_ADMIN_EMAIL"], "secret": env["NPM_ADMIN_PASSWORD"]})["token"]
auth = {"Authorization": "Bearer " + jwt}

cert_id = None
for cert in call(f"{npm}/api/nginx/certificates", headers=auth):
    names = cert.get("domain_names") or []
    if HOST in names or (cert.get("nice_name") or "") == f"cerulean-{HOST}":
        cert_id = cert["id"]
        print(f"  tls   {HOST}: certificate {cert_id} ({cert.get('expires_on')})")
if cert_id is None:
    raise SystemExit(f"no NPM certificate covers {HOST} — run scripts/npm-upload-cert.py first")

model = call(f"{npm}/api/nginx/proxy-hosts/{MODEL_HOST_ID}", headers=auth)
hosts = call(f"{npm}/api/nginx/proxy-hosts", headers=auth)
existing = next((h for h in hosts if HOST in (h.get("domain_names") or [])), None)

body = {
    "domain_names": [HOST],
    "forward_scheme": "http",
    "forward_host": UPSTREAM[0],
    "forward_port": UPSTREAM[1],
    "ssl_forced": True,
    "http2_support": model.get("http2_support", True),
    "hsts_enabled": model.get("hsts_enabled", False),
    "hsts_subdomains": False,
    "block_exploits": model.get("block_exploits", True),
    "caching_enabled": False,
    "allow_websocket_upgrade": True,
    "access_list_id": model.get("access_list_id", 0),
    "advanced_config": "",
    "meta": {"letsencrypt_agree": False, "dns_challenge": False},
    "locations": [],
    "enabled": True,
    "certificate_id": cert_id,
}
if existing and existing.get("certificate_id") == cert_id \
        and existing.get("forward_host") == UPSTREAM[0] \
        and existing.get("forward_port") == UPSTREAM[1]:
    print(f"  npm   {HOST}: already host {existing['id']} -> {UPSTREAM[0]}:{UPSTREAM[1]} "
          f"cert {cert_id}")
elif DRY:
    print(f"  npm   {HOST}: would {'update ' + str(existing['id']) if existing else 'create'} "
          f"-> {UPSTREAM[0]}:{UPSTREAM[1]} cert {cert_id}")
else:
    if existing:
        call(f"{npm}/api/nginx/proxy-hosts/{existing['id']}", "PUT", body, auth)
        print(f"  npm   {HOST}: updated host {existing['id']} cert {cert_id}")
    else:
        created = call(f"{npm}/api/nginx/proxy-hosts", "POST", body, auth)
        print(f"  npm   {HOST}: created host {created['id']} -> {UPSTREAM[0]}:{UPSTREAM[1]} "
              f"cert {cert_id}")

for host in call(f"{npm}/api/nginx/proxy-hosts", headers=auth):
    if HOST in (host.get("domain_names") or []):
        print(f"  host  {host['domain_names']} enabled={host.get('enabled')} "
              f"cert={host.get('certificate_id')} ssl={host.get('ssl_forced')} -> "
              f"{host.get('forward_host')}:{host.get('forward_port')}")
