#!/bin/sh
# Publish the public website — one command.
#
#   deploy/update-landing.sh [checkout]
#
# `atheniq.institute` is `web/landing/`, served by Caddy out of a git checkout
# (the `landing` service in this repository's docker-compose.yml), and the edge
# answers the name by forwarding to that origin (NPM proxy host 206). There is no
# build step, so publishing is exactly: fast-forward the checkout, recreate the
# container that serves it.
#
# Never copy files onto the host by hand. A copy has no history, so nobody can
# tell which commit the school is looking at, and the only way to change it is to
# copy again — which is how the apex once ended up as a hand-edited tree on a
# Vultr box while this repository said something else.
set -eu

DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PORT="$(sed -n 's/^LANDING_PORT=//p' "$DIR/.env" 2>/dev/null | tail -1)"
PORT="${PORT:-8085}"
# The container binds LANDING_BIND; asking loopback when it listens on the LAN
# address reports a failure for a site that is answering.
BIND="$(sed -n 's/^LANDING_BIND=//p' "$DIR/.env" 2>/dev/null | tail -1)"
BIND="${BIND:-127.0.0.1}"
[ "$BIND" = "0.0.0.0" ] && BIND=127.0.0.1

cd "$DIR"
test -f web/landing/index.html

echo "== checkout: $DIR"
git fetch --quiet origin main
git merge --ff-only FETCH_HEAD
git log --oneline -1

# `landing` sits behind the "landing" profile so a plain `docker compose up`
# on a host that does not serve the apex cannot resurrect it; naming it is how
# this script keeps working on the host that does.
docker compose --profile landing up -d landing
sleep 2
curl -sS -o /dev/null -w "== apex origin (${BIND}:${PORT}): %{http_code}\n" "http://${BIND}:${PORT}/"
