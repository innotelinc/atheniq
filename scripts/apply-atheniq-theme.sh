#!/usr/bin/env bash
# apply-atheniq-theme.sh — put AthenIQ's LMS branding on the running Tutor LMS,
# and make it part of the image so a container recreate keeps it.
#
# The LMS is themed with Indigo, whose footer still prints "Powered by: Tutor +
# Open edX" and an edX trademark paragraph, and whose header/favicon carry the
# upstream marks. The files in contrib/atheniq-theme/ are the source of truth;
# this script applies them — the templates (footer, index overlay), the brand
# rasters (header logo, dark-header logo, favicon) and the Unity stylesheets the
# footer links.
#
#   ./scripts/apply-atheniq-theme.sh             # copy in, bake, restart
#   ./scripts/apply-atheniq-theme.sh --no-bake   # a look only: lost on the next recreate
#   ./scripts/apply-atheniq-theme.sh --no-restart
#
# NOT A WRITABLE-LAYER COPY. `docker cp` into the running container survives a
# restart but not a recreate — and `tutor local launch` stops the platform and
# starts it again, which recreates the containers. So after the copy, the script
# bakes the same files into the image the compose project starts from: a
# one-layer derivative of the upstream `overhangio/openedx` image, which is
# seconds, not the multi-hour edx-platform source rebuild. The untouched image
# is kept under `atheniq/openedx-theme-base:<tag>`, which is the rollback:
#
#   docker tag atheniq/openedx-theme-base:22.0.2-indigo \
#     docker.io/overhangio/openedx:22.0.2-indigo && tutor local start -d
#
# The label `atheniq.theme.base` on the baked image records what it was built
# from, so a second run does not stack on the first: the bake is always one
# layer over the upstream image, and identical content is a cached no-op.
#
# `tutor images build openedx` still replaces that tag from source. Enable the
# `atheniqtheme` plugin (contrib/tutor-atheniq-theme) before rebuilding, so the
# rebuild carries the same files — see docs/Deployment.md §Branding.
#
# The brand rasters are generated — run `make images` first if they are stale.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_DIR="${REPO}/contrib/atheniq-theme"
LMS_CONTAINER="${LMS_CONTAINER:-tutor_local-lms-1}"
THEME_ROOT="${THEME_ROOT:-/openedx/themes/indigo/lms}"
THEME_TARGET="${THEME_TARGET:-${THEME_ROOT}/templates}"
THEME_STATIC="${THEME_STATIC:-${THEME_ROOT}/static}"
IMAGES_TARGET="${IMAGES_TARGET:-${THEME_STATIC}/images}"
# The footer links /theming/asset/atheniq/…, which the LMS resolves out of the
# collected static files — the theme directory alone is not what a browser gets.
STATIC_TARGET="${STATIC_TARGET:-/openedx/staticfiles/atheniq}"

restart=1
bake=1
for arg in "$@"; do
  case "${arg}" in
    --no-restart) restart=0 ;;
    --no-bake) bake=0 ;;
    -h|--help)
      sed -n '2,/^set -euo/{/^#/p}' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "unknown option: ${arg}" >&2; exit 2 ;;
  esac
done

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

# The Unity skin the footer links. Both copies matter: the theme's static dir is
# where a rebuilt image takes it from, and the collected copy is what this
# running LMS serves at /theming/asset/atheniq/….
for file in unity-light.css unity-dark.css; do
  copy "${THEME_DIR}/lms/static/atheniq/${file}" "${THEME_STATIC}/atheniq"
  copy "${THEME_DIR}/lms/static/atheniq/${file}" "${STATIC_TARGET}"
done

# --- bake the copies into the image ------------------------------------------
#
# The container's writable layer is not where a brand can live: `tutor local
# launch` stops and starts the platform, and a recreated container comes back
# from the image without it. One COPY layer fixes that, from the *upstream*
# image — never from the last bake, or every run would grow the chain.

THEME_IMAGE=""
THEME_BASE=""

bake() {
  local image base labels tag ctx
  image="$(docker inspect -f '{{.Config.Image}}' "${LMS_CONTAINER}")"
  labels="$(docker image inspect -f '{{json .Config.Labels}}' "${image}" 2>/dev/null || echo '{}')"
  base="$(printf '%s\n' "${labels}" \
    | sed -n 's/.*"atheniq\.theme\.base":"\([^"]*\)".*/\1/p')"
  if [ -n "${base}" ] && ! docker image inspect "${base}" >/dev/null 2>&1; then
    echo "the base ${base} recorded on ${image} is gone; rebasing on ${image}" >&2
    base=""
  fi
  if [ -z "${base}" ]; then
    tag="${image##*/}"; tag="${tag#*:}"
    base="atheniq/openedx-theme-base:${tag}"
    docker tag "${image}" "${base}"
    echo "kept the upstream image as ${base}"
  fi

  ctx="$(mktemp -d)"
  cat > "${ctx}/Dockerfile" <<DOCKERFILE
FROM ${base}
LABEL atheniq.theme.base="${base}"
COPY --chown=app:app lms/ ${THEME_ROOT}/
COPY --chown=app:app lms/static/atheniq/ ${STATIC_TARGET}/
DOCKERFILE
  docker build --label "atheniq.theme.base=${base}" \
    -t "${image}" -f "${ctx}/Dockerfile" "${THEME_DIR}"
  rm -rf "${ctx}"

  # Prove it rather than trust the build's exit code: the two paths a browser
  # and a template reach are the two that have to be in the image.
  docker run --rm --entrypoint /bin/sh "${image}" -c \
    "test -f ${THEME_TARGET}/footer.html \
     && test -f ${IMAGES_TARGET}/favicon.ico \
     && test -f ${STATIC_TARGET}/unity-light.css"
  echo "baked the theme into ${image} (from ${base})"

  THEME_IMAGE="${image}"
  THEME_BASE="${base}"
}

if [ "${bake}" = "1" ]; then
  bake
fi

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

if [ "${bake}" = "1" ]; then
  cat <<EOF

The branding is part of ${THEME_IMAGE}, so recreating the container
(tutor local launch) now keeps it. Nothing else to re-run.

Rollback to the untouched image:

    docker tag ${THEME_BASE} ${THEME_IMAGE} && tutor local start -d
EOF
else
  cat <<'EOF'

--no-bake: the copies live in the container's writable layer only. They survive a
restart, and are gone the next time the container is recreated (`tutor local
launch`). Re-run without --no-bake to make them part of the image.
EOF
fi
