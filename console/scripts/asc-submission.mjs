#!/usr/bin/env node
/**
 * Creates the App Store Connect draft submission for the iOS app.
 *
 * App Store Connect wants a version ("Prepare for Submission") with its
 * metadata before a build can be reviewed. This script creates or reuses that
 * version and writes the localization the app record needs: name, subtitle,
 * privacy policy, description, keywords, support and marketing URLs. It does
 * not submit for review and it does not touch screenshots — those are uploaded
 * in App Store Connect (or a later step) once they exist.
 *
 *   node scripts/asc-submission.mjs                 # show the plan, no network
 *   node scripts/asc-submission.mjs --apply         # create/update the draft
 *   node scripts/asc-submission.mjs --apply --attach-build
 *
 * Credentials are an App Store Connect Team API key with the App Manager (or
 * Admin) role, read from:
 *   ASC_KEY_ID       key ID
 *   ASC_ISSUER_ID    issuer UUID
 *   ASC_PRIVATE_KEY  the .p8 contents, or ASC_KEY_PATH pointing at the file
 *
 * Metadata lives in console/mobile/store/submission.json so the copy is
 * reviewable in the repository instead of being typed into a web form.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const API = "https://api.appstoreconnect.apple.com/v1";
const args = new Set(process.argv.slice(2));
const APPLY = args.has("--apply");
const ATTACH_BUILD = args.has("--attach-build");
// Found from this file, not the working directory: the workflow runs at the
// repository root, and after the merge the copy sits beside the app it describes.
const META_PATH =
  process.env.SUBMISSION_METADATA ||
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "mobile", "store", "submission.json");

const meta = JSON.parse(fs.readFileSync(META_PATH, "utf8"));
const log = (...parts) => console.log(...parts);
const warn = (...parts) => console.warn("warning:", ...parts);

function fail(message) {
  console.error(`\n${message}\n`);
  process.exit(1);
}

function readKey() {
  if (process.env.ASC_PRIVATE_KEY) return process.env.ASC_PRIVATE_KEY;
  if (process.env.ASC_KEY_PATH) return fs.readFileSync(process.env.ASC_KEY_PATH, "utf8");
  return "";
}

/**
 * App Store Connect only accepts ES256 JWTs, and Node signs them in DER unless
 * it is told otherwise — the raw R||S form is what Apple verifies.
 */
function bearerToken() {
  const key = readKey();
  const keyId = process.env.ASC_KEY_ID || "";
  const issuer = process.env.ASC_ISSUER_ID || "";
  const missing = [!key && "ASC_PRIVATE_KEY (or ASC_KEY_PATH)", !keyId && "ASC_KEY_ID", !issuer && "ASC_ISSUER_ID"].filter(Boolean);
  if (missing.length) {
    fail(`Missing Apple credentials: ${missing.join(", ")}.\nAdd them as repository secrets or export them locally; see README "App Store draft submission".`);
  }
  if (!key.includes("BEGIN PRIVATE KEY")) {
    fail("ASC_PRIVATE_KEY is not a .p8 key. It must be the whole block, BEGIN/END lines included (a truncated paste is the usual cause).");
  }
  const now = Math.floor(Date.now() / 1000);
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const header = encode({ alg: "ES256", kid: keyId, typ: "JWT" });
  const payload = encode({ iss: issuer, iat: now, exp: now + 900, aud: "appstoreconnect-v1" });
  const signature = crypto
    .createSign("SHA256")
    .update(`${header}.${payload}`)
    .sign({ key, dsaEncoding: "ieee-p1363" })
    .toString("base64url");
  return `${header}.${payload}.${signature}`;
}

let token = "";
async function call(method, path, body) {
  if (!token) token = bearerToken();
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = (data.errors || []).map((error) => `${error.title}: ${error.detail ?? ""}`).join("; ");
    throw new Error(`${method} ${path} failed (${response.status}) — ${detail || text}`);
  }
  return data;
}

const OPEN_STATES = ["PREPARE_FOR_SUBMISSION", "METADATA_REJECTED", "DEVELOPER_REJECTED", "REJECTED"];

function versionAttributes() {
  const attributes = {
    description: meta.description,
    keywords: meta.keywords,
    supportUrl: meta.supportUrl,
    marketingUrl: meta.marketingUrl,
    promotionalText: meta.promotionalText,
  };
  if (meta.whatsNew) attributes.whatsNew = meta.whatsNew;
  return attributes;
}

function printPlan() {
  log(`App        ${meta.name} (${meta.appId}), bundle ${meta.bundleId}, team ${meta.teamId}`);
  log(`Version    ${meta.version}, locale ${meta.locale}, category ${meta.primaryCategory}`);
  log(`Privacy    ${meta.privacyPolicyUrl}`);
  log(`Support    ${meta.supportUrl}`);
  log("");
  log("Would do, in order:");
  log(`  1. GET  /apps/${meta.appId} and check the bundle identifier is ${meta.bundleId}`);
  log(`  2. find an IOS version in ${OPEN_STATES.join("/")}, or POST /appStoreVersions (${meta.version})`);
  log(`  3. POST or PATCH /appStoreVersionLocalizations (${meta.locale}): description, keywords, support, marketing`);
  log(`  4. POST or PATCH /appInfoLocalizations (${meta.locale}): name, subtitle, privacy policy URL`);
  log(`  5. PATCH /appInfos/:id primaryCategory ${meta.primaryCategory}`);
  if (ATTACH_BUILD) log("  6. attach the newest processed build to the version");
  log("\nNothing was sent. Re-run with --apply to write it to App Store Connect.");
}

async function findOrCreateVersion() {
  const versions = await call(
    "GET",
    `/apps/${meta.appId}/appStoreVersions?filter[platform]=IOS&limit=20&fields[appStoreVersions]=versionString,appStoreState,createdDate`,
  );
  const open = versions.data.find(
    (item) => OPEN_STATES.includes(item.attributes.appStoreState) && item.attributes.versionString === meta.version,
  ) ?? versions.data.find((item) => OPEN_STATES.includes(item.attributes.appStoreState));

  if (open) {
    log(`version ${open.attributes.versionString} already open (${open.attributes.appStoreState}); reusing it`);
    return open;
  }

  const created = await call("POST", "/appStoreVersions", {
    data: {
      type: "appStoreVersions",
      attributes: { platform: "IOS", versionString: meta.version, releaseType: "MANUAL" },
      relationships: { app: { data: { type: "apps", id: meta.appId } } },
    },
  });
  log(`created version ${meta.version} (${created.data.id})`);
  return created.data;
}

async function writeVersionLocalization(versionId) {
  const list = await call("GET", `/appStoreVersions/${versionId}/appStoreVersionLocalizations?limit=50`);
  const existing = list.data.find((item) => item.attributes.locale === meta.locale);
  const attributes = versionAttributes();

  if (existing) {
    await call("PATCH", `/appStoreVersionLocalizations/${existing.id}`, {
      data: { type: "appStoreVersionLocalizations", id: existing.id, attributes },
    });
    log(`updated ${meta.locale} version metadata`);
    return;
  }
  await call("POST", "/appStoreVersionLocalizations", {
    data: {
      type: "appStoreVersionLocalizations",
      attributes: { locale: meta.locale, ...attributes },
      relationships: { version: { data: { type: "appStoreVersions", id: versionId } } },
    },
  });
  log(`created ${meta.locale} version metadata`);
}

async function writeAppInfo() {
  const infos = await call("GET", `/apps/${meta.appId}/appInfos?limit=5&fields[appInfos]=state`);
  const info = infos.data[0];
  if (!info) {
    warn("the app has no appInfo yet, so name, subtitle and privacy policy were skipped");
    return;
  }

  const list = await call("GET", `/appInfos/${info.id}/appInfoLocalizations?limit=50`);
  const existing = list.data.find((item) => item.attributes.locale === meta.locale);
  const attributes = { name: meta.name, subtitle: meta.subtitle, privacyPolicyUrl: meta.privacyPolicyUrl };

  if (existing) {
    await call("PATCH", `/appInfoLocalizations/${existing.id}`, {
      data: { type: "appInfoLocalizations", id: existing.id, attributes },
    });
    log(`updated ${meta.locale} app name, subtitle and privacy policy`);
  } else {
    await call("POST", "/appInfoLocalizations", {
      data: {
        type: "appInfoLocalizations",
        attributes: { locale: meta.locale, ...attributes },
        relationships: { appInfo: { data: { type: "appInfos", id: info.id } } },
      },
    });
    log(`created ${meta.locale} app name, subtitle and privacy policy`);
  }

  // Category is a relationship on appInfo; a wrong id is not worth failing the
  // whole draft for, so it warns and continues.
  try {
    await call("PATCH", `/appInfos/${info.id}`, {
      data: {
        type: "appInfos",
        id: info.id,
        relationships: { primaryCategory: { data: { type: "appCategories", id: meta.primaryCategory } } },
      },
    });
    log(`primary category ${meta.primaryCategory}`);
  } catch (error) {
    warn(`could not set category ${meta.primaryCategory}: ${error.message}`);
  }
}

async function attachNewestBuild(versionId) {
  const builds = await call(
    "GET",
    `/builds?filter[app]=${meta.appId}&filter[processingState]=VALID&sort=-uploadedDate&limit=1&fields[builds]=version,processingState,uploadedDate`,
  );
  const build = builds.data[0];
  if (!build) {
    warn("no processed build yet; run the iOS TestFlight workflow first, then re-run with --attach-build");
    return;
  }
  await call("PATCH", `/appStoreVersions/${versionId}`, {
    data: {
      type: "appStoreVersions",
      id: versionId,
      relationships: { build: { data: { type: "builds", id: build.id } } },
    },
  });
  log(`attached build ${build.attributes.version} (uploaded ${build.attributes.uploadedDate})`);
}

async function main() {
  log(`${meta.name} ${meta.version} → App Store Connect app ${meta.appId} (${meta.bundleId})`);
  if (!APPLY) {
    printPlan();
    return;
  }

  const app = await call("GET", `/apps/${meta.appId}?fields[apps]=name,bundleId,sku`);
  const bundleId = app.data.attributes.bundleId;
  if (bundleId !== meta.bundleId) {
    fail(`App ${meta.appId} is registered as ${bundleId}, not ${meta.bundleId}. An upload would be rejected; fix the record or the metadata.`);
  }
  log(`app record confirmed: ${app.data.attributes.name} (${bundleId})`);

  const version = await findOrCreateVersion();
  await writeVersionLocalization(version.id);
  await writeAppInfo();
  if (ATTACH_BUILD) await attachNewestBuild(version.id);

  const after = await call("GET", `/appStoreVersions/${version.id}?fields[appStoreVersions]=versionString,appStoreState`);
  log("");
  log(`draft ready: ${after.data.attributes.versionString} (${after.data.attributes.appStoreState})`);
  log(`https://appstoreconnect.apple.com/apps/${meta.appId}/distribution/ios/version/inflight`);
  log("Screenshots and the review submission itself are still manual.");
}

main().catch((error) => fail(error.message));
