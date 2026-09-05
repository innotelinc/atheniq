#!/usr/bin/env bash
set -Eeuo pipefail

forbidden='code.?buff'
messages="$(git log --all --format='%H%n%s%n%b')"

if printf '%s\n' "$messages" | grep -Ein "$forbidden"; then
  printf 'error: forbidden generated attribution found in commit history\n' >&2
  exit 1
fi

printf 'commit message policy: clean\n'
