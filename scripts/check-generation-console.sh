#!/usr/bin/env bash
# check-generation-console.sh — probe the AthenIQ console through its SSO proxy.
#
# The console's /healthz is the one path generation-sso answers without a
# session (--skip-auth-route=^/healthz$), so this walks the same
# NPM -> oauth2-proxy -> console path a staff browser takes. A 502 from the
# proxy, a dead upstream or a console that stopped answering all fail the check.
#
# A failure is handed to notify-generation-console.py, which emails the address
# in ATHENIQ_ALERT_EMAIL (and/or posts to ATHENIQ_ALERT_WEBHOOK_URL when set).
# The unit fails either way, so a broken alert channel never turns a down
# console into a healthy-looking probe.
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

notifier="$(dirname "$0")/notify-generation-console.py"
if [ -f "$notifier" ]; then
  if reply=$(python3 "$notifier" "$URL" "$body" 2>&1); then
    echo "alert: ${reply}" >&2
  else
    echo "alert FAILED: ${reply}" >&2
  fi
fi

exit 1
