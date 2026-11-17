#!/bin/sh
# Rebuild the console image on the console host itself.
#
#   ./deploy/rebuild-on-host.sh [source-dir]
#
# The host has 1.28 GB of RAM and no swap (it is an Incus container, so swapon is
# refused). `next build` inside `docker build` is killed there. So the compile
# runs in a Node container with a capped heap — one process, one worker — and the
# runtime image is built from the output. Nothing is compiled twice and no image
# has to be shipped from another machine.
set -eu

SRC="${1:-$(pwd)}"
HEAP_MB="${BUILD_HEAP_MB:-768}"
IMAGE="${IMAGE:-atheniq-console:deploy}"

cd "$SRC"
echo "== source: $SRC"
test -f package.json
test -f Dockerfile.runtime

echo "== compile (heap ${HEAP_MB} MB, one worker)"
docker run --rm \
  -v "$SRC:/app" \
  -w /app \
  -e NODE_OPTIONS="--max-old-space-size=${HEAP_MB}" \
  -e NEXT_TELEMETRY_DISABLED=1 \
  node:22-alpine \
  sh -c 'npm ci --no-audit --no-fund && npm run build'

echo "== package runtime image"
docker build -f Dockerfile.runtime -t "$IMAGE" .
echo "== built $IMAGE"
