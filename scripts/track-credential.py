#!/usr/bin/env python3
"""AthenIQ — track-level credential issuance.

A workforce track carries its own credential (`credential` in
config/workforce-tracks.json). A course certificate is issued per passing grade;
the **track** credential is issued once a learner has passed *every* course in the
track — the "I finished the ladder" document, signed through Signara like any
other (see scripts/cert-bridge.py, whose Signara client and PDF renderer this
reuses).

    python3 scripts/track-credential.py --learner <username|email>
    python3 scripts/track-credential.py --earned course-v1:A+B+C,course-v1:...
    python3 scripts/track-credential.py --learner <u> --sign     # push to Signara
    python3 scripts/track-credential.py --status

Detection is pure and testable: give it the catalog and the set of courses the
learner has completed, and it returns the tracks that are now complete. The
`--sign` path renders a track-completion PDF and records the outcome in
`atheniq_track_credential`, keyed on (track, learner), so re-runs are idempotent.
"""
import argparse
import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(REPO, "config", "workforce-tracks.json")


def _load_bridge():
    """Load scripts/cert-bridge.py (hyphenated, not importable by name) so the
    two tools share one Signara client, PDF renderer, and MySQL path."""
    path = os.path.join(REPO, "scripts", "cert-bridge.py")
    spec = importlib.util.spec_from_file_location("atheniq_cert_bridge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BRIDGE = _load_bridge()


# --------------------------------------------------------------------------
# detection (pure)
# --------------------------------------------------------------------------

def completed_tracks(doc, earned):
    """Tracks whose every course is in `earned`."""
    earned = set(earned)
    done = []
    for track in doc.get("tracks", []):
        if not isinstance(track, dict):
            continue
        courses = [c for c in (track.get("courses") or []) if isinstance(c, str)]
        if courses and all(c in earned for c in courses):
            done.append(track)
    return done


def missing_courses(track, earned):
    earned = set(earned)
    return [c for c in (track.get("courses") or []) if c not in earned]


def credential_for(track):
    """The track's credential when it is one that gets signed, else None."""
    cred = track.get("credential") or {}
    if cred.get("type") in ("certificate", "badge"):
        return cred
    return None


# --------------------------------------------------------------------------
# LMS read + Signara write (operator paths)
# --------------------------------------------------------------------------

EARNED_QUERY = (
    "SELECT DISTINCT cc.course_id FROM certificates_generatedcertificate cc "
    "JOIN auth_user au ON au.id = cc.user_id "
    "WHERE cc.status = 'downloadable' AND (au.username = {who} OR au.email = {who})"
)

IDENTITY_QUERY = (
    "SELECT au.username, au.email, COALESCE(ap.name, '') FROM auth_user au "
    "LEFT JOIN auth_userprofile ap ON ap.user_id = au.id "
    "WHERE au.username = {who} OR au.email = {who} LIMIT 1"
)

LEDGER_DDL = (
    "CREATE TABLE IF NOT EXISTS atheniq_track_credential ("
    "track_id VARCHAR(64) NOT NULL,"
    "learner VARCHAR(255) NOT NULL,"
    "learner_email VARCHAR(255),"
    "courses VARCHAR(1024),"
    "verify_uuid VARCHAR(64),"
    "signara_document_id VARCHAR(64),"
    "signara_request_id VARCHAR(64),"
    "status VARCHAR(32),"
    "submitted_at DATETIME(6),"
    "PRIMARY KEY (track_id, learner)"
    ") ENGINE=InnoDB"
)


def earned_for(identifier):
    """Course keys the learner holds a downloadable certificate for."""
    q = EARNED_QUERY.format(who=BRIDGE.sh_quote(identifier))
    rows = BRIDGE.mysql(q)
    return [line.strip() for line in rows.splitlines() if line.strip()]


def identity_for(identifier):
    q = IDENTITY_QUERY.format(who=BRIDGE.sh_quote(identifier))
    rows = BRIDGE.mysql(q)
    for line in rows.splitlines():
        if not line.strip():
            continue
        f = line.split("\t")
        return {"username": f[0], "email": f[1], "name": f[2] if len(f) > 2 else ""}
    return {"username": identifier, "email": "", "name": ""}


def ledger_status(track_id, learner):
    BRIDGE.mysql(LEDGER_DDL)
    q = ("SELECT status FROM atheniq_track_credential "
         f"WHERE track_id = {BRIDGE.sh_quote(track_id)} "
         f"AND learner = {BRIDGE.sh_quote(learner)}")
    rows = BRIDGE.mysql(q)
    return rows.strip() or None


def ledger_upsert(track, learner, email, courses, uuid_, doc_id, req_id, status):
    BRIDGE.mysql(LEDGER_DDL)
    sql = (
        "INSERT INTO atheniq_track_credential (track_id, learner, learner_email, "
        "courses, verify_uuid, signara_document_id, signara_request_id, status, "
        "submitted_at) VALUES ("
        f"{BRIDGE.sh_quote(track)}, {BRIDGE.sh_quote(learner)}, "
        f"{BRIDGE.sh_quote(email)}, {BRIDGE.sh_quote(','.join(courses))}, "
        f"{BRIDGE.sh_quote(uuid_)}, {BRIDGE.sh_quote(doc_id or '')}, "
        f"{BRIDGE.sh_quote(req_id or '')}, {BRIDGE.sh_quote(status)}, NOW(6)) AS new "
        "ON DUPLICATE KEY UPDATE courses = new.courses, verify_uuid = new.verify_uuid, "
        "signara_document_id = new.signara_document_id, "
        "signara_request_id = new.signara_request_id, status = new.status, "
        "submitted_at = NOW(6)"
    )
    BRIDGE.mysql(sql)


def issue(signara, track, learner, dry_run):
    """Push one track credential through Signara; returns the final status."""
    cred = credential_for(track)
    if cred is None:
        print(f"  {track['id']}: no signed credential declared — skipped.")
        return "SKIPPED"
    who = learner["username"]
    existing = ledger_status(track["id"], who)
    if existing == "SIGNED":
        print(f"  {track['id']}: already SIGNED — skipped.")
        return "SIGNED"

    uuid_ = uuid.uuid4().hex
    title = f"{cred.get('title') or track.get('title')} ({learner['name'] or who})"
    desc = (f"AthenIQ track completion credential — {track.get('title')} "
            f"({', '.join(track.get('courses', []))}).")
    print(f"  {track['id']}: {learner['name'] or who} <{learner['email']}> — {title}")
    if dry_run:
        return "DRY-RUN"

    cert = {
        "org": "Innotel",
        "course_name": cred.get("title") or track.get("title"),
        "course_id": track["id"],
        "grade": "Pass",
        "created_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "verify_uuid": uuid_,
        "username": who,
        "email": learner["email"],
        "learner_name": learner["name"],
    }
    pdf = os.path.join("/tmp", f"atheniq-track-{track['id']}-{uuid_[:8]}.pdf")
    try:
        BRIDGE.render_cert_pdf(cert, BRIDGE.cfg("CERT_SIGNER_NAME"),
                               BRIDGE.cfg("CERT_SIGNER_TITLE"), pdf)
        st, doc = signara.upload_document(title, desc, pdf)
        if st >= 300:
            print(f"    !! upload failed ({st}): {str(doc)[:200]}")
            return "FAILED"
        doc_id = doc.get("id")
        st, rq = signara.create_request(doc_id, title, desc)
        if st >= 300:
            print(f"    !! request failed ({st}): {str(rq)[:200]}")
            ledger_upsert(track["id"], who, learner["email"], track["courses"],
                          uuid_, doc_id, "", "PARTIAL")
            return "PARTIAL"
        req_id = rq.get("id")
        signer = (rq.get("signers") or [{}])[0]
        token = signer.get("token")
        if not token:
            _, rq2 = signara.get_request(req_id)
            token = ((rq2.get("signers") or [{}])[0]).get("token")
        if not token:
            print(f"    !! no signer token for request {req_id}")
            ledger_upsert(track["id"], who, learner["email"], track["courses"],
                          uuid_, doc_id, req_id, "PARTIAL")
            return "PARTIAL"
        st, _ = signara.sign(token, BRIDGE.cfg("CERT_SIGNER_NAME"))
        status = "SIGNED" if st < 300 else "PARTIAL"
        print(f"    -> document {str(doc_id)[:8]}… request {str(req_id)[:8]}… "
              f"sign http {st}: {status}")
        ledger_upsert(track["id"], who, learner["email"], track["courses"],
                      uuid_, doc_id, req_id, status)
        return status
    finally:
        try:
            os.remove(pdf)
        except OSError:
            pass


def status_report():
    BRIDGE.mysql(LEDGER_DDL)
    rows = BRIDGE.mysql("SELECT status, COUNT(*) FROM atheniq_track_credential "
                        "GROUP BY status ORDER BY status")
    counts = {}
    for line in rows.splitlines():
        f = line.split("\t")
        if len(f) >= 2:
            counts[f[0]] = int(f[1])
    print("AthenIQ track credentials — ledger status")
    print(f"  ledger rows   : {sum(counts.values())}")
    for st in ("SIGNED", "PARTIAL", "FAILED"):
        print(f"  {st:<8}: {counts.get(st, 0)}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", default=DEFAULT_FILE, help="catalog to read")
    ap.add_argument("--learner", help="LMS username or email to look up")
    ap.add_argument("--earned", help="comma-separated course keys (offline/testing)")
    ap.add_argument("--sign", action="store_true", help="push completed tracks to Signara")
    ap.add_argument("--dry-run", action="store_true", help="show what --sign would do")
    ap.add_argument("--status", action="store_true", help="print ledger health and exit")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification")
    args = ap.parse_args()

    env = BRIDGE.load_dotenv(os.path.join(REPO, ".env"))
    for k, v in env.items():
        os.environ.setdefault(k, v)

    if args.status:
        status_report()
        return

    try:
        doc = json.load(open(args.file))
    except FileNotFoundError:
        raise SystemExit(f"catalog not found: {args.file}")

    if args.earned is not None:
        earned = [c.strip() for c in args.earned.split(",") if c.strip()]
        learner = {"username": args.learner or "offline", "email": "", "name": ""}
    elif args.learner:
        earned = earned_for(args.learner)
        learner = identity_for(args.learner)
    else:
        raise SystemExit("pass --learner <username|email> or --earned <keys>")

    done = completed_tracks(doc, earned)
    print(f"{learner['username']}: {len(earned)} course(s) completed, "
          f"{len(done)} track(s) complete.")
    if not done:
        for track in doc.get("tracks", []):
            missing = missing_courses(track, earned)
            if missing and len(missing) < len(track.get("courses") or []):
                print(f"  {track['id']}: still needs {', '.join(missing)}")
        return

    if not args.sign:
        for track in done:
            cred = credential_for(track)
            label = (cred or {}).get("title", track.get("title"))
            print(f"  complete: {track['id']} -> {label}")
        return

    key = BRIDGE.cfg("SIGNARA_API_KEY")
    if not key:
        raise SystemExit("SIGNARA_API_KEY is not set — see .env.example.")
    signara = BRIDGE.Signara(BRIDGE.cfg("SIGNARA_API_URL"), key, verify=not args.insecure)
    for track in done:
        issue(signara, track, learner, args.dry_run)


if __name__ == "__main__":
    main()
