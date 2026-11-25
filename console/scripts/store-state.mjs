#!/usr/bin/env node
/**
 * store-state.mjs — one record of what Apple holds for this app, and the checks
 * that keep the repository honest about it.
 *
 * `store.json` at the repository root is the single source: the App Store
 * workflow reads its app id, version id and build instead of carrying copies;
 * the listing document carries a block generated from it; and the scheduled job
 * reads the same file and asks Apple whether it is still true.
 *
 *   node console/scripts/store-state.mjs                 # check the record and the listing block
 *   node console/scripts/store-state.mjs --write         # rewrite the listing block from store.json
 *   node console/scripts/store-state.mjs --verify-live   # ask App Store Connect and compare
 *   node console/scripts/store-state.mjs --github-env    # print APP_ID/VERSION_ID/BUILD_NUMBER for $GITHUB_ENV
 *
 * `--verify-live` needs ASC_KEY_ID, ASC_ISSUER_ID and ASC_PRIVATE_KEY, and only
 * ever issues GETs: this file cannot change anything at Apple.
 */

import { createPrivateKey, sign } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const API = 'https://api.appstoreconnect.apple.com';
const HERE = dirname(fileURLToPath(import.meta.url));

const argv = process.argv.slice(2);
const has = (name) => argv.includes(name);
const value = (name) => {
  const i = argv.indexOf(name);
  return i >= 0 ? argv[i + 1] : null;
};

const WRITE = has('--write');
const VERIFY_LIVE = has('--verify-live');
const GITHUB_ENV = has('--github-env');
const SUMMARY = value('--summary');

/** The App Store states a version can be in, as App Store Connect spells them. */
const STATES = [
  'PREPARE_FOR_SUBMISSION',
  'READY_FOR_SUBMISSION',
  'WAITING_FOR_REVIEW',
  'IN_REVIEW',
  'UNRESOLVED_ISSUES',
  'PENDING_DEVELOPER_RELEASE',
  'PENDING_APPLE_RELEASE',
  'PROCESSING_FOR_DISTRIBUTION',
  'READY_FOR_SALE',
  'DEVELOPER_REJECTED',
  'REJECTED',
  'METADATA_REJECTED',
  'INVALID_BINARY',
  'REPLACED_WITH_NEW_VERSION',
];

/** True when one version string is newer than another, numerically, segment by segment. */
function newer(a, b) {
  const pa = String(a).split('.').map(Number);
  const pb = String(b).split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d !== 0) return d > 0 ? 1 : -1;
  }
  return 0;
}

/** Walk up to the checkout root, so the script works from any working directory. */
function repoRoot() {
  let dir = HERE;
  for (;;) {
    if (existsSync(join(dir, '.git'))) return dir;
    const up = dirname(dir);
    if (up === dir) return process.cwd();
    dir = up;
  }
}

const ROOT = repoRoot();
const STORE_PATH = join(ROOT, 'store.json');

function die(message) {
  console.error(`::error::${message}`);
  process.exit(1);
}

if (!existsSync(STORE_PATH)) die(`no store.json at ${STORE_PATH}`);
let store;
try {
  store = JSON.parse(readFileSync(STORE_PATH, 'utf8'));
} catch (err) {
  die(`store.json is not valid JSON: ${err.message}`);
}

// ---------------------------------------------------------------- the record

// versionId and whatsNew are optional: the version is always resolved from
// `version`, and a version that carries no release notes has nothing to record.
const REQUIRED = ['app', 'appId', 'bundleId', 'version', 'build', 'state', 'listingDoc'];

function checkRecord() {
  const problems = [];
  for (const key of REQUIRED) {
    if (store[key] === undefined || store[key] === null || store[key] === '') {
      problems.push(`store.json is missing "${key}"`);
    }
  }
  if (store.platform && store.platform !== 'IOS') {
    problems.push(`store.json says platform ${store.platform}; this job reads the IOS version list`);
  }
  if (store.version && !/^\d+(\.\d+){0,2}$/.test(String(store.version))) {
    problems.push(`store.json version "${store.version}" is not a version string like 1.1 or 1.0.0`);
  }
  if (store.build && !/^\d+$/.test(String(store.build))) {
    problems.push(`store.json build "${store.build}" is not a build number`);
  }
  if (store.state && !STATES.includes(store.state)) {
    problems.push(`store.json state "${store.state}" is not an App Store version state (${STATES.join(', ')})`);
  }
  if (store.notes !== undefined && typeof store.notes !== 'string') {
    problems.push('store.json "notes" must be a string');
  }
  if (typeof store.whatsNew === 'string' && store.whatsNew.length > 4000) {
    problems.push(`store.json whatsNew is ${store.whatsNew.length} characters; App Store Connect allows 4000`);
  }
  return problems;
}

// -------------------------------------------------------------- listing doc

const BEGIN_PREFIX = '<!-- store-state:begin';
const END_MARK = '<!-- store-state:end -->';
const BLOCK_HEADER =
  `${BEGIN_PREFIX} — generated from store.json; edit that file, then run the ` +
  'store-state script with --write -->';

/** The block a listing document carries so a reader sees exactly what store.json says. */
function renderBlock(s) {
  const rows = [
    '| What App Store Connect holds | Value |',
    '| --- | --- |',
    `| App | \`${s.app}\` — app id \`${s.appId}\`, bundle \`${s.bundleId}\` |`,
    `| Version | \`${s.version}\` |`,
    `| Build | \`${s.build}\` |`,
    `| State | \`${s.state}\` |`,
    s.versionId ? `| Version id | \`${s.versionId}\` |` : null,
    `| Released | ${s.releasedAt || 'not recorded'} |`,
    typeof s.whatsNew === 'string' ? `| What's New | ${s.whatsNew.length} characters |` : null,
  ].filter(Boolean);
  return [BLOCK_HEADER, ...rows, END_MARK].join('\n');
}

function listingPath() {
  return resolve(ROOT, store.listingDoc);
}

function readListing() {
  const path = listingPath();
  if (!existsSync(path)) die(`store.json points at ${store.listingDoc}, which is not in the checkout`);
  return { path, body: readFileSync(path, 'utf8') };
}

/**
 * The listing is either a Markdown document carrying the generated block, or a
 * JSON copy of the store metadata. Both have to agree with store.json on the
 * version, and on the What's New copy where they hold one.
 */
function checkListing() {
  const problems = [];
  const { path, body } = readListing();

  if (path.endsWith('.json')) {
    let listing;
    try {
      listing = JSON.parse(body);
    } catch (err) {
      return [`${store.listingDoc} is not valid JSON: ${err.message}`];
    }
    for (const key of ['version', 'whatsNew']) {
      if (listing[key] === undefined || store[key] === undefined) continue;
      if (String(listing[key]) !== String(store[key])) {
        problems.push(`${store.listingDoc} has ${key} "${listing[key]}"; store.json says "${store[key]}"`);
      }
    }
    if (listing.appId !== undefined && String(listing.appId) !== String(store.appId)) {
      problems.push(`${store.listingDoc} is for app ${listing.appId}; store.json says ${store.appId}`);
    }
    return problems;
  }

  if (store.listingBlock === false) return problems;

  const start = body.indexOf(BEGIN_PREFIX);
  const end = body.indexOf(END_MARK);
  if (start < 0 || end < start) {
    problems.push(
      `${store.listingDoc} has no generated store-state block; add one between ` +
        `"${BEGIN_PREFIX} … -->" and "${END_MARK}", then run this script with --write`
    );
    return problems;
  }
  const found = body.slice(start, end + END_MARK.length);
  const expected = renderBlock(store);
  if (found !== expected) {
    problems.push(
      `${store.listingDoc} disagrees with store.json; run \`node ${scriptPath()} --write\` to regenerate the block`
    );
  }
  return problems;
}

function scriptPath() {
  return fileURLToPath(import.meta.url).slice(ROOT.length + 1);
}

function writeListingBlock() {
  const path = listingPath();
  if (path.endsWith('.json') || store.listingBlock === false) {
    die(`${store.listingDoc} has no generated block to write; only the JSON checks apply`);
  }
  if (!existsSync(path)) die(`store.json points at ${store.listingDoc}, which is not in the checkout`);
  const body = readFileSync(path, 'utf8');
  const start = body.indexOf(BEGIN_PREFIX);
  const end = body.indexOf(END_MARK);
  if (start < 0 || end < start) die(`${store.listingDoc} has no store-state block markers to replace`);
  const next = body.slice(0, start) + renderBlock(store) + body.slice(end + END_MARK.length);
  if (next === body) {
    console.log(`${store.listingDoc} already matches store.json; nothing written`);
    return;
  }
  writeFileSync(path, next);
  console.log(`${store.listingDoc} regenerated from store.json`);
}

// ------------------------------------------------------- live, read-only

const keyId = (process.env.ASC_KEY_ID || '').trim();
const issuer = (process.env.ASC_ISSUER_ID || '').trim();
const pem = (process.env.ASC_PRIVATE_KEY || '').replace(/\\n/g, '\n').trim();

let token = null;
function bearer() {
  if (token) return token;
  const key = createPrivateKey({ key: pem, format: 'pem' });
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const now = Math.floor(Date.now() / 1000);
  const head = b64({ alg: 'ES256', kid: keyId, typ: 'JWT' });
  const body = b64({ iss: issuer, iat: now, exp: now + 900, aud: 'appstoreconnect-v1' });
  const sig = sign('sha256', Buffer.from(`${head}.${body}`), { key, dsaEncoding: 'ieee-p1363' }).toString(
    'base64url'
  );
  token = `${head}.${body}.${sig}`;
  return token;
}

/** GET only. There is no write path in this file, by design. */
async function get(path) {
  const res = await fetch(`${API}${path}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${bearer()}`, 'Content-Type': 'application/json' },
  });
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    die(`GET ${path} -> ${res.status} ${typeof body === 'string' ? body : JSON.stringify(body?.errors ?? body)}`);
  }
  return body;
}

async function checkLive() {
  if (!keyId || !issuer || !pem) {
    die('ASC_KEY_ID, ASC_ISSUER_ID and ASC_PRIVATE_KEY are all needed to read App Store Connect');
  }
  const problems = [];
  const list = await get(
    `/v1/apps/${store.appId}/appStoreVersions?filter[platform]=IOS` +
      '&fields[appStoreVersions]=versionString,appStoreState&limit=50'
  );
  const versions = list?.data || [];
  console.log(`Apple holds ${versions.length} IOS version(s) of app ${store.appId}`);

  const mine = versions.find((v) => v.attributes.versionString === String(store.version));
  if (!mine) {
    const held = versions.map((v) => `${v.attributes.versionString} (${v.attributes.appStoreState})`).join(', ');
    problems.push(`Apple has no ${store.version}; it holds ${held || 'nothing'}`);
  } else {
    const detail = await get(
      `/v1/appStoreVersions/${mine.id}?include=build` +
        '&fields[appStoreVersions]=versionString,appStoreState&fields[builds]=version,processingState'
    );
    const state = detail.data.attributes.appStoreState;
    const build = detail.included?.find((i) => i.type === 'builds')?.attributes.version ?? 'none';
    console.log(`read back ${store.version} (${mine.id}): ${state}, build ${build}`);
    if (state !== store.state) {
      problems.push(`store.json says ${store.version} is ${store.state}; Apple says ${state}`);
    }
    if (build !== String(store.build)) {
      problems.push(`store.json says ${store.version} is on build ${store.build}; Apple has build ${build} attached`);
    }
    if (store.versionId && mine.id !== store.versionId) {
      problems.push(`store.json pins version id ${store.versionId}; Apple has ${mine.id} for ${store.version}`);
    }
  }

  const newest = [...versions].sort((a, b) =>
    newer(a.attributes.versionString, b.attributes.versionString)
  ).pop();
  if (newest && newer(newest.attributes.versionString, store.version) > 0) {
    problems.push(
      `Apple holds a newer version, ${newest.attributes.versionString} ` +
        `(${newest.attributes.appStoreState}); store.json still says ${store.version}`
    );
  }
  return problems;
}

// -------------------------------------------------------------------- main

function summary(lines) {
  const text = `${lines.join('\n')}\n`;
  if (SUMMARY) writeFileSync(SUMMARY, text, { flag: 'a' });
  process.stdout.write(text);
}

if (GITHUB_ENV) {
  const lines = checkRecord();
  if (lines.length) die(lines.join('; '));
  process.stdout.write(`APP_ID=${store.appId}\nVERSION_ID=${store.versionId}\nBUILD_NUMBER=${store.build}\n`);
  process.exit(0);
}

if (WRITE) {
  const problems = checkRecord();
  if (problems.length) die(problems.join('; '));
  writeListingBlock();
  process.exit(0);
}

const problems = [...checkRecord(), ...checkListing()];

if (!VERIFY_LIVE) {
  if (problems.length) {
    for (const problem of problems) console.error(`::error::${problem}`);
    process.exit(1);
  }
  console.log(
    `store.json and ${store.listingDoc} agree: ${store.app} ${store.version} (build ${store.build}) is ${store.state}`
  );
  process.exit(0);
}

const live = await checkLive();
const all = [...problems, ...live];
summary([
  `# Store state — ${store.app}`,
  '',
  all.length
    ? `store.json no longer matches what App Store Connect holds for **${store.app}**. Nothing was written; update \`store.json\` (and the listing block) to match.`
    : `store.json agrees with App Store Connect: **${store.version}** (build ${store.build}) is \`${store.state}\`.`,
  ...(all.length ? ['', ...all.map((p) => `- ${p}`)] : []),
  '',
]);
for (const problem of all) console.error(`::error::${problem}`);
process.exit(all.length ? 1 : 0);
