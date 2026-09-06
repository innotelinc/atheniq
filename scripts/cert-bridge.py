#!/usr/bin/env python3
"""AthenIQ → Signara certificate bridge.

Watches the Open edX LMS for newly issued course certificates and pushes each
one through Signara's signing workflow, producing a signed certificate PDF that
the learner can view and verify in the Signara portal (the stack's sole
DocumentOps surface).

Flow per certificate (mirrors docs/Integrations.md §Signara):
  1. read the completion record from the LMS DB (certificates_* tables),
  2. render a certificate PDF (pure Python, no dependencies),
  3. upload it to Signara as a document,
  4. create a signing request with the issuer/signatory as the signer,
  5. sign it via the signer's public token,
  6. record the outcome in a ledger table so re-runs are idempotent.

Usage:
    python3 scripts/cert-bridge.py --once            # one pass over new certs
    python3 scripts/cert-bridge.py --watch           # poll forever (default)
    python3 scripts/cert-bridge.py --dry-run         # show what would sync
    python3 scripts/cert-bridge.py --status          # ledger health (MySQL only)
    python3 scripts/cert-bridge.py --interval 120    # watch interval seconds

PARTIAL rows (the document was uploaded but the signing request or signature
failed) are auto-resumed on every pass: the bridge re-fetches the request,
signs it when pending, and marks the ledger SIGNED — so a transient Signara
error never parks a certificate permanently.

Configuration comes from the repo .env (SIGNARA_API_URL / SIGNARA_API_KEY,
CERT_SIGNER_*). The LMS MySQL root password is resolved via Tutor
(`tutor config printvalue MYSQL_ROOT_PASSWORD`), which requires the operator
user to be able to `sudo -u tutor`. Set LMS_DB_PASSWORD to skip that step.

Run it on the group-1 (Primary) host next to Tutor and Signara, e.g. under a
simple cron or a `--watch` systemd unit.
"""
import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

DEFAULTS = {
    "SIGNARA_API_URL": "https://api.signara.innotel.us",
    "CERT_SIGNER_NAME": "D. Hunter",
    "CERT_SIGNER_EMAIL": "dhunter@innotel.us",
    "CERT_SIGNER_TITLE": "Founder - Innotel",
    "LMS_MYSQL_CONTAINER": "tutor_local-mysql-1",
}


def load_dotenv(path):
    env = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'\"")
                env[key] = val
    except FileNotFoundError:
        pass
    return env


def cfg(name):
    if name in os.environ and os.environ[name]:
        return os.environ[name]
    return DEFAULTS.get(name, "")


# --------------------------------------------------------------------------
# LMS database access (via the Tutor MySQL container)
# --------------------------------------------------------------------------


def mysql_password():
    if os.environ.get("LMS_DB_PASSWORD"):
        return os.environ["LMS_DB_PASSWORD"]
    # Tutor-managed install: resolve from tutor config as the tutor user.
    try:
        out = subprocess.run(
            ["sudo", "-u", "tutor", "-H", "bash", "-c",
             "cd ~ && . tutor-venv/bin/activate && tutor config printvalue MYSQL_ROOT_PASSWORD"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    # Last resort: read it from the running container's environment.
    try:
        out = subprocess.run(
            ["docker", "exec", cfg("LMS_MYSQL_CONTAINER"), "sh", "-c", "printenv MYSQL_ROOT_PASSWORD"],
            capture_output=True, text=True, timeout=20,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    raise SystemExit("Cannot resolve the LMS MySQL root password — set LMS_DB_PASSWORD "
                     "or make `sudo -u tutor` work.")


def mysql(sql):
    pw = mysql_password()
    cmd = ["docker", "exec", cfg("LMS_MYSQL_CONTAINER"), "sh", "-c",
           f"mysql -uroot -p{pw} openedx -N -B -e {sh_quote(sql)} 2>/dev/null"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"mysql failed: {out.stderr[:400] or out.stdout[:400]}")
    return out.stdout


def sh_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


LEDGER_DDL = (
    "CREATE TABLE IF NOT EXISTS atheniq_cert_sync ("
    "cert_id INT PRIMARY KEY,"
    "course_id VARCHAR(255),"
    "learner VARCHAR(255),"
    "learner_email VARCHAR(255),"
    "grade VARCHAR(16),"
    "signara_document_id VARCHAR(64),"
    "signara_request_id VARCHAR(64),"
    "status VARCHAR(32),"
    "submitted_at DATETIME(6)"
    ") ENGINE=InnoDB"
)

CERT_QUERY = (
    "SELECT cc.id, cc.course_id, cc.verify_uuid, cc.grade, cc.created_date, "
    "       au.username, au.email, ap.name AS learner_name, "
    "       cc.name AS cert_name, "
    "       co.display_name AS course_name, co.org "
    "FROM certificates_generatedcertificate cc "
    "JOIN auth_user au ON au.id = cc.user_id "
    "LEFT JOIN auth_userprofile ap ON ap.user_id = cc.user_id "
    "LEFT JOIN course_overviews_courseoverview co ON co.id = cc.course_id "
    "WHERE cc.status = 'downloadable' "
    "  AND cc.id NOT IN (SELECT cert_id FROM atheniq_cert_sync) "
    "ORDER BY cc.id"
)


def pending_certs():
    mysql(LEDGER_DDL)
    rows = mysql(CERT_QUERY)
    certs = []
    for line in rows.splitlines():
        if not line.strip():
            continue
        f = line.split("\t")
        if len(f) < 10:
            continue
        certs.append({
            "id": int(f[0]), "course_id": f[1], "verify_uuid": f[2],
            "grade": f[3], "created_date": f[4], "username": f[5],
            "email": f[6], "learner_name": f[7], "cert_name": f[8],
            "course_name": f[9], "org": f[10],
        })
    return certs


def learner_display_name(cert):
    """Best available display name: profile name, then the name recorded on the
    certificate itself (set at award time), then the username as a last resort."""
    for key in ("learner_name", "cert_name"):
        val = (cert.get(key) or "").strip()
        if val:
            return val
    return (cert.get("username") or "").strip()


def ledger_insert(row):
    cert_id = row.get("cert_id") or row["id"]
    course_id = row.get("course_id") or ""
    learner = row.get("learner") or learner_display_name(row) or row.get("username") or ""
    email = row.get("learner_email") or row.get("email") or ""
    grade = row.get("grade") or ""
    sql = (
        "INSERT INTO atheniq_cert_sync (cert_id, course_id, learner, learner_email, grade, "
        "signara_document_id, signara_request_id, status, submitted_at) VALUES ("
        f"{cert_id}, {sh_quote(str(course_id))}, "
        f"{sh_quote(str(learner))}, {sh_quote(str(email))}, "
        f"{sh_quote(str(grade))}, "
        f"{sh_quote(row.get('doc_id') or '')}, {sh_quote(row.get('req_id') or '')}, "
        f"{sh_quote(row.get('status', 'SUBMITTED'))}, NOW(6))"
    )
    mysql(sql)


# --------------------------------------------------------------------------
# ledger helpers — update rows and read PARTIAL work for resume
# --------------------------------------------------------------------------


PARTIAL_QUERY = (
    "SELECT cert_id, course_id, learner, learner_email, grade, "
    "signara_document_id, signara_request_id "
    "FROM atheniq_cert_sync WHERE status = 'PARTIAL' ORDER BY cert_id"
)


def ledger_update(cert_id, doc_id, req_id, status):
    """Upsert a ledger row's Signara outcome, preserving the original row's
    course/learner columns (used when resuming PARTIAL submissions)."""
    sql = (
        "INSERT INTO atheniq_cert_sync (cert_id, course_id, learner, learner_email, grade, "
        "signara_document_id, signara_request_id, status, submitted_at) VALUES ("
        f"{cert_id}, '', '', '', '', {sh_quote(doc_id or '')}, {sh_quote(req_id or '')}, "
        f"{sh_quote(status)}, NOW(6)) AS new "
        "ON DUPLICATE KEY UPDATE signara_document_id = new.signara_document_id, "
        "signara_request_id = new.signara_request_id, status = new.status, "
        "submitted_at = NOW(6)"
    )
    mysql(sql)


def ledger_partials():
    rows = mysql(PARTIAL_QUERY)
    partials = []
    for line in rows.splitlines():
        if not line.strip():
            continue
        f = line.split("\t")
        if len(f) < 7:
            continue
        partials.append({
            "id": int(f[0]), "course_id": f[1], "learner": f[2],
            "learner_email": f[3], "grade": f[4],
            "doc_id": f[5].strip(), "req_id": f[6].strip(),
        })
    return partials


def resume_partials(signara, dry_run):
    """Finish Signara legs that previously failed midway (upload landed, but
    the request was never created, never got a signer token, or the signature
    call failed). Returns how many rows reached SIGNED."""
    mysql(LEDGER_DDL)
    partials = ledger_partials()
    if not partials:
        return 0
    if dry_run:
        print(f"{len(partials)} PARTIAL submission(s) would be resumed:")
        for c in partials:
            print(f"  [{c['id']}] {c['learner'] or c['learner_email']} — {c['course_id']} "
                  f"(doc {c['doc_id'][:8] or '-'}…, req {c['req_id'][:8] or '-'}…)")
        return 0

    resumed = 0
    print(f"{len(partials)} PARTIAL submission(s) to resume.")
    for c in partials:
        doc_id, req_id = c["doc_id"], c["req_id"]
        print(f"  [{c['id']}] {c['learner'] or c['learner_email']} — {c['course_id']} "
              f"(doc {doc_id[:8] or '-'}…, req {req_id[:8] or '-'}…)")

        if req_id:
            st, rq = signara.get_request(req_id)
            if st >= 300:
                print(f"    !! request fetch failed ({st}): {str(rq)[:200]} — retrying next pass")
                continue
            request_status = (rq.get("status") or "").upper()
            signer = (rq.get("signers") or [{}])[0]
            if request_status == "COMPLETED" or (signer.get("status") or "").upper() == "SIGNED":
                ledger_update(c["id"], doc_id, req_id, "SIGNED")
                resumed += 1
                print("    -> already signed; ledger marked SIGNED")
                continue
            token = signer.get("token")
            if not token:
                print("    !! no signer token on fetch — retrying next pass")
                continue
            st, sg = signara.sign(token, cfg("CERT_SIGNER_NAME"))
            if st == 409:
                ledger_update(c["id"], doc_id, req_id, "SIGNED")
                resumed += 1
                print("    -> 409 already signed; ledger marked SIGNED")
            elif st < 300:
                ledger_update(c["id"], doc_id, req_id, "SIGNED")
                resumed += 1
                print(f"    -> signed (http {st}); ledger marked SIGNED")
            else:
                print(f"    !! sign failed ({st}): {str(sg)[:200]} — retrying next pass")
            continue

        if doc_id:
            title = f"{c['course_id']} - Certificate of Completion ({c['learner'] or c['id']})"
            st, rq = signara.create_request(doc_id, title, "Auto-signed by the AthenIQ cert bridge (resume).")
            if st >= 300:
                print(f"    !! request re-create failed ({st}): {str(rq)[:200]} — retrying next pass")
                continue
            new_req_id = rq.get("id")
            signer = (rq.get("signers") or [{}])[0]
            token = signer.get("token")
            if not token:
                _, rq2 = signara.get_request(new_req_id)
                signer = (rq2.get("signers") or [{}])[0]
                token = signer.get("token")
            if not token:
                print(f"    !! no signer token for new request {new_req_id[:8]}… — retrying next pass")
                continue
            st, sg = signara.sign(token, cfg("CERT_SIGNER_NAME"))
            status = "SIGNED" if st < 300 else "PARTIAL"
            print(f"    -> request {new_req_id[:8]}… sign http {st}: {status}")
            ledger_update(c["id"], doc_id, new_req_id, status)
            if status == "SIGNED":
                resumed += 1
            continue

        print("    !! nothing to resume (no document/request id) — retrying next pass")
    return resumed


# --------------------------------------------------------------------------
# certificate PDF rendering (pure Python, Helvetica)
# --------------------------------------------------------------------------


def render_cert_pdf(cert, signer_name, signer_title, out_path):
    org = cert["org"] or "Innotel"
    platform = "ATHENIQ LEARNING PLATFORM"
    learner = learner_display_name(cert)
    course = cert["course_name"] or cert["course_id"]
    grade = cert["grade"]
    try:
        issued = datetime.strptime(cert["created_date"][:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        issued = datetime.now()
    date_str = issued.strftime("%B %d, %Y")

    W, H = 792, 612  # letter landscape, origin bottom-left

    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Absolute placement per line (Tm sets the text matrix; no accumulation).
    # y_from_top is measured from the top edge; PDF y runs from the bottom.
    def text_line(font, size, x, y_from_top, s):
        y = H - y_from_top
        return f"/{font} {size} Tf 0.15 0.15 0.2 rg 1 0 0 1 {x} {y} Tm ({esc(s)}) Tj"

    s = ["BT"]
    s.append("0.8 w 0.2 0.2 0.25 RG 20 20 %d %d re S" % (W - 40, H - 40))
    s.append("1.5 w 0.15 0.15 0.2 RG 26 26 %d %d re S" % (W - 52, H - 52))
    lines = [
        (org.upper(), "F2", 26, 40, 96),
        (platform, "F1", 11, 40, 122),
        ("Certificate of Completion", "F2", 34, 40, 210),
        ("This certifies that", "F1", 15, 0, 300),
        (learner, "F2", 24, 0, 332),
        ("has successfully completed the course", "F1", 15, 0, 392),
        (course, "F2", 18, 0, 424),
        (f"with a final grade of {grade}, and is awarded this certificate", "F1", 13, 0, 480),
        ("Issued: " + date_str, "F1", 13, 0, 560),
        ("Certificate ID: " + cert["verify_uuid"], "F1", 10, 0, 578),
    ]
    for t, font, size, x, y in lines:
        cx = x if x else max(20, (W - int(size * len(t) * 0.55)) // 2)
        s.append(text_line(font, size, cx, y, t))
    # signature block (bottom-right)
    s.append("0.5 w 0.3 0.3 0.3 RG 512 96 200 0 re S")
    s.append("/F1 12 Tf 0.3 0.3 0.3 rg 1 0 0 1 512 86 Tm (%s) Tj" % esc(signer_name + " - " + signer_title))
    s.append("/F1 9 Tf 0.5 0.5 0.5 rg 1 0 0 1 512 72 Tm (Authorized Signatory) Tj")
    s.append("ET")
    stream = "\n".join(s)

    content = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
        "/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>" % (W, H),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    content.append("<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    pdf = "%PDF-1.4\n"
    offsets = []
    for c in content:
        offsets.append(len(pdf))
        pdf += c + "\n"
    xref = len(pdf)
    pdf += "xref\n0 %d\n" % (len(content) + 1)
    pdf += "0000000000 65535 f \n"
    for o in offsets:
        pdf += "%010d 00000 n \n" % o
    pdf += "trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(content) + 1, xref)
    with open(out_path, "wb") as fh:
        fh.write(pdf.encode("latin-1"))
    return out_path


# --------------------------------------------------------------------------
# Signara API client (machine auth via X-API-Key)
# --------------------------------------------------------------------------


class Signara:
    def __init__(self, base, api_key, verify=True):
        self.base = base.rstrip("/")
        self.api_key = api_key
        ctx = ssl.create_default_context()
        if not verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.ctx = ctx

    def _open(self, method, path, body=None, ctype="application/json", timeout=90):
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
        headers = {"X-API-Key": self.api_key}
        if ctype:
            headers["Content-Type"] = ctype
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout, context=self.ctx)
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else {}
            except ValueError:
                return e.code, {"error": raw.decode("utf-8", "replace")[:300]}

    def upload_document(self, title, description, pdf_path):
        boundary = "----atheniq" + uuid.uuid4().hex
        blob = open(pdf_path, "rb").read()
        parts = []
        def field(k, v):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        field("title", title)
        field("description", description)
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                     f"filename=\"{os.path.basename(pdf_path)}\"\r\nContent-Type: application/pdf\r\n\r\n".encode())
        parts.append(blob)
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        return self._open("POST", "/api/v1/documents/upload", body=b"".join(parts),
                          ctype=f"multipart/form-data; boundary={boundary}", timeout=120)

    def create_request(self, doc_id, title, message):
        payload = {
            "documentId": doc_id,
            "title": title,
            "message": message,
            "mode": "SEQUENTIAL",
            "sendInvites": False,
            "signers": [{
                "email": cfg("CERT_SIGNER_EMAIL"),
                "name": cfg("CERT_SIGNER_NAME"),
                "role": "SIGNER",
                "orderIndex": 0,
            }],
        }
        return self._open("POST", "/api/v1/signatures/requests", payload)

    def get_request(self, req_id):
        return self._open("GET", f"/api/v1/signatures/requests/{req_id}")

    def sign(self, signer_token, typed_signature):
        return self._open("POST", f"/api/v1/signatures/public/{signer_token}/sign",
                          {"type": "TYPED", "signatureData": typed_signature})


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def sync_once(signara, dry_run, verbose):
    resumed = resume_partials(signara, dry_run)
    certs = pending_certs()
    if not certs:
        if not resumed:
            print("No new downloadable certificates to sync.")
        return 0
    print(f"{len(certs)} certificate(s) awaiting Signara signing.")
    for cert in certs:
        learner = learner_display_name(cert)
        title = f"{cert['course_name'] or cert['course_id']} - Certificate of Completion ({learner})"
        desc = (f"Open edX course completion certificate - {cert['course_id']} "
                f"(grade {cert['grade']}), auto-synced by the AthenIQ cert bridge.")
        print(f"  [{cert['id']}] {learner} <{cert['email']}> — {cert['course_id']} grade {cert['grade']}")
        if dry_run:
            continue
        pdf = os.path.join("/tmp", f"atheniq-cert-{cert['id']}-{uuid.uuid4().hex[:8]}.pdf")
        try:
            render_cert_pdf(cert, cfg("CERT_SIGNER_NAME"), cfg("CERT_SIGNER_TITLE"), pdf)
            st, doc = signara.upload_document(title, desc, pdf)
            if st >= 300:
                print(f"    !! upload failed ({st}): {str(doc)[:200]}")
                continue
            doc_id = doc.get("id")
            st, rq = signara.create_request(doc_id, title, desc)
            if st >= 300:
                print(f"    !! request failed ({st}): {str(rq)[:200]}")
                ledger_insert({**cert, "doc_id": doc_id, "req_id": "", "status": "PARTIAL"})
                continue
            req_id = rq.get("id")
            signer = (rq.get("signers") or [{}])[0]
            token = signer.get("token")
            if not token:
                # token is often returned only at creation; fall back to a re-fetch
                _, rq2 = signara.get_request(req_id)
                signer = (rq2.get("signers") or [{}])[0]
                token = signer.get("token")
            if not token:
                print(f"    !! no signer token for request {req_id}")
                ledger_insert({**cert, "doc_id": doc_id, "req_id": req_id, "status": "PARTIAL"})
                continue
            st, sg = signara.sign(token, cfg("CERT_SIGNER_NAME"))
            status = "SIGNED" if st < 300 else "PARTIAL"
            print(f"    -> document {doc_id[:8]}… request {req_id[:8]}… sign http {st}: {status}")
            ledger_insert({**cert, "doc_id": doc_id, "req_id": req_id, "status": status})
        finally:
            try:
                os.remove(pdf)
            except OSError:
                pass
    return 1


def status_report():
    """Print a ledger health summary (MySQL only — no Signara calls)."""
    mysql(LEDGER_DDL)
    pending = len(pending_certs())
    rows = mysql("SELECT status, COUNT(*) FROM atheniq_cert_sync GROUP BY status ORDER BY status")
    counts = {}
    for line in rows.splitlines():
        if not line.strip():
            continue
        f = line.split("\t")
        if len(f) >= 2:
            counts[f[0]] = int(f[1])
    total = sum(counts.values())
    print("AthenIQ cert bridge — ledger status")
    print(f"  ledger rows           : {total}")
    for st in ("SUBMITTED", "PARTIAL", "SIGNED"):
        print(f"  {st:<12}: {counts.get(st, 0)}")
    for other in sorted(set(counts) - {"SUBMITTED", "PARTIAL", "SIGNED"}):
        print(f"  {other:<12}: {counts[other]}")
    print(f"  awaiting first sync   : {pending}  (downloadable, unledgered)")
    if counts.get("PARTIAL"):
        print("  note: PARTIAL rows are auto-resumed on the next sync pass.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true", help="single pass, then exit")
    ap.add_argument("--watch", action="store_true", help="poll forever (default when neither flag given)")
    ap.add_argument("--dry-run", action="store_true", help="list pending certs without calling Signara")
    ap.add_argument("--status", action="store_true", help="print ledger health and exit (no Signara calls)")
    ap.add_argument("--interval", type=int, default=120, help="watch poll interval in seconds (default 120)")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification (demo hosts)")
    args = ap.parse_args()

    env = load_dotenv(os.path.join(REPO, ".env"))
    for k, v in env.items():
        os.environ.setdefault(k, v)

    if args.status:
        status_report()
        return

    base = cfg("SIGNARA_API_URL")
    key = cfg("SIGNARA_API_KEY")
    if not key:
        raise SystemExit("SIGNARA_API_KEY is not set — see .env.example and docs/Deployment.md Stage 7.")
    signara = Signara(base, key, verify=not args.insecure)

    if args.dry_run:
        sync_once(signara, dry_run=True, verbose=True)
        return

    if args.once:
        sync_once(signara, dry_run=False, verbose=True)
        return

    print(f"Watching for new certificates every {args.interval}s (Ctrl-C to stop).")
    while True:
        try:
            sync_once(signara, dry_run=False, verbose=True)
        except Exception as e:
            print(f"pass failed: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
