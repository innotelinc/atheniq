#!/usr/bin/env python3
"""Upload a Cerulean-issued certificate into NPM (runs on the edge host).

Cerulean issues the certificate and stores the material in its own database
(`scripts/cerulean-issue-cert.js`); NPM is what terminates TLS, so the material
has to get there too. NPM takes it in two calls — create the certificate row,
then POST the PEMs to `/upload` as a **multipart** body (a JSON body is answered
with `No files were uploaded`) — and its `domain_names` are rewritten to the
CN on upload, so the stable handle afterwards is `nice_name`, which this writes
as `cerulean-<host>` like the rest of the deployment.

    python3 scripts/npm-upload-cert.py 51          # by cerulean certificate id

Idempotent: an upload whose `nice_name` already exists is reused and its PEMs
refreshed, so a renewal is the same command. Then point a proxy host at the
returned certificate id (`scripts/ai-lms-edge.py` does that for the generation
console, and is the shape to copy for another name).
"""
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request

ENV = "/usr/src/projects/complete/1-primary/cerulean/.env"
DB = "/usr/src/projects/complete/1-primary/cerulean/data/cerulean.db"

if len(sys.argv) < 2:
    raise SystemExit("usage: npm-upload-cert.py <cerulean certificate id>")
cerulean_id = int(sys.argv[1])

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


def upload_pem(url, certificate, key, headers):
    """POST the two PEMs as a multipart form — three parts, no library."""
    boundary = "----ceruleanupload7f3a"
    parts = []
    for name, filename, content in (("certificate", "certificate.pem", certificate),
                                    ("certificate_key", "key.pem", key)):
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\nContent-Type: application/x-pem-file\r\n\r\n'
            f'{content}\r\n'.encode())
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as err:
        raise SystemExit(f"upload -> HTTP {err.code}: {err.read().decode()[:300]}")


row = sqlite3.connect(DB).execute(
    "select id, domain, domains_json, certificate, key, expires_at, status "
    "from certificates where id=?", (cerulean_id,)).fetchone()
if not row:
    raise SystemExit(f"no cerulean certificate {cerulean_id}")
cert_id, domain, domains_json, certificate, key, expires_at, status = row
if status != "issued" or not certificate:
    raise SystemExit(f"cerulean certificate {cert_id} is {status}, nothing to upload")
print(f"cerulean cert {cert_id} {domain} expires {expires_at}")

npm = env.get("NPM_PUBLIC_API_URL", "http://127.0.0.1:81").rstrip("/")
jwt = call(npm + "/api/tokens", "POST",
           {"identity": env["NPM_ADMIN_EMAIL"], "secret": env["NPM_ADMIN_PASSWORD"]})["token"]
auth = {"Authorization": "Bearer " + jwt}

nice_name = f"cerulean-{domain}"
certificates = call(npm + "/api/nginx/certificates", headers=auth)
existing = [c for c in certificates if (c.get("nice_name") or "") in (nice_name, domain)]
if existing:
    npm_cert_id = existing[0]["id"]
    print(f"reusing NPM certificate {npm_cert_id}")
else:
    created = call(npm + "/api/nginx/certificates", "POST",
                   {"provider": "other", "nice_name": nice_name,
                    "domain_names": json.loads(domains_json or json.dumps([domain])),
                    "meta": {}}, auth)
    npm_cert_id = created["id"]
    print(f"created NPM certificate {npm_cert_id}")

upload_pem(f"{npm}/api/nginx/certificates/{npm_cert_id}/upload", certificate, key, auth)

for cert in call(npm + "/api/nginx/certificates", headers=auth):
    if cert["id"] == npm_cert_id:
        print(f"npm cert {npm_cert_id}: provider={cert.get('provider')} "
              f"expires={cert.get('expires_on')} names={cert.get('domain_names')}")
