#!/usr/bin/env python3
"""AthenIQ — grant or revoke paid-course access from a Magnate entitlement.

This closes the revenue loop: Magnate decides *whether* a learner has paid, and
this script turns that decision into an Open edX enrollment. It never prices or
charges anything — it reads the plan entitlement Magnate owns (see
scripts/magnate-entitlements.py) and reflects it in the LMS.

Flow:
  1. resolve the learner's LMS user id (auth_user, by username or email),
  2. ask Magnate `GET /api/entitlements?plan=<plan>&user=<learner>` (unless
     --force or --revoke),
  3. upsert the `student_courseenrollment` row (mode `verified` by default) to
     active on grant, or inactive on --revoke,
  4. ledger the outcome in `atheniq_paid_enrollment` so re-runs are idempotent.

The LMS is reached through the Tutor MySQL container exactly as
`scripts/cert-bridge.py` reaches it, so no Django process has to be booted.
Direct enrollment writes bypass Open edX signals (as the cert bridge's direct
certificate writes do); this is an operator tool for paid access, not a general
enrollment API. `--dry-run` prints the SQL instead of running it.

Usage:
    python3 scripts/paid-enrollment.py --user learner@x.edu --course course-v1:Org+C+R
    python3 scripts/paid-enrollment.py --user learner --course <key> --revoke
    python3 scripts/paid-enrollment.py --user learner --course <key> --force   # skip the entitlement check
    python3 scripts/paid-enrollment.py --user learner --course <key> --dry-run
    python3 scripts/paid-enrollment.py --status

Configuration (.env): MAGNATE_API_URL / MAGNATE_ENTITLEMENTS_TOKEN /
MAGNATE_PAID_PLAN, and LMS_MYSQL_CONTAINER (default tutor_local-mysql-1). The
LMS MySQL root password is resolved via Tutor (`sudo -u tutor`); set
LMS_DB_PASSWORD to skip that.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "MAGNATE_API_URL": "https://app.magnate.innotel.us",
    "MAGNATE_PAID_PLAN": "premium",
    "LMS_MYSQL_CONTAINER": "tutor_local-mysql-1",
    "PAID_ENROLLMENT_MODE": "verified",
}

LEDGER_DDL = (
    "CREATE TABLE IF NOT EXISTS atheniq_paid_enrollment ("
    "user_id INT NOT NULL,"
    "username VARCHAR(255),"
    "course_id VARCHAR(255) NOT NULL,"
    "plan VARCHAR(64),"
    "mode VARCHAR(64),"
    "state VARCHAR(16),"
    "updated DATETIME(6),"
    "PRIMARY KEY (user_id, course_id)"
    ") ENGINE=InnoDB"
)


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
# pure helpers (unit-tested)
# --------------------------------------------------------------------------

def sh_quote(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def enrollment_sql(existing, user_id, course_key, mode, active):
    """Return the SQL that reflects `active` for one enrollment, as an UPDATE
    when a row exists and an INSERT otherwise (robust even if the schema carries
    no unique key on user_id/course_id)."""
    if existing:
        return (
            "UPDATE student_courseenrollment SET "
            f"is_active = {1 if active else 0}, mode = {sh_quote(mode)}, changed = NOW() "
            f"WHERE user_id = {int(user_id)} AND course_id = {sh_quote(course_key)}"
        )
    return (
        "INSERT INTO student_courseenrollment "
        "(user_id, course_id, created, is_active, mode, changed) VALUES "
        f"({int(user_id)}, {sh_quote(course_key)}, NOW(), {1 if active else 0}, "
        f"{sh_quote(mode)}, NOW())"
    )


def entitlement_allows(payload):
    """Interpret a Magnate entitlement response: True, False, or None (unknown —
    a missing/!200 response, which must never be read as permission)."""
    if not isinstance(payload, dict):
        return None
    value = payload.get("entitled")
    return value if value in (True, False) else None


# --------------------------------------------------------------------------
# Magnate
# --------------------------------------------------------------------------

def magnate_entitled(url, token, plan, user, insecure=False):
    params = urllib.parse.urlencode({"plan": plan, "user": user})
    req = urllib.request.Request(f"{url.rstrip('/')}/api/entitlements?{params}")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    ctx = None
    if insecure:
        import ssl
        ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        return entitlement_allows(body), body
    except urllib.error.HTTPError as e:
        try:
            return entitlement_allows(json.loads(e.read().decode("utf-8", "replace"))), {}
        except Exception:
            return None, {}
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach Magnate at {url}: {e.reason}")


# --------------------------------------------------------------------------
# LMS access (via the Tutor MySQL container), mirroring cert-bridge.py
# --------------------------------------------------------------------------

def mysql_password():
    if os.environ.get("LMS_DB_PASSWORD"):
        return os.environ["LMS_DB_PASSWORD"]
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


def resolve_user(identifier):
    rows = mysql(
        "SELECT id, username FROM auth_user WHERE "
        f"username = {sh_quote(identifier)} OR email = {sh_quote(identifier)} LIMIT 1"
    ).splitlines()
    if not rows or not rows[0].strip():
        raise SystemExit(f"no LMS user found for '{identifier}'")
    fields = rows[0].split("\t")
    return int(fields[0]), fields[1]


def enrollment_exists(user_id, course_key):
    rows = mysql(
        "SELECT id FROM student_courseenrollment WHERE "
        f"user_id = {int(user_id)} AND course_id = {sh_quote(course_key)} LIMIT 1"
    ).strip()
    return bool(rows)


def ledger_upsert(user_id, username, course_key, plan, mode, state):
    sql = (
        "INSERT INTO atheniq_paid_enrollment "
        "(user_id, username, course_id, plan, mode, state, updated) VALUES "
        f"({int(user_id)}, {sh_quote(username)}, {sh_quote(course_key)}, {sh_quote(plan)}, "
        f"{sh_quote(mode)}, {sh_quote(state)}, NOW(6)) AS new "
        "ON DUPLICATE KEY UPDATE plan = new.plan, mode = new.mode, "
        "username = new.username, state = new.state, updated = NOW(6)"
    )
    return mysql(sql)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def status_report():
    mysql(LEDGER_DDL)
    out = mysql("SELECT state, COUNT(*) FROM atheniq_paid_enrollment GROUP BY state").splitlines()
    counts = {}
    for line in out:
        if line.strip():
            f = line.split("\t")
            counts[f[0]] = int(f[1])
    print("AthenIQ paid-enrollment ledger")
    if not counts:
        print("  (empty — no grants or revocations recorded yet)")
        return
    for state in sorted(counts):
        print(f"  {state:<10}: {counts[state]}")
    active = mysql(
        "SELECT COUNT(*) FROM atheniq_paid_enrollment WHERE state = 'ACTIVE'"
    ).strip()
    print(f"  currently active paid enrollments: {active}")


def run(args):
    if args.status:
        status_report()
        return 0

    if not args.user or not args.course:
        raise SystemExit("--user and --course are required (or use --status)")

    user_id, username = resolve_user(args.user)
    mode = args.mode or cfg("PAID_ENROLLMENT_MODE", "verified")
    plan = cfg("MAGNATE_PAID_PLAN")

    # Revocation and --force never consult Magnate.
    if not args.revoke and not args.force:
        url = cfg("MAGNATE_API_URL")
        token = cfg("MAGNATE_ENTITLEMENTS_TOKEN")
        allowed, body = magnate_entitled(url, token, plan, args.user, args.insecure)
        reason = body.get("reason", "no-response")
        if allowed is not True:
            print(f"not entitled — plan={plan} user={args.user} reason={reason}")
            return 1
        print(f"entitled — plan={plan} user={args.user} reason={reason}")

    existing = enrollment_exists(user_id, args.course)
    active = not args.revoke
    sql = enrollment_sql(existing, user_id, args.course, mode, active)
    state = "REVOKED" if args.revoke else "ACTIVE"

    if args.dry_run:
        print(f"[dry-run] would {'revoke' if args.revoke else 'grant'} "
              f"{username} <-> {args.course} (mode {mode})")
        print(f"  {sql}")
        return 0

    mysql(LEDGER_DDL)
    mysql(sql)
    ledger_upsert(user_id, username, args.course, plan, mode, state)
    verb = "revoked" if args.revoke else "granted"
    print(f"{verb}: {username} <-> {args.course} (mode {mode}, state {state})")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", help="LMS username or email")
    ap.add_argument("--course", help="Open edX course key")
    ap.add_argument("--mode", help=f"enrollment mode (default {DEFAULTS['PAID_ENROLLMENT_MODE']})")
    ap.add_argument("--revoke", action="store_true", help="deactivate the enrollment")
    ap.add_argument("--force", action="store_true", help="skip the Magnate entitlement check")
    ap.add_argument("--dry-run", action="store_true", help="print the SQL without executing")
    ap.add_argument("--status", action="store_true", help="print the ledger and exit")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification to Magnate")
    args = ap.parse_args()

    env = load_dotenv(os.path.join(REPO, ".env"))
    for k, v in env.items():
        os.environ.setdefault(k, v)

    sys.exit(run(args))


if __name__ == "__main__":
    main()
