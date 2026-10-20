#!/usr/bin/env bash
# check-generation-console.sh — probe the AthenIQ console through its SSO proxy.
#
# The console's /healthz is the one path generation-sso answers without a
# session (--skip-auth-route=^/healthz$), so this walks the same
# NPM -> oauth2-proxy -> console path a staff browser takes. A 502 from the
# proxy, a dead upstream or a console that stopped answering all fail the check.
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
exit 1
