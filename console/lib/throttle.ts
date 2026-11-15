import { getDb } from "./store";

/**
 * Sign-in throttling for repeated refusals.
 *
 * Derived from the sign-in log rather than a timer in memory, so a restart does
 * not reset an attack, and a successful sign-in empties the window naturally as
 * the entries age out. Only password and code steps are throttled: a passkey is
 * possession plus user verification, and blocking it would let an attacker who
 * knows an address lock the real owner out of their strongest factor.
 */
export const LOCK_WINDOW_MS = 15 * 60_000;
export const LOCK_THRESHOLD = 5;
/** One source gets more room than one address, so a shared office is not locked
 *  out by a single person's typos, while a spray across many addresses stops. */
export const SOURCE_LOCK_THRESHOLD = 10;

export interface Lockout {
  locked: boolean;
  attempts: number;
  retryAfterSeconds: number;
}

export function signInLockout(email: string): Lockout {
  const key = email.trim().toLowerCase();
  if (!key) return { locked: false, attempts: 0, retryAfterSeconds: 0 };

  const now = Date.now();
  const recent = getDb()
    .authLog.filter(
      (event) =>
        event.email.trim().toLowerCase() === key &&
        event.outcome !== "success" &&
        now - new Date(event.at).getTime() < LOCK_WINDOW_MS,
    )
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());

  if (recent.length < LOCK_THRESHOLD) {
    return { locked: false, attempts: recent.length, retryAfterSeconds: 0 };
  }

  // Unlock when the oldest counted refusal falls out of the window.
  const blocking = recent[LOCK_THRESHOLD - 1];
  const until = new Date(blocking.at).getTime() + LOCK_WINDOW_MS;
  return {
    locked: until > now,
    attempts: recent.length,
    retryAfterSeconds: Math.max(1, Math.ceil((until - now) / 1000)),
  };
}

/** Refusals grouped by where they came from, not by address. */
export function sourceLockout(source: string): Lockout {
  const key = source.trim();
  if (!key) return { locked: false, attempts: 0, retryAfterSeconds: 0 };

  const now = Date.now();
  const recent = getDb()
    .authLog.filter(
      (event) =>
        (event.source ?? "").trim() === key &&
        event.outcome !== "success" &&
        now - new Date(event.at).getTime() < LOCK_WINDOW_MS,
    )
    .sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());

  if (recent.length < SOURCE_LOCK_THRESHOLD) {
    return { locked: false, attempts: recent.length, retryAfterSeconds: 0 };
  }
  const blocking = recent[SOURCE_LOCK_THRESHOLD - 1];
  const until = new Date(blocking.at).getTime() + LOCK_WINDOW_MS;
  return {
    locked: until > now,
    attempts: recent.length,
    retryAfterSeconds: Math.max(1, Math.ceil((until - now) / 1000)),
  };
}

export type LockScope = "email" | "source";

export interface PausedSignIn {
  kind: LockScope;
  value: string;
  attempts: number;
  retryAfterSeconds: number;
}

/** Everyone currently paused, for the registrar view. */
export function pausedSignIns(): PausedSignIn[] {
  const db = getDb();
  const now = Date.now();
  const emails = new Set<string>();
  const sources = new Set<string>();
  for (const event of db.authLog) {
    if (event.outcome === "success") continue;
    if (now - new Date(event.at).getTime() >= LOCK_WINDOW_MS) continue;
    if (event.email) emails.add(event.email.toLowerCase());
    if (event.source) sources.add(event.source);
  }

  const paused: PausedSignIn[] = [];
  for (const email of emails) {
    const lock = signInLockout(email);
    if (lock.locked) paused.push({ kind: "email", value: email, attempts: lock.attempts, retryAfterSeconds: lock.retryAfterSeconds });
  }
  for (const source of sources) {
    const lock = sourceLockout(source);
    if (lock.locked) paused.push({ kind: "source", value: source, attempts: lock.attempts, retryAfterSeconds: lock.retryAfterSeconds });
  }
  return paused.sort((a, b) => b.attempts - a.attempts);
}

export function lockoutMessage(retryAfterSeconds: number): string {
  const minutes = Math.max(1, Math.ceil(retryAfterSeconds / 60));
  return `Too many refused attempts for that address. Try again in about ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}
