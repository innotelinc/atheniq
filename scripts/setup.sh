#!/usr/bin/env bash
# ==========================================================================
# AuthenIQ — one-shot bootstrap: preflight, guard hooks, .env secrets, and a
# bring-up checklist. Idempotent; safe to re-run.
# ==========================================================================
set -Eeuo pipefail

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning: %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

say "AuthenIQ bootstrap"
say "================="

# ---- 1. Preflight ----------------------------------------------------------
say "1/4 preflight"
command -v git      >/dev/null || die "git is required"
command -v docker   >/dev/null || die "docker is required"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is required"
command -v python3  >/dev/null || die "python3 is required (Tutor/Open edX)"
command -v openssl  >/dev/null || die "openssl is required (secret generation)"
command -v curl     >/dev/null || die "curl is required"
say "    ok — git, docker, compose, python3, openssl, curl"

# ---- 2. Guard hooks --------------------------------------------------------
say "2/4 attribution guard hooks"
git config core.hooksPath .githooks
say "    ok — core.hooksPath -> .githooks"

# ---- 3. .env ---------------------------------------------------------------
say "3/4 environment"
if [ -f .env ]; then
  warn ".env already exists — leaving it untouched"
else
  cp .env.example .env
  # Replace change-me placeholders for secret-ish keys with random values.
  while IFS='=' read -r key value; do
    case "$key" in
      ''|\#*) continue ;;
    esac
    case "$key" in
      *PASSWORD*|*SECRET*|*KEY*|*TOKEN*)
        if [ -n "$value" ] && printf '%s' "$value" | grep -q '^change-me'; then
          sed -i "s|^${key}=.*|${key}=$(openssl rand -hex 24)|" .env
        fi
        ;;
    esac
  done < .env
  say "    ok — created .env with generated secrets (edit host/domain values)"
fi

# ---- 4. Checklist ----------------------------------------------------------
say "4/4 next steps"
printf '%s\n' \
  "  1. Tutor LMS core:        pip install tutor && make tutor:quickstart" \
  "  2. AI classroom:          docs/Deployment.md — Stage 3 (OpenMAIC)" \
  "  3. Realtime:              docs/Deployment.md — Stage 4 (Convex, self-hosted)" \
  "  4. Gateway + agents:      make gateway:up (OmniRoute on 127.0.0.1:20128)" \
  "  5. Signed certificates:   docs/Deployment.md — Stage 7 (Signara)" \
  "  Full runbook:             docs/Deployment.md"

say "done."
