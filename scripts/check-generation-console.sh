#!/usr/bin/env bash
# check-generation-console.sh — probe the AthenIQ console through its SSO proxy.
#
# The console's /healthz is the one path generation-sso answers without a
# session (--skip-auth-route=^/healthz$), so this walks the same
# NPM -> oauth2-proxy -> console path a staff browser takes. A 502 from the
# proxy, a dead upstream or a console that stopped answering all fail the check.
#
# A failure is also delivered to ATHENIQ_ALERT_WEBHOOK_URL when the deployment
# set one (this host uses an ntfy topic; the body is plain text and the Title/
# Priority/Tags headers are ntfy's). The unit fails either way, so a missing or
# broken webhook never turns a down console into a healthy-looking probe.
#
#   ./scripts/check-generation-console.sh
#   ATHENIQ_CONSOLE_HEALTH_URL=http://192.168.1.59:8091/healthz ./scripts/check-generation-console.sh
set -u

URL="${ATHENIQ_CONSOLE_HEALTH_URL:-https://ai.lms.innotel.us/healthz}"

if body=$(curl -fsS --max-time 10 "$URL" 2>&1); then
  echo "ok ${URL} ${body}"
  exit 0
fi

echo "FAIL ${URL}: ${body}" >&2

webhook="${ATHENIQ_ALERT_WEBHOOK_URL:-}"
if [ -n "$webhook" ]; then
  alert=$(printf 'AthenIQ generation console health check failed\n\n%s\n\n%s' "$URL" "$body")
  if reply=$(curl -fsS --max-time 10 \
      -H "Title: AthenIQ generation console is down" \
      -H "Priority: high" \
      -H "Tags: warning" \
      --data-binary "$alert" "$webhook" 2>&1); then
    echo "alert sent: ${reply}" >&2
  else
    echo "alert could NOT be sent: ${reply}" >&2
  fi
fi

exit 1
