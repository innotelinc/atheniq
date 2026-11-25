#!/usr/bin/env bash
# Kept for runbooks that call scripts/setup.sh directly. The entry point is
# ./setup.sh at the repo root, which runs the guided wizard.
set -Eeuo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/setup.sh" "$@"
