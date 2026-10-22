#!/usr/bin/env bash
# apply-atheniq-theme.sh — install the Unity Open edX theme on the running Tutor
# LMS and Studio, and make it part of the image so a container recreate keeps it.
#
# WHAT IT INSTALLS. `contrib/openedx-theme-unity/` is a complete Open edX theme
# (LMS and Studio templates, compiled stylesheets, fonts, images, and the Unity
# skin). It is installed at `/openedx/themes/unity` and set as the site theme.
# Indigo is not copied, not linked and not required.
#
#   ./scripts/apply-atheniq-theme.sh             # build the image, recreate, set the theme
#   ./scripts/apply-atheniq-theme.sh --no-bake   # copy into the running containers only
#   ./scripts/apply-atheniq-theme.sh --no-restart
#
# NOT A WRITABLE-LAYER COPY. `docker cp` into the running container survives a
# restart but not a recreate — and `tutor local launch` stops the platform and
# starts it again, which recreates the containers. So after the copy, the script
# bakes the same files into the image the compose project starts from: a
# one-layer derivative of the upstream image, which is seconds to build plus a
# `collectstatic`, not the multi-hour edx-platform source rebuild. The untouched
# image is kept under `atheniq/openedx-theme-base:<tag>`, which is the rollback:
#
#   docker tag atheniq/openedx-theme-base:22.0.2 \
#     docker.io/overhangio/openedx:22.0.2 && tutor local start -d
#
# The label `atheniq.theme.base` on the baked image records what it was built
# from, so a second run does not stack on the first: the bake is always one
# layer over the upstream image, and identical content is a cached no-op.
#
# `tutor images build openedx` still replaces that tag from source. Enable the
# `atheniqtheme` plugin (contrib/tutor-atheniq-theme) before rebuilding, so the
# rebuild carries the same theme — see docs/Deployment.md §Branding.
#
# The brand rasters are generated — run `make images` first if they are stale.
# The course photographs are the pool in `atheniq-theme/lms/static/images/courses`
# (`make course-photos`); they are served from `/static/atheniq/images/courses/`.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_SRC="${REPO}/contrib/openedx-theme-unity"
PHOTO_SRC="${REPO}/contrib/atheniq-theme/lms/static/images/courses"
LMS_CONTAINER="${LMS_CONTAINER:-tutor_local-lms-1}"
CMS_CONTAINER="${CMS_CONTAINER:-tutor_local-cms-1}"
COMPOSE_DIR="${COMPOSE_DIR:-/home/tutor/.local/share/tutor/env/local}"
THEME_NAME="unity"
THEME_ROOT="/openedx/themes/${THEME_NAME}"
STATIC_TARGET="/openedx/staticfiles/atheniq"
CMS_STATIC_TARGET="/openedx/staticfiles/studio/${THEME_NAME}/atheniq"

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
[ -d "${THEME_SRC}/lms" ] || { echo "missing theme: ${THEME_SRC}" >&2; exit 1; }
[ -d "${THEME_SRC}/cms" ] || { echo "missing theme: ${THEME_SRC}/cms" >&2; exit 1; }
for container in "${LMS_CONTAINER}" "${CMS_CONTAINER}"; do
  docker inspect "${container}" >/dev/null 2>&1 \
    || { echo "container not found: ${container}" >&2; exit 1; }
done

# Copy the local theme into the two containers. Used by --no-bake and as a
# pre-flight for the image build (a missing file fails here, not mid-recreate).
copy_lms() {
  local container="$1"
  docker exec "${container}" rm -rf "${THEME_ROOT}/lms"
  docker exec "${container}" mkdir -p "${THEME_ROOT}/lms" "${STATIC_TARGET}" \
    "${STATIC_TARGET}/images"
  docker cp "${THEME_SRC}/lms/." "${container}:${THEME_ROOT}/lms/"
  docker cp "${THEME_SRC}/lms/static/atheniq/." "${container}:${STATIC_TARGET}/"
  docker cp "${THEME_SRC}/lms/static/images/." "${container}:${STATIC_TARGET}/images/"
  if [ -d "${PHOTO_SRC}" ]; then
    docker exec "${container}" mkdir -p "${STATIC_TARGET}/images/courses"
    docker cp "${PHOTO_SRC}/." "${container}:${STATIC_TARGET}/images/courses/"
  else
    echo "warning: no course photographs in ${PHOTO_SRC}" >&2
  fi
}

copy_cms() {
  local container="$1"
  docker exec "${container}" rm -rf "${THEME_ROOT}/cms"
  docker exec "${container}" mkdir -p "${THEME_ROOT}/cms" "${CMS_STATIC_TARGET}"
  docker cp "${THEME_SRC}/cms/." "${container}:${THEME_ROOT}/cms/"
  docker cp "${THEME_SRC}/cms/static/atheniq/." "${container}:${CMS_STATIC_TARGET}/"
}

# --- bake the theme into the image ------------------------------------------
#
# The container's writable layer is not where a theme can live: `tutor local
# launch` stops and starts the platform, and a recreated container comes back
# from the image without it. One COPY layer plus a collectstatic fixes that,
# from the *upstream* image — never from the last bake, or every run would grow
# the chain. The theme's static files are collected in the build so the hashed
# copies a browser fetches are Unity's too.

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
COPY --chown=app:app openedx-theme-unity/lms/ ${THEME_ROOT}/lms/
COPY --chown=app:app openedx-theme-unity/cms/ ${THEME_ROOT}/cms/
COPY --chown=app:app openedx-theme-unity/lms/static/atheniq/ ${STATIC_TARGET}/
COPY --chown=app:app openedx-theme-unity/lms/static/images/ ${STATIC_TARGET}/images/
COPY --chown=app:app atheniq-theme/lms/static/images/courses/ ${STATIC_TARGET}/images/courses/
COPY --chown=app:app openedx-theme-unity/cms/static/atheniq/ ${CMS_STATIC_TARGET}/
RUN ./manage.py lms collectstatic --noinput --settings=tutor.assets && \\
    ./manage.py cms collectstatic --noinput --settings=tutor.assets
DOCKERFILE
  docker build --label "atheniq.theme.base=${base}" \
    -t "${image}" -f "${ctx}/Dockerfile" "${REPO}/contrib"
  rm -rf "${ctx}"

  # Prove it rather than trust the build's exit code: the paths a browser, a
  # template and a course card reach are the ones that have to be in the image.
  docker run --rm --entrypoint /bin/sh "${image}" -c \
    "test -f ${THEME_ROOT}/lms/templates/head-extra.html \
     && test -f ${THEME_ROOT}/lms/templates/footer.html \
     && test -f ${THEME_ROOT}/lms/static/css/lms-main-v1.css \
     && test -f ${THEME_ROOT}/cms/templates/widgets/header.html \
     && test -f ${THEME_ROOT}/cms/static/css/studio-main-v1.css \
     && test -f ${STATIC_TARGET}/atheniq-lms.css \
     && test -f ${STATIC_TARGET}/unity-theme.js \
     && test -f ${STATIC_TARGET}/images/courses/BUS101.jpg \
     && test -f ${CMS_STATIC_TARGET}/unity-cms.css \
     && test -d /openedx/staticfiles/${THEME_NAME}/css"
  echo "baked the Unity theme into ${image} (from ${base})"

  THEME_IMAGE="${image}"
  THEME_BASE="${base}"
}

if [ "${bake}" = "1" ]; then
  bake
else
  copy_lms "${LMS_CONTAINER}"
  copy_cms "${CMS_CONTAINER}"
  docker exec "${LMS_CONTAINER}" ./manage.py lms collectstatic --noinput --settings=tutor.assets >/dev/null
  docker exec "${CMS_CONTAINER}" ./manage.py cms collectstatic --noinput --settings=tutor.assets >/dev/null
  echo "copied the Unity theme into the running containers (not baked)"
fi

# --- recreate with the baked image ------------------------------------------
#
# A restart keeps the old image; only a recreate asks Docker for the tag again.
# `docker compose up` against the deployment's own compose files is the same
# thing `tutor local start` does, without re-running tutor's configuration.

if [ "${restart}" = "1" ]; then
  if [ "${bake}" = "1" ] && [ -f "${COMPOSE_DIR}/docker-compose.yml" ]; then
    (cd "${COMPOSE_DIR}" && COMPOSE_PROJECT_NAME=tutor_local \
      docker compose -f docker-compose.yml -f docker-compose.prod.yml \
        up -d --force-recreate --no-deps lms cms >/dev/null)
    echo "recreated ${LMS_CONTAINER} and ${CMS_CONTAINER} from the baked image"
  else
    docker restart "${LMS_CONTAINER}" "${CMS_CONTAINER}" >/dev/null
    echo "restarted ${LMS_CONTAINER} and ${CMS_CONTAINER}"
  fi
fi

cat <<'EOF'

The theme is installed at /openedx/themes/unity. Set it as the site theme once
per deployment (and after a fresh database):

    tutor local do settheme unity

The theme plugin (contrib/tutor-atheniq-theme) also sets DEFAULT_SITE_THEME, so
a site without an explicit theme row gets Unity on its own.

Note: the learner MFEs (catalog, learning, ...) render their own footer from
their compiled JS bundles. Removing the upstream badge from that footer needs an
MFE rebuild (the tutor-atheniq-mfe plugin renders the AthenIQ lockup). The Unity
palette reaches the MFEs through the stylesheet the bundles already load.
EOF

if [ "${bake}" = "1" ]; then
  cat <<EOF

The theme is part of ${THEME_IMAGE}, so recreating the containers
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
