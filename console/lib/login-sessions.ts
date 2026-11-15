import { SESSION_TTL_SECONDS } from "./session";
import { newId, nowIso } from "./store";
import type { ActorRef, Database, LoginSession, SessionEnd, SessionEndReason } from "./types";

/**
 * Live sign-in sessions, so a single address cannot hold more than a few at
 * once. The cookie is still signed and verified without a lookup (middleware
 * runs on the edge and cannot touch the store); this registry adds the two
 * things a stateless cookie cannot do: a per-address cap, and revocation.
 *
 * A revoked session stops working on the next request that resolves the account
 * (every page and API that matters calls currentStaff), even though middleware's
 * signature check alone still passes it through.
 */
export const SESSIONS_PER_SOURCE = 3;

/** How many ended sessions to remember once their registry row is pruned. */
const ENDED_HISTORY_LIMIT = 200;

/**
 * Keep a short record of what ended a session and who did it. Revocation rows
 * are pruned on the next sign-in, so without this the only trace would be the
 * free-text activity entry.
 */
function recordEnd(
  db: Database,
  entry: LoginSession,
  reason: SessionEndReason,
  actor: ActorRef | null,
): void {
  if (!Array.isArray(db.sessionEnds)) db.sessionEnds = [];
  const ended: SessionEnd = {
    id: newId("sen"),
    sessionId: entry.id,
    staffId: entry.staffId,
    source: entry.source,
    startedAt: entry.createdAt,
    endedAt: nowIso(),
    reason,
    endedBy: actor ?? null,
  };
  db.sessionEnds.unshift(ended);
  db.sessionEnds = db.sessionEnds.slice(0, ENDED_HISTORY_LIMIT);
}

/** Drop finished rows so the cap counts only sessions that can still be used. */
export function pruneSessions(db: Database): void {
  if (!Array.isArray(db.loginSessions)) db.loginSessions = [];
  const now = Date.now();
  db.loginSessions = db.loginSessions.filter(
    (entry) => !entry.revokedAt && new Date(entry.expiresAt).getTime() > now,
  );
}

/**
 * Open a session for this address. At the cap, the oldest session from the same
 * address is ended so the person signing in now is never refused because of an
 * old tab; exactly `SESSIONS_PER_SOURCE` remain usable.
 */
export function openLoginSession(
  db: Database,
  staffId: string,
  source: string,
): { sid: string; ended: number; newSource: boolean } {
  pruneSessions(db);

  // Remember where each person has signed in from, so a session opened from an
  // address they have never used can be flagged on the security page. This lives
  // on the account rather than the sign-in log, which a registrar can clear.
  const member = db.staff.find((person) => person.id === staffId);
  const seen = member?.seenSources ?? [];
  const newSource = seen.length > 0 && !seen.includes(source);
  if (member && !seen.includes(source)) {
    member.seenSources = [...seen, source].slice(-8);
  }

  const onSource = db.loginSessions
    .filter((entry) => entry.source === source)
    .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());

  let ended = 0;
  while (onSource.length >= SESSIONS_PER_SOURCE) {
    const oldest = onSource.shift();
    if (!oldest) break;
    oldest.revokedAt = nowIso();
    recordEnd(db, oldest, "evicted", null);
    ended += 1;
  }

  const sid = newId("ses");
  db.loginSessions.push({
    id: sid,
    staffId,
    source,
    createdAt: nowIso(),
    expiresAt: new Date(Date.now() + SESSION_TTL_SECONDS * 1000).toISOString(),
    revokedAt: null,
    newSource,
  });
  return { sid, ended, newSource };
}

/** Sessions that can still be used right now, newest first. */
export function liveSessions(db: Database): LoginSession[] {
  return (db.loginSessions ?? [])
    .filter((entry) => !entry.revokedAt && new Date(entry.expiresAt).getTime() > Date.now())
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
}

/**
 * End every live session, or just the one named. Returns how many were ended, so
 * the caller can report it and record it in the activity trail.
 */
export function revokeSessions(
  db: Database,
  sid?: string,
  meta: { reason?: SessionEndReason; actor?: ActorRef | null } = {},
): number {
  const targets = liveSessions(db).filter((entry) => !sid || entry.id === sid);
  const at = nowIso();
  for (const entry of targets) {
    entry.revokedAt = at;
    recordEnd(db, entry, meta.reason ?? (sid ? "ended_by_registrar" : "signed_out_everywhere"), meta.actor ?? null);
  }
  return targets.length;
}

/** End every live session belonging to one person; returns how many went. */
export function revokeStaffSessions(
  db: Database,
  staffId: string,
  meta: { reason?: SessionEndReason; actor?: ActorRef | null } = {},
): number {
  const targets = liveSessions(db).filter((entry) => entry.staffId === staffId);
  const at = nowIso();
  for (const entry of targets) {
    entry.revokedAt = at;
    recordEnd(db, entry, meta.reason ?? "access_change", meta.actor ?? null);
  }
  return targets.length;
}

export function sessionIsLive(db: Database, sid: string): boolean {
  const entry = (db.loginSessions ?? []).find((session) => session.id === sid);
  if (!entry) return false;
  if (entry.revokedAt) return false;
  return new Date(entry.expiresAt).getTime() > Date.now();
}

export function revokeSession(
  db: Database,
  sid: string,
  meta: { reason?: SessionEndReason; actor?: ActorRef | null } = {},
): boolean {
  const entry = (db.loginSessions ?? []).find((session) => session.id === sid);
  if (!entry || entry.revokedAt) return false;
  entry.revokedAt = nowIso();
  recordEnd(db, entry, meta.reason ?? "signed_out", meta.actor ?? null);
  return true;
}
