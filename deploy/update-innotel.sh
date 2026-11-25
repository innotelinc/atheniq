#!/bin/sh
# Publish the Innotel Labs company site (web/innotel/) to its two real homes.
#
#   deploy/update-innotel.sh
#
# innotel.tech  i1 (192.168.1.51), Incus container `atheniq`
#               /home/tutor/atheniq/web/innotel -> `innotel` (Caddy) :8086
#               NPM edge host 276 -> 192.168.1.59:8086
# innotel.us    i4 (192.168.1.54), Incus container `proxy`
#               /usr/src/innotel-site -> `innotel-site` (nginx) :8086
#               NPM edge host 88  -> 192.168.1.71:8086
#
# No build step. Fast-forward the atheniq checkout on i1, mirror web/innotel/
# into i4's site directory, restart both serving containers, then check the
# origins and the two public URLs.
#
# Run from the admin host (i2) or anywhere with SSH access to i1 and i4.
# Override I1, I4, ATHENIQ_REPO, SITE_DIR or SSH_KEY as needed.
set -eu

I1="${I1:-192.168.1.51}"
I4="${I4:-192.168.1.54}"
ATHENIQ_CONTAINER="${ATHENIQ_CONTAINER:-atheniq}"
ATHENIQ_REPO="${ATHENIQ_REPO:-/home/tutor/atheniq}"
LANDING_SERVICE="${LANDING_SERVICE:-innotel}"
PROXY_CONTAINER="${PROXY_CONTAINER:-proxy}"
SITE_CONTAINER="${SITE_CONTAINER:-innotel-site}"
SITE_DIR="${SITE_DIR:-/usr/src/innotel-site}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10"
[ -n "${SSH_KEY:-}" ] && SSH_OPTS="$SSH_OPTS -i $SSH_KEY"

ssh_i1() { ssh $SSH_OPTS "root@$I1" "$@"; }
ssh_i4() { ssh $SSH_OPTS "root@$I4" "$@"; }

echo "== 1/4 fast-forward $ATHENIQ_REPO on $I1 ($ATHENIQ_CONTAINER) =="
ssh_i1 "incus exec $ATHENIQ_CONTAINER -- bash -lc '
  set -eu
  cd $ATHENIQ_REPO
  git fetch --quiet origin main
  git merge --ff-only FETCH_HEAD
  git log --oneline -1
  test -f web/innotel/index.html
  docker compose up -d $LANDING_SERVICE'"

echo "== 2/4 mirror web/innotel/ to $I4:$SITE_DIR ($PROXY_CONTAINER/$SITE_CONTAINER) =="
ssh_i1 "incus exec $ATHENIQ_CONTAINER -- tar -C $ATHENIQ_REPO/web/innotel --exclude='*.bak*' -cf - ." \
  | ssh_i4 "tar -C $SITE_DIR -xf - && incus exec $PROXY_CONTAINER -- docker restart $SITE_CONTAINER"

echo "== 3/4 verify origins =="
ssh_i1 "incus exec $ATHENIQ_CONTAINER -- curl -sS -o /dev/null -w 'innotel.tech origin %{http_code}\\n' http://127.0.0.1:8086/"
ssh_i4 "curl -sS -o /dev/null -w 'innotel.us origin %{http_code}\\n' http://192.168.1.71:8086/"

echo "== 4/4 verify public =="
for u in https://innotel.tech/ https://innotel.us/; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' "$u" || true)"
  copy="$(curl -sS "$u" | grep -c 'approved and released on the App Store' || true)"
  echo "$u  http=$code  approved-copy=$copy"
done
