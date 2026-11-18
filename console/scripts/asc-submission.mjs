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
const READY = args.has("--ready") || args.has("--submit");
const SUBMIT = args.has("--submit");
// Found from this file, not the working directory: the workflow runs at the
// repository root, and after the merge the copy sits beside the app it describes.
const META_PATH =
  process.env.SUBMISSION_METADATA ||
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "mobile", "store", "submission.json");

const meta = JSON.parse(fs.readFileSync(META_PATH, "utf8"));
const log = (...parts) => console.log(...parts);
const warn = (...parts) => console.warn("warning:", ...parts);

/** Blockers found while preparing; --submit refuses to run with any of them. */
const problems = [];

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
    // Apple hides the real reason for a refused submission under
    // errors[].meta.associatedErrors, keyed by the resource it applies to —
    // without it the message is only "this resource cannot be reviewed".
    const associated = (data.errors || []).flatMap((error) => {
      const map = error.meta?.associatedErrors;
      if (!map || typeof map !== "object") return [];
      return Object.entries(map).flatMap(([resource, list]) =>
        (Array.isArray(list) ? list : []).map(
          (entry) => `${resource}: ${entry.title || entry.code || ""}${entry.detail ? ` — ${entry.detail}` : ""}`,
        ),
      );
    });
    const detail = [
      ...(data.errors || []).map((error) => `${error.title}: ${error.detail ?? ""}`),
      ...associated,
    ].join("; ");
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
  if (READY) {
    log(`  7. PATCH the age rating declaration: ${meta.ageRating?.label ?? "4+"}, every descriptor none`);
    log("  8. POST/PATCH appStoreReviewDetail with the review contact and notes");
    log("  9. PATCH the build to declare no non-exempt encryption");
    log(" 10. POST an appPriceSchedule with the free price point (all territories)");
    log(" 11. check a screenshot set and a build are on the version");
  }
  if (SUBMIT) {
    log(" 12. POST a reviewSubmission, add the version, PATCH submitted:true");
    log(`     review contact: ${meta.reviewContact?.firstName ?? "?"} ${meta.reviewContact?.lastName ?? "?"} <${meta.reviewContact?.email ?? "?"}>`);
  }
  log("\nNothing was sent. Re-run with --apply (and --ready / --submit) to write it to App Store Connect.");
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
    if (open.attributes.versionString !== meta.version) {
      // A draft's version string can still be edited, and it has to match the
      // build's CFBundleShortVersionString: a "1.0" draft holding a "1.0.0"
      // build is only refused when the version is sent to review, long after
      // anyone last looked at the listing.
      try {
        await call("PATCH", `/appStoreVersions/${open.id}`, {
          data: { type: "appStoreVersions", id: open.id, attributes: { versionString: meta.version } },
        });
        log(`renamed it to ${meta.version} so it matches the build`);
        open.attributes.versionString = meta.version;
      } catch (error) {
        warn(`could not rename ${open.attributes.versionString} to ${meta.version}: ${error.message}`);
      }
    }
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

  try {
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
  } catch (error) {
    // Apple refuses "What's New" until there is a released version to compare
    // against, which a first draft never has. Losing that one field is much
    // better than losing the whole listing, so it is written again without it.
    if (!attributes.whatsNew || !/whatsNew/i.test(String(error?.message ?? ""))) throw error;
    const rest = { ...attributes };
    delete rest.whatsNew;
    if (existing) {
      await call("PATCH", `/appStoreVersionLocalizations/${existing.id}`, {
        data: { type: "appStoreVersionLocalizations", id: existing.id, attributes: rest },
      });
    } else {
      await call("POST", "/appStoreVersionLocalizations", {
        data: {
          type: "appStoreVersionLocalizations",
          attributes: { locale: meta.locale, ...rest },
          relationships: { version: { data: { type: "appStoreVersions", id: versionId } } },
        },
      });
    }
    warn(`whatsNew is refused before a first release; the rest of the ${meta.locale} metadata was written`);
  }
}

/**
 * The copyright line App Review shows on the listing. It is an attribute of the
 * version, not of its localization — putting it on the localization is refused.
 */
async function writeVersionCopyright(versionId) {
  if (!meta.copyright) return;
  try {
    await call("PATCH", `/appStoreVersions/${versionId}`, {
      data: { type: "appStoreVersions", id: versionId, attributes: { copyright: meta.copyright } },
    });
    log(`copyright: ${meta.copyright}`);
  } catch (error) {
    problems.push(`copyright: ${error.message}`);
  }
}

/**
 * Content rights: whether the app uses third-party content it does not own.
 * AthenIQ's courses, copy and artwork are its own, so the declaration is the
 * "does not use third-party content" answer App Review expects.
 */
async function writeContentRights() {
  try {
    await call("PATCH", `/apps/${meta.appId}`, {
      data: {
        type: "apps",
        id: meta.appId,
        attributes: { contentRightsDeclaration: "DOES_NOT_USE_THIRD_PARTY_CONTENT" },
      },
    });
    log("content rights: does not use third-party content");
  } catch (error) {
    problems.push(`content rights: ${error.message}`);
  }
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

async function firstAppInfo() {
  const infos = await call("GET", `/apps/${meta.appId}/appInfos?limit=5`);
  return infos.data[0] ?? null;
}

/**
 * The age-rating questionnaire. 4+ means every content descriptor is "none" and
 * the two flags that would change the band are false; the declaration itself is
 * created by App Store Connect with the app, so this only fills it in.
 */
async function writeAgeRating() {
  try {
    const info = await firstAppInfo();
    if (!info) {
      problems.push("no appInfo on the app record, so no age rating");
      return;
    }
    const found = await call("GET", `/appInfos/${info.id}/ageRatingDeclaration`);
    const id = found?.data?.id;
    if (!id) {
      problems.push("no age rating declaration to fill in");
      return;
    }
    const attributes = {
      alcoholTobaccoOrDrugUseOrReferences: "NONE",
      contests: "NONE",
      gamblingSimulated: "NONE",
      gunsOrOtherWeapons: "NONE",
      horrorOrFearThemes: "NONE",
      matureOrSuggestiveThemes: "NONE",
      medicalOrTreatmentInformation: "NONE",
      profanityOrCrudeHumor: "NONE",
      sexualContentGraphicAndNudity: "NONE",
      sexualContentOrNudity: "NONE",
      violenceCartoonOrFantasy: "NONE",
      violenceRealisticProlongedGraphicOrSadistic: "NONE",
      violenceRealistic: "NONE",
      unrestrictedWebAccess: false,
      kidsAgeBand: meta.ageRating?.kidsAgeBand ?? null,
      // Apple's newer questionnaire fields; all of them are required, and an
      // educational client that neither chats nor shows ads answers none/false.
      socialMedia: false,
      messagingAndChat: false,
      ageAssurance: false,
      advertising: false,
      gambling: false,
      healthOrWellnessTopics: false,
      lootBox: false,
      parentalControls: false,
      userGeneratedContent: false,
    };
    await call("PATCH", `/ageRatingDeclarations/${id}`, {
      data: { type: "ageRatingDeclarations", id, attributes },
    });
    log(`age rating: ${meta.ageRating?.label ?? "4+"} — every content descriptor none`);
  } catch (error) {
    problems.push(`age rating: ${error.message}`);
  }
}

/** Who Apple calls if review has a question. Missing contact blocks submission. */
async function writeReviewDetail(versionId) {
  const contact = meta.reviewContact ?? {};
  if (!contact.firstName || !contact.lastName || !contact.phone || !contact.email) {
    problems.push("review contact is incomplete (firstName, lastName, phone, email in submission.json)");
    return;
  }
  const attributes = {
    contactFirstName: contact.firstName,
    contactLastName: contact.lastName,
    contactPhone: contact.phone,
    contactEmail: contact.email,
    demoAccountRequired: false,
    notes: meta.reviewNotes ?? "",
  };
  try {
    const existing = await call("GET", `/appStoreVersions/${versionId}/appStoreReviewDetail`).catch(() => null);
    const id = existing?.data?.id;
    if (id) {
      await call("PATCH", `/appStoreReviewDetails/${id}`, {
        data: { type: "appStoreReviewDetails", id, attributes },
      });
      log(`review contact updated: ${contact.firstName} ${contact.lastName} <${contact.email}>`);
    } else {
      await call("POST", "/appStoreReviewDetails", {
        data: {
          type: "appStoreReviewDetails",
          attributes,
          relationships: { appStoreVersion: { data: { type: "appStoreVersions", id: versionId } } },
        },
      });
      log(`review contact created: ${contact.firstName} ${contact.lastName} <${contact.email}>`);
    }
  } catch (error) {
    problems.push(`review detail: ${error.message}`);
  }
}

/**
 * Export compliance. app.json already sets ITSAppUsesNonExemptEncryption, so a
 * build answers this on upload; the answer still has to be on the build record
 * before review will take it.
 */
async function writeExportCompliance() {
  try {
    const builds = await call(
      "GET",
      `/builds?filter[app]=${meta.appId}&sort=-uploadedDate&limit=1&fields[builds]=version,usesNonExemptEncryption`,
    );
    const build = builds.data[0];
    if (!build) {
      problems.push("no build on the app record");
      return;
    }
    if (build.attributes.usesNonExemptEncryption === false) {
      log(`export compliance: build ${build.attributes.version} reports no non-exempt encryption`);
      return;
    }
    await call("PATCH", `/builds/${build.id}`, {
      data: { type: "builds", id: build.id, attributes: { usesNonExemptEncryption: false } },
    });
    log(`export compliance: declared no non-exempt encryption on build ${build.attributes.version}`);
  } catch (error) {
    problems.push(`export compliance: ${error.message}`);
  }
}

/** The first of several URL shapes that answers, so an API move is not a blocker. */
async function firstThatAnswers(paths) {
  let last = null;
  for (const candidate of paths) {
    try {
      return await call("GET", candidate);
    } catch (error) {
      last = error;
    }
  }
  throw last;
}

/** The app is free everywhere; Apple wants that as a price schedule, not a flag. */
async function writeFreePrice() {
  try {
    // Singular: one schedule per app, and a 404 simply means none is set yet.
    // A schedule object can exist with no prices in it, which still reads as
    // "missing required pricing" to App Review — so count the rows, not the object.
    const schedule = await call(
      "GET",
      `/apps/${meta.appId}/appPriceSchedule?include=manualPrices,automaticPrices`,
    ).catch(() => null);
    const manual = schedule?.data?.relationships?.manualPrices?.data?.length ?? 0;
    const automatic = schedule?.data?.relationships?.automaticPrices?.data?.length ?? 0;
    if (manual + automatic > 0) {
      log(`price: the schedule already carries ${manual + automatic} price row(s)`);
      return;
    }
    const points = await firstThatAnswers([
      `/apps/${meta.appId}/appPricePoints?filter[territory]=USA&limit=200&fields[appPricePoints]=customerPrice`,
      `/appPricePoints?filter[app]=${meta.appId}&filter[territory]=USA&limit=200&fields[appPricePoints]=customerPrice`,
    ]);
    const free = points.data.find((point) => Number(point.attributes?.customerPrice) === 0);
    if (!free) {
      problems.push("the USA price points contain no free tier, so the price was not set");
      return;
    }
    await call("POST", "/appPriceSchedules", {
      data: {
        type: "appPriceSchedules",
        relationships: {
          app: { data: { type: "apps", id: meta.appId } },
          baseTerritory: { data: { type: "territories", id: "USA" } },
          manualPrices: { data: [{ type: "appPrices", id: "${price1}" }] },
        },
      },
      included: [
        {
          type: "appPrices",
          id: "${price1}",
          relationships: { appPricePoint: { data: { type: "appPricePoints", id: free.id } } },
        },
      ],
    });
    log("price: free in every territory that follows the USA base");
  } catch (error) {
    problems.push(`price schedule: ${error.message}`);
  }
}

async function checkVersionReadiness(versionId) {
  try {
    // Screenshot sets hang off the version's localization, not the version.
    const localizations = await call(
      "GET",
      `/appStoreVersions/${versionId}/appStoreVersionLocalizations?limit=50`,
    );
    const found = [];
    for (const localization of localizations.data) {
      const sets = await call(
        "GET",
        `/appStoreVersionLocalizations/${localization.id}/appScreenshotSets?limit=50`,
      ).catch(() => ({ data: [] }));
      for (const set of sets.data) {
        found.push(`${localization.attributes.locale} ${set.attributes.screenshotDisplayType}`);
      }
    }
    if (!found.length) problems.push("no screenshots on the version");
    else log(`screenshots: ${found.join(", ")}`);
  } catch (error) {
    problems.push(`screenshot check: ${error.message}`);
  }
  try {
    const version = await call("GET", `/appStoreVersions/${versionId}?include=build`);
    const buildId = version.data.relationships?.build?.data?.id;
    if (!buildId) problems.push("no build attached to the version");
    else log(`build attached: ${buildId}`);
  } catch (error) {
    problems.push(`build check: ${error.message}`);
  }
}

async function prepareForReview(version) {
  await writeVersionCopyright(version.id);
  await writeContentRights();
  await writeAgeRating();
  await writeReviewDetail(version.id);
  await writeExportCompliance();
  await writeFreePrice();
  await checkVersionReadiness(version.id);
  if (problems.length) {
    log("");
    for (const problem of problems) warn(problem);
  }
}

/**
 * The last step: put the version into a review submission and hand it to Apple.
 * It refuses to run while anything above reported a blocker, because a
 * half-filled submission is rejected and the reason is harder to read there.
 */
async function submitForReview(version) {
  if (problems.length) fail(`Not submitting — ${problems.length} blocker(s) listed above.`);

  const open = await call(
    "GET",
    `/reviewSubmissions?filter[app]=${meta.appId}&filter[platform]=IOS&limit=5`,
  ).catch(() => ({ data: [] }));
  let submission = open.data.find((item) =>
    ["READY_FOR_REVIEW", "WAITING_FOR_REVIEW", "IN_REVIEW"].includes(item.attributes.state),
  );

  if (!submission) {
    const created = await call("POST", "/reviewSubmissions", {
      data: {
        type: "reviewSubmissions",
        attributes: { platform: "IOS" },
        relationships: { app: { data: { type: "apps", id: meta.appId } } },
      },
    });
    submission = created.data;
    log(`created review submission ${submission.id}`);
  } else {
    log(`reusing review submission ${submission.id} (${submission.attributes.state})`);
  }

  const items = await call("GET", `/reviewSubmissionItems?filter[reviewSubmission]=${submission.id}&limit=50`).catch(() => ({ data: [] }));
  const listed = items.data.some((item) => item.relationships?.appStoreVersion?.data?.id === version.id);
  if (!listed) {
    await call("POST", "/reviewSubmissionItems", {
      data: {
        type: "reviewSubmissionItems",
        relationships: {
          reviewSubmission: { data: { type: "reviewSubmissions", id: submission.id } },
          appStoreVersion: { data: { type: "appStoreVersions", id: version.id } },
        },
      },
    });
    log(`added version ${meta.version} to the submission`);
  } else {
    log(`version ${meta.version} is already in the submission`);
  }

  if (submission.attributes.state !== "WAITING_FOR_REVIEW" && submission.attributes.state !== "IN_REVIEW") {
    await call("PATCH", `/reviewSubmissions/${submission.id}`, {
      data: { type: "reviewSubmissions", id: submission.id, attributes: { submitted: true } },
    });
    log("submitted for review");
  }

  const after = await call(
    "GET",
    `/reviewSubmissions/${submission.id}?fields[reviewSubmissions]=state,submittedDate`,
  );
  log(`review state: ${after.data.attributes.state} (submitted ${after.data.attributes.submittedDate ?? "not yet"})`);
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
  if (READY) await prepareForReview(version);
  if (SUBMIT) await submitForReview(version);

  const after = await call("GET", `/appStoreVersions/${version.id}?fields[appStoreVersions]=versionString,appStoreState`);
  log("");
  log(`draft ready: ${after.data.attributes.versionString} (${after.data.attributes.appStoreState})`);
  log(`https://appstoreconnect.apple.com/apps/${meta.appId}/distribution/ios/version/inflight`);
  log("Screenshots and the review submission itself are still manual.");
}

main().catch((error) => fail(error.message));
