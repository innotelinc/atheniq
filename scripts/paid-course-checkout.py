#!/usr/bin/env python3
"""AthenIQ — paid-course Checkout entry point.

A learner reaching a paid course needs somewhere to pay. AthenIQ holds no price
list and no Stripe key: this small service is the redirect that sends the
learner into Magnate (RevenueOps), tagged with their identity, so the standard
chain takes over — Magnate bills, the plan entitlement turns on, the
entitlement reconciler adds `paid_users`, and paid-enrollment grants the course.

Two shapes, chosen by the course's entry in `config/course-prices.json`:

  * `plan` (no one-off price) -> 302 to Magnate's subscribe page for the plan,
    carrying `?course=<key>&user=<username>` so the purchase is attributable.
  * `amount_cents`            -> create a one-off hosted Stripe Checkout via
    Magnate's `POST /api/purchases` and 302 to it.

It is a *service* (unlike the one-shot scripts) because a course page links to
it. Run it on loopback behind the edge; see
deploy/systemd/atheniq-paid-checkout.service.

Usage:
    python3 scripts/paid-course-checkout.py                 # serve
    python3 scripts/paid-course-checkout.py --addr 127.0.0.1:8099
    python3 scripts/paid-course-checkout.py --list          # show the price map
    python3 scripts/paid-course-checkout.py --dry-run       # plan, no Magnate call

Endpoints:
    GET /buy?course=<key>&user=<name>&email=<addr>  -> 302 to Checkout
    GET /healthz                                    -> 200 "ok"
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS = {
    "MAGNATE_API_URL": "https://app.magnate.innotel.us",
    "PAID_CHECKOUT_ADDR": "127.0.0.1:8099",
    "COURSE_PRICES_FILE": os.path.join(REPO, "config", "course-prices.json"),
    "LMS_HOST": "learn.innotel.us",
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


def load_prices(path=None):
    path = path or cfg("COURSE_PRICES_FILE", DEFAULTS["COURSE_PRICES_FILE"])
    with open(path) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# pure decision (unit-tested)
# --------------------------------------------------------------------------

def checkout_action(catalog, course_key):
    """Decide what a course's checkout should be.

    Returns ("unknown", None) | ("subscribe", url) | ("checkout", entry).
    The plan-shaped case deliberately wins when there is no one-off price: the
    subscription is the billing object, and the entitlement reconciler already
    knows how to turn it into access.
    """
    entry = (catalog.get("courses") or {}).get(course_key)
    if not entry:
        return "unknown", None
    if entry.get("amount_cents"):
        return "checkout", entry
    if entry.get("plan"):
        return "subscribe", entry
    # A course with neither a price nor a plan is free — nothing to buy.
    return "free", entry


def subscribe_redirect(catalog, entry, course_key, user):
    base = catalog.get("subscribe_url") or cfg("MAGNATE_SUBSCRIBE_URL", "")
    params = {"plan": entry.get("plan") or "", "course": course_key}
    if user:
        params["user"] = user
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    return f"{base}?{query}" if query else base


# --------------------------------------------------------------------------
# Magnate
# --------------------------------------------------------------------------

def create_checkout(entry, course_key, user, email, insecure=False):
    """Open a one-off Checkout for a course; return the hosted URL."""
    url = cfg("MAGNATE_API_URL").rstrip("/") + "/api/purchases"
    body = {
        "item": {
            "slug": "course",
            "name": entry.get("name") or course_key,
            "unitAmountCents": int(entry["amount_cents"]),
        },
        "metadata": {"course_key": course_key},
    }
    if user:
        body["metadata"]["username"] = user
    if email:
        body["customerEmail"] = email
    success = f"https://{cfg('LMS_HOST')}/courses/{course_key}/about"
    body["successUrl"] = success
    body["cancelUrl"] = success

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, method="POST", data=data)
    req.add_header("Content-Type", "application/json")
    token = cfg("MAGNATE_ENTITLEMENTS_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    ctx = None
    if insecure:
        import ssl
        ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", "replace")).get("url")


# --------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    catalog = {}
    dry_run = False
    insecure = False
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep stdout tidy
        sys.stderr.write("paid-checkout: " + (fmt % args) + "\n")

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _text(self, code, message):
        body = message.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self._text(200, "ok")
            return
        if parsed.path != "/buy":
            self._text(404, "not found")
            return

        qs = urllib.parse.parse_qs(parsed.query)
        course = (qs.get("course") or [""])[0]
        user = (qs.get("user") or [""])[0]
        email = (qs.get("email") or [""])[0]
        if not course:
            self._text(400, "missing course")
            return

        action, entry = checkout_action(self.catalog, course)
        if action == "unknown":
            self._text(404, f"no price for course {course}")
            return
        if action == "free":
            self._redirect(f"https://{cfg('LMS_HOST')}/courses/{course}/about")
            return
        if action == "subscribe":
            self._redirect(subscribe_redirect(self.catalog, entry, course, user))
            return

        # one-off checkout
        if self.dry_run:
            self._text(200, f"[dry-run] would create a Checkout for {course} "
                            f"({entry['amount_cents']} cents)")
            return
        try:
            url = create_checkout(entry, course, user, email, insecure=self.insecure)
        except urllib.error.HTTPError as e:
            self._text(502, f"Magnate rejected the checkout (HTTP {e.code})")
            return
        except urllib.error.URLError as e:
            self._text(502, f"Magnate unreachable: {e.reason}")
            return
        if not url:
            self._text(502, "Magnate returned no checkout URL")
            return
        self._redirect(url)


def serve(args):
    Handler.catalog = load_prices()
    Handler.dry_run = args.dry_run
    Handler.insecure = args.insecure
    host, _, port = args.addr.rpartition(":")
    server = HTTPServer((host or "127.0.0.1", int(port)), Handler)
    scheme = "http"
    print(f"paid-course checkout listening on {scheme}://{args.addr} "
          f"({'dry run' if args.dry_run else 'live'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--addr", default=cfg("PAID_CHECKOUT_ADDR", DEFAULTS["PAID_CHECKOUT_ADDR"]))
    ap.add_argument("--list", action="store_true", help="print the price map and exit")
    ap.add_argument("--dry-run", action="store_true", help="plan checkouts; do not call Magnate")
    ap.add_argument("--insecure", action="store_true", help="disable TLS verification to Magnate")
    args = ap.parse_args()

    env = load_dotenv(os.path.join(REPO, ".env"))
    for k, v in env.items():
        os.environ.setdefault(k, v)

    if args.list:
        catalog = load_prices()
        print(f"subscribe: {catalog.get('subscribe_url', '(unset)')}")
        for key, entry in (catalog.get("courses") or {}).items():
            price = entry.get("amount_cents")
            access = f"one-off {price} cents" if price else \
                (f"plan {entry.get('plan')}" if entry.get("plan") else "free")
            print(f"  {key:<44} {entry.get('name', ''):<40} {access}")
        return

    serve(args)


if __name__ == "__main__":
    main()
