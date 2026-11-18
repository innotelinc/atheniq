#!/usr/bin/env node
/**
 * Uploads the 6.9-inch iPhone screenshot set to the App Store Connect draft.
 *
 * A version cannot be submitted without screenshots, and they are per display
 * size, not per device: the 6.9-inch canvas (1320×2868 portrait, what an iPhone
 * 16 Pro Max simulator captures) uploads into APP_IPHONE_67, because Apple never
 * added a 69 display type and the API answers 409 for anything it does not list.
 * The workflow `.github/workflows/ios-screenshots.yml` takes the frames; this
 * puts them in.
 *
 *   node scripts/asc-screenshots.mjs --dir screenshots            # show the plan
 *   node scripts/asc-screenshots.mjs --dir screenshots --apply    # replace the set
 *
 * The draft version must already exist (run `asc-submission.mjs --apply` first),
 * and the same three App Store Connect secrets are used:
 *   ASC_KEY_ID, ASC_ISSUER_ID, ASC_PRIVATE_KEY (or ASC_KEY_PATH).
 */
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const API = "https://api.appstoreconnect.apple.com/v1";
// The 6.7/6.9-inch display family: APP_IPHONE_67 accepts 1320×2868 as well as
// 1290×2796, and it is the only one of the two the API will take.
const args = process.argv.slice(2);
const APPLY = args.includes("--apply");
// Read-only: what Apple has done with the set that is already there. The upload
// path reports the state it finds a moment after the bytes land, which is
// UPLOAD_COMPLETE while Apple is still checking the images — this answers the
// question that comes later, without touching the listing.
const STATUS = args.includes("--status");
const valueAfter = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};
const DIR = valueAfter("--dir") || "screenshots";
/** Which display slot this run fills. The iPhone set does not satisfy an iPad app. */
const DISPLAY = valueAfter("--display") || "APP_IPHONE_67";
const DISPLAY_SIZES = {
  APP_IPHONE_67: ["1320x2868", "1290x2796", "2868x1320"],
  APP_IPAD_PRO_3GEN_129: ["2064x2752", "2048x2732", "2752x2064"],
};
// Read after the table above exists: referring to either of those consts in the
// line that used to sit at the top of the file threw a temporal-dead-zone
// ReferenceError, which is how the upload failed on a set that was already
// captured.
const EXPECTED = DISPLAY_SIZES[DISPLAY] ?? DISPLAY_SIZES.APP_IPHONE_67;
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

/** PNG IHDR, so a wrong-size set fails here instead of inside Apple's API. */
function pixelSize(file) {
  const buffer = fs.readFileSync(file);
  if (buffer.toString("ascii", 1, 4) !== "PNG") return null;
  return `${buffer.readUInt32BE(16)}x${buffer.readUInt32BE(20)}`;
}

function screenshots() {
  if (!fs.existsSync(DIR)) fail(`No screenshots in ${DIR}. Run the iOS screenshots workflow, or point --dir at a folder of PNGs.`);
  const files = fs
    .readdirSync(DIR)
    .filter((name) => name.toLowerCase().endsWith(".png"))
    .sort()
    .map((name) => path.join(DIR, name));
  if (!files.length) fail(`${DIR} has no PNG files.`);
  for (const file of files) {
    const size = pixelSize(file);
    if (!size) fail(`${file} is not a PNG.`);
    if (!EXPECTED.includes(size)) {
      fail(`${file} is ${size}; the 6.9-inch set needs ${EXPECTED.join(" or ")}. That is what an iPhone 16 Pro Max simulator captures.`);
    }
  }
  return files;
}

function readKey() {
  if (process.env.ASC_PRIVATE_KEY) return process.env.ASC_PRIVATE_KEY;
  if (process.env.ASC_KEY_PATH) return fs.readFileSync(process.env.ASC_KEY_PATH, "utf8");
  return "";
}

/** App Store Connect only accepts ES256 JWTs in raw R||S form, not DER. */
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
async function call(method, requestPath, body) {
  if (!token) token = bearerToken();
  // App Store Connect 500s on reads that succeed a moment later; the iPad set
  // was lost that way after the iPhone set had already gone in. Retrying the
  // request is what makes a run finish the job it started.
  const attempts = 4;
  for (let attempt = 1; ; attempt += 1) {
    const response = await fetch(`${API}${requestPath}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    if (response.ok) return data;
    const detail = (data.errors || []).map((error) => `${error.title}: ${error.detail ?? ""}`).join("; ");
    const retryable = response.status === 429 || response.status >= 500;
    if (retryable && attempt < attempts) {
      warn(`${method} ${requestPath} failed (${response.status}); retrying (${attempt}/${attempts - 1})`);
      await new Promise((resolve) => setTimeout(resolve, attempt * 2000));
      continue;
    }
    throw new Error(`${method} ${requestPath} failed (${response.status}) — ${detail || text}`);
  }
}

const OPEN_STATES = ["PREPARE_FOR_SUBMISSION", "METADATA_REJECTED", "DEVELOPER_REJECTED", "REJECTED"];

async function findDraftVersion() {
  const versions = await call(
    "GET",
    `/apps/${meta.appId}/appStoreVersions?filter[platform]=IOS&limit=50&fields[appStoreVersions]=versionString,appStoreState`,
  );
  const open =
    versions.data.find((item) => OPEN_STATES.includes(item.attributes.appStoreState) && item.attributes.versionString === meta.version) ??
    versions.data.find((item) => OPEN_STATES.includes(item.attributes.appStoreState));
  if (!open) {
    fail(`No ${meta.version} draft in ${OPEN_STATES.join("/")}. Run "node scripts/asc-submission.mjs --apply" first — screenshots hang off the version.`);
  }
  log(`draft version ${open.attributes.versionString} (${open.attributes.appStoreState})`);
  return open;
}

async function findLocalization(versionId) {
  const list = await call("GET", `/appStoreVersions/${versionId}/appStoreVersionLocalizations?limit=50&fields[appStoreVersionLocalizations]=locale`);
  const existing = list.data.find((item) => item.attributes.locale === meta.locale);
  if (!existing) fail(`The draft has no ${meta.locale} localization; run asc-submission.mjs --apply to create it.`);
  return existing;
}

async function ensureScreenshotSet(localizationId) {
  const sets = await call(
    "GET",
    `/appStoreVersionLocalizations/${localizationId}/appScreenshotSets?limit=50&fields[appScreenshotSets]=screenshotDisplayType`,
  );
  const existing = sets.data.find((item) => item.attributes.screenshotDisplayType === DISPLAY);
  if (existing) {
    log(`screenshot set ${DISPLAY} exists (${existing.id})`);
    return existing;
  }
  const created = await call("POST", "/appScreenshotSets", {
    data: {
      type: "appScreenshotSets",
      attributes: { screenshotDisplayType: DISPLAY },
      relationships: { appStoreVersionLocalization: { data: { type: "appStoreVersionLocalizations", id: localizationId } } },
    },
  });
  log(`created screenshot set ${DISPLAY}`);
  return created.data;
}

async function clearSet(setId) {
  const listed = await call("GET", `/appScreenshotSets/${setId}/appScreenshots?limit=50&fields[appScreenshots]=fileName,assetDeliveryState`);
  for (const shot of listed.data) {
    await call("DELETE", `/appScreenshots/${shot.id}`);
    log(`removed ${shot.attributes.fileName}`);
  }
}

async function uploadOne(setId, file) {
  const fileName = path.basename(file);
  const bytes = fs.readFileSync(file);
  const created = await call("POST", "/appScreenshots", {
    data: {
      type: "appScreenshots",
      attributes: { fileName, fileSize: bytes.length },
      relationships: { appScreenshotSet: { data: { type: "appScreenshotSets", id: setId } } },
    },
  });
  const shot = created.data;
  const operations = shot.attributes.uploadOperations || [];
  if (!operations.length) fail(`Apple returned no upload operations for ${fileName}.`);

  for (const operation of operations) {
    const headers = {};
    for (const header of operation.requestHeaders || []) headers[header.name] = header.value;
    const chunk = bytes.subarray(operation.offset, operation.offset + operation.length);
    const response = await fetch(operation.url, { method: operation.method || "PUT", headers, body: chunk });
    if (!response.ok) {
      const detail = await response.text();
      fail(`Uploading ${fileName} failed at offset ${operation.offset} (${response.status}) — ${detail.slice(0, 300)}`);
    }
  }

  await call("PATCH", `/appScreenshots/${shot.id}`, {
    data: { type: "appScreenshots", id: shot.id, attributes: { uploaded: true } },
  });
  log(`uploaded ${fileName} (${bytes.length} bytes)`);
  return shot.id;
}

async function stateOf(shotId) {
  const shot = await call("GET", `/appScreenshots/${shotId}?fields[appScreenshots]=fileName,assetDeliveryState`);
  return shot.data.attributes.assetDeliveryState?.state || "UNKNOWN";
}

async function reportStatus() {
  const version = await findDraftVersion();
  const localization = await findLocalization(version.id);
  const sets = await call(
    "GET",
    `/appStoreVersionLocalizations/${localization.id}/appScreenshotSets?limit=20&fields[appScreenshotSets]=screenshotDisplayType`,
  );
  const set = sets.data.find((item) => item.attributes.screenshotDisplayType === DISPLAY);
  log(`${meta.name} ${meta.version} → ${DISPLAY}`);
  if (!set) {
    fail(`The draft has no ${DISPLAY} screenshot set. Upload one first (--apply).`);
  }
  const listed = await call(
    "GET",
    `/appScreenshotSets/${set.id}/appScreenshots?limit=50&fields[appScreenshots]=fileName,assetDeliveryState`,
  );
  let pending = 0;
  let failed = 0;
  for (const shot of listed.data) {
    const state = shot.attributes.assetDeliveryState?.state || "UNKNOWN";
    const errors = (shot.attributes.assetDeliveryState?.errors || []).map((error) => error.code || error.description);
    log(`  ${shot.attributes.fileName.padEnd(22)} ${state}${errors.length ? ` — ${errors.join(", ")}` : ""}`);
    if (state === "FAILED") failed += 1;
    else if (state !== "COMPLETE") pending += 1;
  }
  log("");
  log(`screenshot set ${DISPLAY}: ${listed.data.length} image(s), ${listed.data.length - pending - failed} complete, ${pending} still processing, ${failed} failed`);
  if (failed) fail(`${failed} image(s) failed Apple's checks; open the set in App Store Connect.`);
  if (pending) log("Apple is still processing; re-run --status in a few minutes.");
}

async function main() {
  if (STATUS) return reportStatus();
  const files = screenshots();
  log(`${meta.name} ${meta.version} → ${DISPLAY}, ${files.length} screenshot(s) from ${DIR}`);
  for (const file of files) log(`  ${path.basename(file)} ${pixelSize(file)}`);

  if (!APPLY) {
    log("");
    log("Would do, in order:");
    log(`  1. find the ${meta.version} draft in ${OPEN_STATES.join("/")}`);
    log(`  2. find or create the ${DISPLAY} screenshot set on the ${meta.locale} localization`);
    log("  3. DELETE every screenshot already in that set");
    log("  4. POST, PUT the asset, and PATCH uploaded:true for each file, in name order");
    log("\nNothing was sent. Re-run with --apply to write it to App Store Connect.");
    return;
  }

  const version = await findDraftVersion();
  const localization = await findLocalization(version.id);
  const set = await ensureScreenshotSet(localization.id);
  await clearSet(set.id);

  const ids = [];
  for (const file of files) ids.push(await uploadOne(set.id, file));

  // Apple processes the assets after the upload; report rather than wait, the
  // set is already attached to the version.
  for (const id of ids) {
    let state = await stateOf(id);
    for (let attempt = 0; attempt < 10 && state === "AWAITING_UPLOAD"; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      state = await stateOf(id);
    }
    if (state === "FAILED") warn(`${id} failed Apple's asset check; open the set in App Store Connect.`);
    else log(`state ${state}`);
  }

  log("");
  log(`screenshot set updated: ${meta.appId} (${DISPLAY}, ${files.length} images)`);
  log(`https://appstoreconnect.apple.com/apps/${meta.appId}/distribution/ios/version/inflight`);
}

main().catch((error) => fail(error.message));
