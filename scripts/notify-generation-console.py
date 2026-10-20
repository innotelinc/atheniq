#!/usr/bin/env python3
"""Deliver a failed console probe to the channels this deployment configured.

Email is the site relay: mail.innotel.us on port 25, STARTTLS, no credentials —
the path Mailcow accepts inbound mail from the LAN on. Port 587 with
`ATHENIQ_SMTP_USER`/`ATHENIQ_SMTP_PASSWORD` is supported for a relay that wants
submission auth. A plain-text webhook (ntfy-style Title/Priority/Tags) is
optional; this host uses email.

Run by check-generation-console.sh after the probe has already failed. An
unconfigured channel is skipped. The exit status is 1 when a configured channel
could not deliver; the probe's failed unit is independent of that.
"""
import os
import smtplib
import ssl
import sys
import urllib.request
from email.message import EmailMessage


def truthy(value: str) -> bool:
    return value.lower() not in ("0", "false", "no", "off", "")


def email_alert(url: str, error: str) -> str | None:
    recipient = os.environ.get("ATHENIQ_ALERT_EMAIL", "").strip()
    if not recipient:
        return None
    host = os.environ.get("ATHENIQ_SMTP_HOST", "mail.innotel.us").strip()
    port = int(os.environ.get("ATHENIQ_SMTP_PORT", "25"))
    sender = os.environ.get("ATHENIQ_SMTP_FROM", "atheniq-uptime@innotel.us").strip()
    user = os.environ.get("ATHENIQ_SMTP_USER", "").strip()
    password = os.environ.get("ATHENIQ_SMTP_PASSWORD", "")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = "AthenIQ generation console is down"
    message.set_content(
        "The AthenIQ generation console failed its health probe.\n\n"
        f"URL: {url}\nError: {error}\n\n"
        "Sent by the atheniq-generation-uptime timer on the AthenIQ host.\n"
    )
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if truthy(os.environ.get("ATHENIQ_SMTP_STARTTLS", "1")):
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if user:
            smtp.login(user, password)
        smtp.send_message(message)
    return f"email {recipient} via {host}:{port}"


def webhook_alert(url: str, error: str) -> str | None:
    target = os.environ.get("ATHENIQ_ALERT_WEBHOOK_URL", "").strip()
    if not target:
        return None
    body = f"AthenIQ generation console health check failed\n\n{url}\n\n{error}".encode()
    request = urllib.request.Request(
        target,
        data=body,
        method="POST",
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Title": "AthenIQ generation console is down",
            "Priority": "high",
            "Tags": "warning",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return f"webhook {target} ({response.status})"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "(unknown)"
    error = sys.argv[2] if len(sys.argv) > 2 else "(no detail)"
    delivered: list[str] = []
    failed: list[str] = []
    for name, send in (("email", email_alert), ("webhook", webhook_alert)):
        try:
            result = send(url, error)
        except Exception as exc:  # a broken channel must not hide the probe failure
            failed.append(f"{name} failed: {exc}")
            continue
        if result:
            delivered.append(result)
    for line in delivered:
        print(line)
    for line in failed:
        print(line, file=sys.stderr)
    if not delivered and not failed:
        print("no alert channel configured (set ATHENIQ_ALERT_EMAIL or ATHENIQ_ALERT_WEBHOOK_URL)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
