#!/usr/bin/env bash
# AthenIQ — first-install entry point. Runs the guided wizard; see --help.
set -Eeuo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/setup-wizard.py" "$@"
