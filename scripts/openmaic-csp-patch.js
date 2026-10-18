// Add or update the frame-ancestors allowlist inside the running OpenMAIC
// container — for when a rename cannot wait for an image rebuild.
//
// `ALLOWED_FRAME_ANCESTORS` is read by `next.config.ts`, so every origin a
// course unit is served from is compiled into `.next/routes-manifest.json` at
// build time; a runtime environment variable cannot change it. Rewriting the
// manifest is the same shape of one-time in-container patch the runbook uses for
// other baked-in upstream values — the next `docker compose build openmaic`
// (with `ALLOWED_FRAME_ANCESTORS` set in `services/OpenMAIC/.env`) replaces it.
//
//   docker cp scripts/openmaic-csp-patch.js openmaic-openmaic-1:/tmp/patch.js
//   docker exec -u root openmaic-openmaic-1 node /tmp/patch.js
//   docker restart openmaic-openmaic-1
//
// Then keep it across container recreates by committing the patched container
// as the image the compose project uses (see docs/Deployment.md).
const fs = require('fs');

const MANIFEST = '/app/.next/routes-manifest.json';
// Every origin a learner can be served a course unit from: the canonical pair
// and the aliases kept in front of the same application.
const ADD = [
  'https://learn.innotel.us',
  'https://apps.learn.innotel.us',
  'https://lms.innotel.us',
  'https://apps.lms.innotel.us',
  'https://atheniq.innotel.us',
];

const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
const changed = [];
for (const rule of manifest.headers || []) {
  for (const header of rule.headers || []) {
    if (header.key !== 'Content-Security-Policy') continue;
    if (!header.value || !header.value.includes('frame-ancestors')) continue;
    const missing = ADD.filter((origin) => !header.value.includes(origin));
    if (missing.length === 0) continue;
    header.value = header.value.trimEnd() + ' ' + missing.join(' ');
    changed.push(header.value);
  }
}

if (changed.length === 0) {
  console.log('already allowed: ' + MANIFEST);
  process.exit(0);
}

const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15);
const backup = MANIFEST + '.bak-' + stamp;
fs.copyFileSync(MANIFEST, backup);
fs.writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2));
console.log('patched: ' + MANIFEST);
console.log('backup:  ' + backup);
changed.forEach((value) => console.log('now:     ' + value));
