import fs from "node:fs";
import path from "node:path";
import { buildSeed, DEFAULT_SETTINGS } from "./seed";
import { bootstrapStaff } from "./staff";
import type { Activity, ActorRef, AuthEvent, Database, Settings } from "./types";

const DATA_DIR = path.join(process.cwd(), "data");
const STORE_FILE = path.join(DATA_DIR, "store.json");

declare global {
  // eslint-disable-next-line no-var
  var __atheniqDb: Database | undefined;
  // eslint-disable-next-line no-var
  var __atheniqQueue: Promise<unknown> | undefined;
}

function ensureDir() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
}

function readFromDisk(): Database | null {
  try {
    const raw = fs.readFileSync(STORE_FILE, "utf8");
    const parsed = JSON.parse(raw) as Database;
    if (!parsed || !Array.isArray(parsed.courses)) return null;
    parsed.settings = { ...DEFAULT_SETTINGS, ...parsed.settings };
    parsed.settings.lms = { ...DEFAULT_SETTINGS.lms, ...parsed.settings.lms };
    parsed.settings.signara = { ...DEFAULT_SETTINGS.signara, ...parsed.settings.signara };
    parsed.settings.ai = { ...DEFAULT_SETTINGS.ai, ...parsed.settings.ai };
    parsed.settings.signer = { ...DEFAULT_SETTINGS.signer, ...parsed.settings.signer };
    parsed.settings.sites = { ...DEFAULT_SETTINGS.sites, ...parsed.settings.sites };
    parsed.settings.brand = { ...DEFAULT_SETTINGS.brand, ...parsed.settings.brand };
    parsed.settings.site = { ...DEFAULT_SETTINGS.site, ...parsed.settings.site };
    parsed.settings.mail = { ...DEFAULT_SETTINGS.mail, ...parsed.settings.mail };
    parsed.settings.auth = { ...DEFAULT_SETTINGS.auth, ...parsed.settings.auth };
    if (!Array.isArray(parsed.settings.auth.allowedDomains)) {
      parsed.settings.auth.allowedDomains = DEFAULT_SETTINGS.auth.allowedDomains;
    }
    if (!Array.isArray(parsed.staff)) parsed.staff = [];
    if (!Array.isArray(parsed.accessRequests)) parsed.accessRequests = [];
    if (!Array.isArray(parsed.authLog)) parsed.authLog = [];
    if (!Array.isArray(parsed.loginSessions)) parsed.loginSessions = [];
    if (!Array.isArray(parsed.sessionEnds)) parsed.sessionEnds = [];
    // Accounts written before 2FA or passkeys existed start unenrolled rather than broken.
    for (const member of parsed.staff) {
      if (!Array.isArray(member.passkeys)) member.passkeys = [];
      member.vault = member.vault ?? null;
      member.totp = {
        secret: member.totp?.secret ?? null,
        enabled: member.totp?.enabled ?? false,
        enrolledAt: member.totp?.enrolledAt ?? null,
        recoveryCodes: member.totp?.recoveryCodes ?? [],
      };
    }
    ensureBootstrapStaff(parsed);
    return parsed;
  } catch {
    return null;
  }
}

/** A store written before staff accounts existed gets the bootstrap registrar. */
function ensureBootstrapStaff(db: Database) {
  if (!Array.isArray(db.staff)) db.staff = [];
  if (db.staff.length || !process.env.AUTH_PASSWORD) return;
  db.staff.push(bootstrapStaff());
}

function writeToDisk(db: Database) {
  ensureDir();
  const tmp = `${STORE_FILE}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(db, null, 2), "utf8");
  fs.renameSync(tmp, STORE_FILE);
}

export function getDb(): Database {
  if (globalThis.__atheniqDb) return globalThis.__atheniqDb;
  const fromDisk = readFromDisk();
  if (fromDisk) {
    globalThis.__atheniqDb = fromDisk;
    return fromDisk;
  }
  const seeded = buildSeed();
  ensureBootstrapStaff(seeded);
  globalThis.__atheniqDb = seeded;
  writeToDisk(seeded);
  return seeded;
}

/**
 * Serialise every mutation: the console is a single-writer admin surface and
 * two route handlers can otherwise interleave a read-modify-write on the store.
 */
export async function mutate<T>(fn: (db: Database) => T | Promise<T>): Promise<T> {
  const previous = globalThis.__atheniqQueue ?? Promise.resolve();
  const run = previous.then(async () => {
    const db = getDb();
    const result = await fn(db);
    db.version = (db.version || 0) + 1;
    writeToDisk(db);
    return result;
  });
  globalThis.__atheniqQueue = run.catch(() => undefined);
  return run as Promise<T>;
}

export function resetDb(): Database {
  ensureDir();
  try {
    fs.rmSync(STORE_FILE, { force: true });
  } catch {
    /* ignore */
  }
  globalThis.__atheniqDb = undefined;
  return getDb();
}

export function newId(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${Date.now().toString(36)}${rand}`;
}

export function verifyId(): string {
  const a = Math.random().toString(36).slice(2, 12);
  const b = Math.random().toString(36).slice(2, 12);
  return (a + b).slice(0, 24);
}

export function nowIso(): string {
  return new Date().toISOString();
}

/** Failed and successful sign-in attempts, capped; separate from staff actions. */
export function logAuthEvent(
  db: Database,
  email: string,
  outcome: AuthEvent["outcome"],
  detail = "",
  source = "",
): void {
  db.authLog.unshift({ id: newId("auth"), at: nowIso(), email, outcome, detail, source });
  db.authLog = db.authLog.slice(0, 200);
}

export function logActivity(
  db: Database,
  kind: Activity["kind"],
  message: string,
  ref = "",
  actor?: ActorRef | null,
): void {
  db.activity.unshift({ id: newId("act"), at: nowIso(), kind, message, ref, actor: actor ?? null });
  db.activity = db.activity.slice(0, 200);
}

/** Never hand a raw secret to a client component. */
export function maskSecret(value: string): string {
  if (!value) return "";
  if (value.length <= 8) return "••••";
  return `${value.slice(0, 4)}••••••${value.slice(-4)}`;
}

export function publicSettings(settings: Settings) {
  return {
    ...settings,
    lms: { ...settings.lms, apiToken: maskSecret(settings.lms.apiToken) },
    signara: { ...settings.signara, apiKey: maskSecret(settings.signara.apiKey) },
    ai: { ...settings.ai, apiKey: maskSecret(settings.ai.apiKey) },
    configured: {
      signara: Boolean(settings.signara.apiKey),
      ai: Boolean(settings.ai.apiKey),
      lmsImport: Boolean(settings.lms.importUrl),
      mail: Boolean(process.env.MAIL_API_KEY && process.env.MAIL_FROM),
      rotation: Boolean(process.env.SIGNARA_ADMIN_SECRET),
    },
  };
}
