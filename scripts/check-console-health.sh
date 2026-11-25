#!/usr/bin/env bash
# check-console-health.sh — probe the AthenIQ console through its SSO proxy.
#
# The console's /api/health is one path generation-sso answers without a
# session (--skip-auth-route=^/api/health($|[/?])), so this walks the same
# NPM -> oauth2-proxy -> console path a staff browser takes. A 502 from the
# proxy, a dead upstream or a console that stopped answering all fail the check.
#
# A failure is handed to notify-console-health.py, which emails the address
# in ATHENIQ_ALERT_EMAIL (and/or posts to ATHENIQ_ALERT_WEBHOOK_URL when set).
# The unit fails either way, so a broken alert channel never turns a down
# console into a healthy-looking probe.
#
#   ./scripts/check-console-health.sh
#   ATHENIQ_CONSOLE_HEALTH_URL=http://192.168.1.59:8091/api/health ./scripts/check-console-health.sh
set -u

URL="${ATHENIQ_CONSOLE_HEALTH_URL:-https://ai.atheniq.courses/api/health}"

if body=$(curl -fsS --max-time 10 "$URL" 2>&1); then
  echo "ok ${URL} ${body}"
  exit 0
fi

echo "FAIL ${URL}: ${body}" >&2

notifier="$(dirname "$0")/notify-console-health.py"
if [ -f "$notifier" ]; then
  if reply=$(python3 "$notifier" "$URL" "$body" 2>&1); then
    echo "alert: ${reply}" >&2
  else
    echo "alert FAILED: ${reply}" >&2
  fi
fi

exit 1
