#!/usr/bin/env bash
check() { docker exec tutor_local-caddy-1 wget -qS -O /dev/null --header="Host: studio.innotel.us" "http://localhost$1" 2>&1 | head -1; }
for p in /static/studio/atheniq/unity-cms.css /static/studio/atheniq/unity-theme.css /static/indigo/atheniq/unity-cms.css; do
  echo -n "$p -> "; check "$p"
done
docker exec tutor_local-cms-1 ls -d /openedx/staticfiles/studio /openedx/staticfiles/studio/atheniq 2>&1
