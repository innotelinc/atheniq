#!/usr/bin/env python3
"""AthenIQ — reconcile Magnate entitlements into Authentik `paid_users`.

Magnate is the source of truth for *billing*; Authentik is the source of truth
for *identity and group membership*. This reconciler closes the gap between
them for AthenIQ's audience: for every active learner in the `learners` group,
it asks Magnate whether the paid-course plan is entitled to them, and adds or
removes the `paid_users` group membership to match.

It is deliberately idempotent and safe to run on a timer: a member whose
entitlement is unchanged is left alone, and an entitlement it could not
determine (Magnate unreachable, unknown user) changes nothing — an outage must
never revoke access.

Why a reconciler when Magnate already grants the group on checkout: the grant
is event-driven. This is the convergence pass that heals a missed webhook, a
restored database, or a plan change made directly in Magnate.

Usage:
    python3 scripts/entitlement-sync.py --status        # counts, no writes
    python3 scripts/entitlement-sync.py --dry-run       # print planned changes
    python3 scripts/entitlement-sync.py                 # apply (the timer's call)
    python3 scripts/entitlement-sync.py --user learner  # reconcile one learner

Configuration (.env): MAGNATE_API_URL / MAGNATE_ENTITLEMENTS_TOKEN /
MAGNATE_PAID_PLAN, AUTHENTIK_API_URL / AUTHENTIK_API_TOKEN,
AUTHENTIK_LEARNERS_GROUP (default learners), AUTHENTIK_PAID_GROUP
(default paid_users).

Run it from a systemd timer — see deploy/systemd/atheniq-entitlement-sync.*.
"""
import argparse
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
    "MAGNATE_PAID_PLAN": "premium",
    "AUTHENTIK_API_URL": "https://auth.cerulean.innotel.us",
    "AUTHENTIK_LEARNERS_GROUP": "learners",
    "AUTHENTIK_PAID_GROUP": "paid_users",
    "AUTHENTIK_PAGE_SIZE": "200",
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
# pure decision (unit-tested)
# --------------------------------------------------------------------------

def reconciliation_action(current_member, entitled):
    """What to do for one learner: 'add', 'remove', or None.

    `entitled` is True, False, or None. None means "could not determine" and
    must never change membership — an unreachable Magnate must not revoke
    anyone."""
    if entitled is True and not current_member:
        return "add"
    if entitled is False and current_member:
        return "remove"
    return None


# --------------------------------------------------------------------------
# HTTP clients
# --------------------------------------------------------------------------

def _request(url, method="GET", token="", body=None, insecure=False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    ctx = None
    if insecure:
        ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw[:300]}
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach {url}: {e.reason}")


class Authentik:
    def __init__(self, base, token, insecure=False):
        self.base = base.rstrip("/")
        self.token = token
        self.insecure = insecure

    def _call(self, path, method="GET", body=None):
        return _request(self.base + path, method=method, token=self.token,
                        body=body, insecure=self.insecure)

    def group_uuid(self, name):
        _, data = self._call(f"/api/v3/core/groups/?name={urllib.parse.quote(name)}")
        results = (data or {}).get("results", [])
        for group in results:
            if group.get("name") == name:
                return group.get("pk")
        return None

    def users(self, limit=None):
        page_size = int(cfg("AUTHENTIK_PAGE_SIZE", DEFAULTS["AUTHENTIK_PAGE_SIZE"]))
        out = []
        page = 1
        while True:
            status, data = self._call(
                f"/api/v3/core/users/?page_size={page_size}&page={page}")
            if status != 200:
                raise SystemExit(f"Authentik user list failed (HTTP {status}): {data}")
            out.extend(data.get("results", []))
            if limit and len(out) >= limit:
                return out[:limit]
            nxt = (data.get("pagination") or {}).get("next")
            if not nxt:
                return out
            page = int(nxt)

    def user(self, username):
        _, data = self._call(
            f"/api/v3/core/users/?username={urllib.parse.quote(username)}")
        for user in (data or {}).get("results", []):
            if user.get("username") == username:
                return user
        return None

    def add_user(self, group_uuid, pk):
        return self._call(f"/api/v3/core/groups/{group_uuid}/add_user/",
                          method="POST", body={"pk": pk})

    def remove_user(self, group_uuid, pk):
        return self._call(f"/api/v3/core/groups/{group_uuid}/remove_user/",
                          method="POST", body={"pk": pk})


class Magnate:
    def __init__(self, base, token, plan, insecure=False):
        self.base = base.rstrip("/")
        self.token = token
        self.plan = plan
        self.insecure = insecure

    def entitled(self, user):
        params = urllib.parse.urlencode({"plan": self.plan, "user": user})
        status, body = _request(f"{self.base}/api/entitlements?{params}",
                                token=self.token, insecure=self.insecure)
        if status != 200:
            return None
        value = (body or {}).get("entitled")
        return value if value in (True, False) else None


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def learners_in(users, learners_uuid):
    return [u for u in users if learners_uuid in (u.get("groups") or [])]


def reconcile(auth, mag, learners_uuid, paid_uuid, users, dry_run):
    added = removed = unchanged = unknown = 0
    for user in users:
        if not user.get("is_active", True):
            continue
        username = user.get("username", "")
        current = paid_uuid in (user.get("groups") or [])
        entitled = mag.entitled(username)
        action = reconciliation_action(current, entitled)
        if entitled is None:
            unknown += 1
        if action == "add":
            print(f"  + {username}: granted paid access")
            if not dry_run:
                auth.add_user(paid_uuid, user["pk"])
            added += 1
        elif action == "remove":
            print(f"  - {username}: revoked paid access")
            if not dry_run:
                auth.remove_user(paid_uuid, user["pk"])
            removed += 1
        else:
            unchanged += 1
    return added, removed, unchanged, unknown


def run(args):
    auth = Authentik(cfg("AUTHENTIK_API_URL"), cfg("AUTHENTIK_API_TOKEN"),
                     insecure=args.insecure)
    mag = Magnate(cfg("MAGNATE_API_URL"), cfg("MAGNATE_ENTITLEMENTS_TOKEN"),
                  cfg("MAGNATE_PAID_PLAN"), insecure=args.insecure)

    if not auth.token:
        raise SystemExit("AUTHENTIK_API_TOKEN is not set — see .env.example.")

    learners_uuid = auth.group_uuid(cfg("AUTHENTIK_LEARNERS_GROUP"))
    paid_uuid = auth.group_uuid(cfg("AUTHENTIK_PAID_GROUP"))
    if not paid_uuid:
        raise SystemExit(f"Authentik group '{cfg('AUTHENTIK_PAID_GROUP')}' not found.")
    if not learners_uuid:
        raise SystemExit(f"Authentik group '{cfg('AUTHENTIK_LEARNERS_GROUP')}' not found.")

    if args.user:
        user = auth.user(args.user)
        if not user:
            raise SystemExit(f"no Authentik user '{args.user}'")
        users = [user]
    else:
        users = learners_in(auth.users(limit=args.limit), learners_uuid)

    if args.status:
        paid = [u for u in users if paid_uuid in (u.get("groups") or [])]
        print("AthenIQ entitlement reconciliation — status")
        print(f"  learners group : {cfg('AUTHENTIK_LEARNERS_GROUP')} ({len(users)} user(s) considered)")
        print(f"  paid group     : {cfg('AUTHENTIK_PAID_GROUP')} ({len(paid)} member(s))")
        print(f"  plan           : {cfg('MAGNATE_PAID_PLAN')}")
        return 0

    plan = cfg("MAGNATE_PAID_PLAN")
    mode = " (dry run)" if args.dry_run else ""
    print(f"Reconciling {len(users)} learner(s) against Magnate plan "
          f"'{plan}'{mode}…")
    added, removed, unchanged, unknown = reconcile(
        auth, mag, learners_uuid, paid_uuid, users, args.dry_run)
    print(f"done: +{added} added, -{removed} removed, {unchanged} unchanged"
          + (f", {unknown} undetermined (left as-is)" if unknown else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", help="reconcile a single Authentik username")
    ap.add_argument("--status", action="store_true", help="print counts and exit")
    ap.add_argument("--dry-run", action="store_true", help="print planned changes only")
    ap.add_argument("--limit", type=int, help="consider at most N learners")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification")
    args = ap.parse_args()

    env = load_dotenv(os.path.join(REPO, ".env"))
    for k, v in env.items():
        os.environ.setdefault(k, v)

    sys.exit(run(args))


if __name__ == "__main__":
    main()
