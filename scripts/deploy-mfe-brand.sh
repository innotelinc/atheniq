#!/usr/bin/env bash
# deploy-mfe-brand.sh — put the AthenIQ copy into the compiled MFEs.
#
# The MFE image is assembled from one image per app (`atheniq/openedx-mfe:<app>-*`),
# each holding that app's built `dist`. There is no Tutor install on this host, so
# this does what `tutor images build mfe` would: take each app's dist, run
# `patch-mfe-brand.py` over it, and stack the results into one runtime image.
#
# Nothing is rebuilt with webpack. The patch only rewrites text inside files that
# webpack already produced, so the bundles keep their hashed names — every
# `index.html` reference stays valid — and the layer is a COPY of a few hundred
# megabytes instead of a rebuild of thirteen Node apps.
#
# Usage:
#   scripts/deploy-mfe-brand.sh            # patch, assemble, retag, recreate
#   DRY_RUN=1 scripts/deploy-mfe-brand.sh  # patch and assemble, do not retag/recreate
#
# Env:
#   SRC_SUFFIX   tag suffix of the app images to patch (default 20261020)
#   DST_SUFFIX   suffix for the patched images      (default: today, YYYYMMDD)
#   BASE         the runtime base image             (default overhangio/openedx-mfe:22.0.0-indigo.pre-nav)
#   TARGET       the tag the deployment runs        (default overhangio/openedx-mfe:22.0.0-indigo)

set -euo pipefail

SRC_SUFFIX="${SRC_SUFFIX:-20261020}"
DST_SUFFIX="${DST_SUFFIX:-$(date -u +%Y%m%d)}"
BASE="${BASE:-overhangio/openedx-mfe:22.0.0-indigo.pre-nav}"
TARGET="${TARGET:-overhangio/openedx-mfe:22.0.0-indigo}"
WORK="${WORK:-/tmp/mfe-brand-$DST_SUFFIX}"
DRY_RUN="${DRY_RUN:-0}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$HERE/patch-mfe-brand.py"
# The shell guard: an expired JWT cookie makes the app's public config call 401 and
# leaves every page on the error boundary (measured 2026-10-29). It lives in the
# same `index.html` this script already rewrites, so it is applied here — a rebuilt
# image loses it exactly as it loses the brand patch.
STALE_JWT="$HERE/patch-mfe-stale-jwt.py"
# The Unity skin the patcher installs beside each bundle: the canonical copies
# from contrib/atheniq-theme, so the MFEs and the console wear one palette.
UNITY_CSS="${UNITY_CSS:-$HERE/../contrib/atheniq-theme/mfe}"
if [ ! -f "$UNITY_CSS/unity-light.css" ]; then
  echo "deploy-mfe-brand: no Unity skin at $UNITY_CSS (set UNITY_CSS)" >&2
  exit 1
fi

# Site is built from a different source path than the app MFEs.
APPS="authn account profile catalog learning learner-dashboard discussions gradebook communications ora-grading admin-console authoring site"

dist_path() { [ "$1" = site ] && echo /openedx/site/dist || echo /openedx/app/dist; }

mkdir -p "$WORK"

for app in $APPS; do
  src="atheniq/openedx-mfe:$app-$SRC_SUFFIX"
  dist="$(dist_path "$app")"
  echo "=== $app"
  rm -rf "$WORK/$app"
  mkdir -p "$WORK/$app"
  cid="$(docker create "$src")"
  docker cp "$cid:$dist" "$WORK/$app/dist" >/dev/null
  docker rm "$cid" >/dev/null
  python3 "$PATCH" "$WORK/$app/dist" --app "$app" --unity-css "$UNITY_CSS"
  if [ -f "$WORK/$app/dist/index.html" ]; then
    python3 "$STALE_JWT" "$WORK/$app/dist/index.html"
  fi
  # The patch rewrites compiled JavaScript, so "it ran" is not "it is valid".
  # Every app's bundle is parsed before it is allowed into an image; a one-line
  # brace mistake once shipped a page that rendered nothing.
  if command -v node >/dev/null 2>&1; then
    for bundle in "$WORK/$app/dist"/app.*.js; do
      node --check "$bundle" || { echo "$app: $bundle does not parse" >&2; exit 1; }
    done
  else
    echo "    (no node here: syntax not re-checked)" >&2
  fi
  printf 'FROM %s\nCOPY dist %s\n' "$src" "$dist" | \
    docker build -q -t "atheniq/openedx-mfe:$app-$DST_SUFFIX" -f - "$WORK/$app" >/dev/null
done

echo "=== assembling $TARGET"
# `rm -rf /openedx/dist` first: the base image carries an older build of every
# app, and a plain COPY over it leaves the previous hashed bundles behind —
# still served, still wearing the old brand. Only the app dirs live there, and
# every one of them is copied back below.
printf 'FROM %s\nRUN rm -rf /openedx/dist\n' "$BASE" > "$WORK/Dockerfile"
for app in $APPS; do
  printf 'COPY --from=atheniq/openedx-mfe:%s-%s %s /openedx/dist/%s\n' \
    "$app" "$DST_SUFFIX" "$(dist_path "$app")" "$app" >> "$WORK/Dockerfile"
done
docker build -t "$TARGET" "$WORK" >/dev/null

echo "=== assembled $(docker image inspect -f '{{.Id}}' "$TARGET")"

if [ "$DRY_RUN" = 1 ]; then
  echo "DRY_RUN: left $TARGET retagged; the running container is untouched"
  exit 0
fi

# The previous image stays under its own tag: a brand patch that breaks a page
# is then one retag away from being undone, without a rebuild.
previous="$(docker inspect -f '{{.Image}}' tutor_local-mfe-1 2>/dev/null || true)"
if [ -n "$previous" ]; then
  rollback="overhangio/openedx-mfe:rollback-$(date -u +%Y%m%d%H%M)"
  docker tag "$previous" "$rollback"
  echo "=== rollback tag $rollback"
fi

# The project name is the deployment's, not the directory's: run without it and
# compose invents a second project (`local`), leaves the real container on the
# old image and says it succeeded.
compose="/home/tutor/.local/share/tutor/env/local"
COMPOSE_PROJECT_NAME=tutor_local docker compose \
  -f "$compose/docker-compose.yml" -f "$compose/docker-compose.prod.yml" \
  up -d --force-recreate --no-deps mfe

sleep 5
docker inspect -f 'mfe runs {{.Image}}' tutor_local-mfe-1
echo "=== target is $(docker image inspect -f '{{.Id}}' "$TARGET")"
