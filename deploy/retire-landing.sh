#!/usr/bin/env bash
#
# retire-landing.sh — make a shut-down landing container stay shut down.
#
#   deploy/retire-landing.sh [dir...]        # default roots: /usr/src /srv /home
#
# The `landing` service serves the apex from a checkout, and more than one host
# has had a stack that defines it: the copy on the classroom host
# (`192.168.1.59`) was stopped, and a plain `docker compose up` there put it back,
# on a tree nobody was updating. The service is now behind the `landing` compose
# profile, so an untargeted `up` leaves it out — but a container that already
# exists keeps running until something removes it, and a checkout that has not
# pulled the change still defines the service without the profile.
#
# This walks the stacks that define it and, for each one:
#
#   1. fast-forwards the checkout (a dirty tree is reported, never merged over),
#   2. refuses to touch a stack whose file has no landing profile — bringing it
#      up would be the thing we are trying to prevent,
#   3. removes the landing container with `--profile landing rm -sf landing`,
#      then brings the rest of the stack up, which no longer includes it,
#   4. confirms no `atheniq-landing` container remains.
#
# Nothing here deletes `web/landing/` or any volume: the tree the service served
# stays exactly where it is, so bringing the service back is one command, not a
# restore.
set -euo pipefail

ROOTS=("$@")
[ "${#ROOTS[@]}" -eq 0 ] && ROOTS=(/usr/src /srv /home)

found=0
status=0

while IFS= read -r file; do
  dir="$(dirname "$file")"
  found=$((found + 1))
  echo "== $file"

  if git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
    if [ -n "$(git -C "$dir" status --porcelain)" ]; then
      echo "   local changes in the checkout; not pulling" >&2
      status=1
    else
      if git -C "$dir" pull --ff-only --quiet; then
        :
      else
        echo "   could not fast-forward this checkout" >&2
        status=1
      fi
    fi
    echo "   checkout $(git -C "$dir" rev-parse --short HEAD)"
  else
    echo "   not a git checkout — add the landing profile to this file by hand" >&2
    status=1
  fi

  # Without the profile in the file, an `up` here would recreate the container.
  if ! grep -q 'profiles: \["landing"\]' "$file"; then
    echo "   no landing profile in this file; leaving the stack alone" >&2
    status=1
    continue
  fi

  (
    cd "$dir"
    docker compose --profile landing rm -sf landing >/dev/null 2>&1 || true
    docker compose up -d --remove-orphans
  )

  if [ -n "$(docker ps -a --filter name=atheniq-landing --format '{{.Names}}')" ]; then
    echo "   atheniq-landing is still present" >&2
    status=1
  else
    echo "   atheniq-landing: gone"
  fi

  if [ -f "$dir/web/landing/index.html" ]; then
    echo "   tree kept: web/landing/index.html is still there"
  fi
done < <(grep -rl --include='*compose*.yml' --include='*compose*.yaml' \
           'container_name: atheniq-landing' "${ROOTS[@]}" 2>/dev/null)

if [ "$found" -eq 0 ]; then
  echo "no compose file defining atheniq-landing under: ${ROOTS[*]}" >&2
  exit 1
fi

exit "$status"
