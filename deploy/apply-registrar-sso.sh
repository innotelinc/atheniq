#!/bin/sh
# Put deploy/compose/atheniq-registrar-sso.yml on the host that runs the
# registrar door, as that host's docker-compose.yml.
#
#   ./deploy/apply-registrar-sso.sh root@192.168.1.73
#   SSO_DIR=/opt/registrar-sso ./deploy/apply-registrar-sso.sh root@host
#
# WHY THIS EXISTS. The proxy in front of the console used to be a hand-edited
# copy on the host, so a route added in the repository reached production only
# if somebody remembered to paste it there — and a route added on the host
# reached no repository at all. This makes the repository's file the deployed
# file: one ssh call copies it, validates it against the host's own environment,
# and recreates the containers.
#
# WHAT IT LEAVES ALONE. `console-sso.env` and `.env` beside it are the host's
# secrets; they are not in this repository and are never read or written here.
# The previous compose file is kept as docker-compose.yml.bak-<timestamp>.
#
# One ssh invocation does everything, so a copy can never sit on the host
# without the recreate that follows it. ssh prompts for a password or uses a
# key, as it would by hand.
set -eu

TARGET="${1:?usage: $0 <user@host>}"
SOURCE="$(dirname "$0")/compose/atheniq-registrar-sso.yml"
DIR="${SSO_DIR:-/usr/src/atheniq-console-sso}"

test -f "$SOURCE" || { echo "apply-registrar-sso: missing $SOURCE" >&2; exit 1; }

# The file carries no secrets, but sending it inline keeps this to a single
# connection: there is no window where the host has half of a deploy.
payload="$(base64 < "$SOURCE" | tr -d '\n')"

ssh "$TARGET" "
  set -eu
  cd '$DIR' || { echo 'apply-registrar-sso: no $DIR on the host' >&2; exit 1; }
  stamp=\$(date +%Y%m%d-%H%M%S)
  if [ -f docker-compose.yml ]; then
    cp -a docker-compose.yml \"docker-compose.yml.bak-\$stamp\"
    echo \"apply-registrar-sso: kept the previous file as docker-compose.yml.bak-\$stamp\"
  fi
  printf '%s' '$payload' | base64 -d > docker-compose.yml
  echo 'apply-registrar-sso: validating against the host environment'
  docker compose -f docker-compose.yml config -q
  echo 'apply-registrar-sso: recreating'
  docker compose -f docker-compose.yml up -d --remove-orphans
  docker compose -f docker-compose.yml ps --format 'table {{.Name}}\t{{.Status}}'
"
