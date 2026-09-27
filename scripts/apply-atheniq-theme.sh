#!/usr/bin/env bash
# apply-atheniq-theme.sh — put AthenIQ's LMS branding on the running Tutor LMS.
#
# The LMS is themed with Indigo, whose footer still prints "Powered by: Tutor +
# Open edX" and an edX trademark paragraph, and whose header/favicon carry the
# upstream marks. Indigo's theme files live inside the LMS image, so the
# cleanest immediate fix is to copy our overrides over them and restart the LMS.
# The files in contrib/atheniq-theme/ are the source of truth; this script
# applies them — both the templates (footer, index overlay) and the brand
# rasters (header logo, dark-header logo, favicon).
#
#   ./scripts/apply-atheniq-theme.sh            # apply + restart the LMS
#   ./scripts/apply-atheniq-theme.sh --no-restart
#
# This is an operational convenience, not a substitute for a real theme build:
# the overrides live in the container's writable layer and are lost if the
# container is recreated (e.g. `tutor local launch`). Re-run this script after a
# recreate, or fold the templates into a Tutor theme plugin before a rebuild.
#
# The brand rasters are generated — run `make images` first if they are stale.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_DIR="${REPO}/contrib/atheniq-theme"
LMS_CONTAINER="${LMS_CONTAINER:-tutor_local-lms-1}"
THEME_TARGET="${THEME_TARGET:-/openedx/themes/indigo/lms/templates}"
IMAGES_TARGET="${IMAGES_TARGET:-/openedx/themes/indigo/lms/static/images}"

restart=1
[ "${1:-}" = "--no-restart" ] && restart=0

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
docker inspect "${LMS_CONTAINER}" >/dev/null 2>&1 \
  || { echo "LMS container not found: ${LMS_CONTAINER}" >&2; exit 1; }

# templates -> the theme's templates dir; rasters -> its static/images dir.
copy() {
  local src="$1" dest_dir="$2"
  [ -f "${src}" ] || { echo "missing theme file: ${src}" >&2; exit 1; }
  docker exec "${LMS_CONTAINER}" mkdir -p "${dest_dir}"
  docker cp "${src}" "${LMS_CONTAINER}:${dest_dir}/$(basename "${src}")"
  echo "copied $(basename "${src}") -> ${LMS_CONTAINER}:${dest_dir}/$(basename "${src}")"
}

for file in footer.html index_overlay.html; do
  copy "${THEME_DIR}/lms/templates/${file}" "${THEME_TARGET}"
done

for file in logo.png logo-white.png favicon.ico; do
  copy "${THEME_DIR}/lms/static/images/${file}" "${IMAGES_TARGET}"
done

if [ "${restart}" = "1" ]; then
  docker restart "${LMS_CONTAINER}" >/dev/null
  echo "restarted ${LMS_CONTAINER}"
fi

cat <<'EOF'

Note: the learner MFEs (catalog, learning, ...) render their own footer from
their compiled JS bundles, which still say "Powered by Open edX". That string is
baked into the images at build time and is not runtime-configurable — removing it
needs an MFE rebuild (the tutor-atheniq-mfe plugin hides Indigo's default footer
slot content and renders the AthenIQ lockup). See docs/Deployment.md §Branding.
EOF
