#!/usr/bin/env bash
# deploy.sh — bring this host's checkout up to main and restart what it runs.
#
# WHY THIS EXISTS. Part of an AthenIQ host is not in a container: `web/landing/`
# is mounted into the landing service, and `docker-compose.yml` is what tells
# that host what to run at all. Those files used to reach the host by hand
# (rsync, or a `cp` after a fix), which is how the landing page came to exist in
# the repository and in only one of the running hosts. Running this instead
# makes the host's state a function of a commit.
#
# WHAT IT DOES. Refuses to pull over a dirty tree; fast-forwards; reports the
# commits it moved across; brings up the compose services this repo owns; and
# finishes with scripts/cert-check.py --http, because a host that restarted
# cleanly onto a name whose certificate no longer covers it — or whose backend
# never came back and answers 502 — has not deployed.
#
# USAGE
#   ./scripts/deploy.sh                  # pull, restart, verify TLS
#   ./scripts/deploy.sh --no-pull        # restart what is on disk as-is
#   ./scripts/deploy.sh --recreate       # force new containers
#   ./scripts/deploy.sh --no-cert-check  # skip the certificate gate
#   DIR=/srv/atheniq ./scripts/deploy.sh
#
# --recreate matters when a bind-mounted directory is replaced rather than
# edited: a running container keeps the path it resolved at creation, so the
# files the landing service reads would silently stay on the old directory.
#
# A pull that updates this script hands the rest of the run over to the version
# it pulled, so the checks below are never the ones a previous release shipped.
#
# `.env` is gitignored, so a fresh clone has none: copy the host's `.env` in
# first (or the script reports that compose is running on its defaults). Profiles
# stay opt-in, exactly as in the Makefile — set COMPOSE_PROFILES to bring up
# openmaic/convex as well.
set -euo pipefail

DIR="${DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PULL=1
CERT_CHECK=1
RECREATE=0

for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=0 ;;
    --no-cert-check) CERT_CHECK=0 ;;
    --recreate) RECREATE=1 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

cd "$DIR"
[ -f docker-compose.yml ] || { echo "not an AthenIQ checkout: $DIR" >&2; exit 1; }

if [ "$PULL" = 1 ]; then
  git rev-parse --git-dir >/dev/null 2>&1 \
    || { echo "$DIR is not a git clone — re-clone it, or pass --no-pull to restart what is here" >&2; exit 1; }

  if [ -n "$(git status --porcelain)" ]; then
    echo "refusing to pull: $DIR has changes that a pull would carry or collide with" >&2
    git status --short >&2
    exit 1
  fi

  before="$(git rev-parse --short HEAD)"
  git pull --ff-only
  after="$(git rev-parse --short HEAD)"
  if [ "$before" = "$after" ]; then
    echo "already at $after"
  else
    echo "updated $before -> $after"
    git log --oneline "$before..$after"
  fi

  # A script that pulls can pull a new version of itself, and bash is already
  # reading the old one: this run would finish with the checks it started with.
  # Hand over to the version on disk instead, once.
  if [ "${DEPLOY_REEXEC:-0}" != 1 ] && git diff --name-only "$before" "$after" | grep -qx scripts/deploy.sh; then
    echo "deploy.sh itself changed in that pull — re-running it"
    reexec=()
    [ "$RECREATE" = 1 ] && reexec+=(--recreate)
    [ "$CERT_CHECK" = 0 ] && reexec+=(--no-cert-check)
    exec env DEPLOY_REEXEC=1 "$0" --no-pull ${reexec[@]+"${reexec[@]}"}
  fi
fi

if [ -f .env ]; then
  echo "using .env"
else
  echo "note: no .env in $DIR — compose is running on its built-in defaults" >&2
fi

compose_up=(docker compose up -d --remove-orphans)
[ "$RECREATE" = 1 ] && compose_up+=(--force-recreate)
"${compose_up[@]}"
docker compose ps

if [ "$CERT_CHECK" = 1 ]; then
  echo
  if ! python3 scripts/cert-check.py --http; then
    echo "deployed, but a platform name is not answering: see the certificate and" >&2
    echo "HTTP lines above (the edge, its upstream, or the certificate behind it)" >&2
    exit 1
  fi
fi

echo "deploy ok"
