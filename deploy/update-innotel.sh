#!/bin/sh
# Publish the Innotel Labs company site (web/innotel/) — one command.
#
#   deploy/update-innotel.sh [checkout]
#
# `innotel.tech` / `innotel.us` is `web/innotel/`, served by the `innotel`
# compose service (Caddy file server) out of a git checkout on the host, with
# the edge (NPM proxy host 88) forwarding to INNOTEL_BIND:INNOTEL_PORT. There
# is no build step, so publishing is exactly: fast-forward the checkout, then
# recreate the container that serves it. The bind mount is read-only, so the
# files on disk are the files the visitor sees.
set -eu

DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PORT="$(sed -n 's/^INNOTEL_PORT=//p' "$DIR/.env" 2>/dev/null | tail -1)"
PORT="${PORT:-8086}"
BIND="$(sed -n 's/^INNOTEL_BIND=//p' "$DIR/.env" 2>/dev/null | tail -1)"
BIND="${BIND:-127.0.0.1}"
[ "$BIND" = "0.0.0.0" ] && BIND=127.0.0.1

cd "$DIR"
test -f web/innotel/index.html

echo "== checkout: $DIR"
git fetch --quiet origin main
git merge --ff-only FETCH_HEAD
git log --oneline -1

docker compose up -d innotel
sleep 2
curl -sS -o /dev/null -w "== innotel origin (${BIND}:${PORT}): %{http_code}\n" "http://${BIND}:${PORT}/"
