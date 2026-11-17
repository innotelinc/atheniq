import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * App sign-in.
 *
 * A phone has no cookie jar worth relying on and cannot walk an Authentik
 * redirect, so the app carries a bearer token instead of the console's session
 * cookie. The token is the same HMAC construction as lib/session.ts, with its
 * own label, so one can never be replayed as the other.
 */
export type MobileRole = "learner" | "staff";

export interface MobileIdentity {
  sub: string;
  role: MobileRole;
  name: string;
  email: string;
  /** Only for role "staff"; mirrors the console's two roles. */
  staffRole?: "registrar" | "publisher";
  exp: number;
}

/** Long enough to keep a phone signed in between terms, short enough to matter. */
const LEARNER_TTL_SECONDS = 30 * 24 * 60 * 60;
/** A staff token can award credentials, so it lives no longer than a console session. */
const STAFF_TTL_SECONDS = 12 * 60 * 60;

function secret(): string {
  return process.env.AUTH_SECRET || process.env.AUTH_PASSWORD || "atheniq-dev";
}

function signature(payload: string): string {
  return createHmac("sha256", secret()).update(`mobile:${payload}`).digest("base64url");
}

export function issueToken(identity: Omit<MobileIdentity, "exp">): string {
  const ttl = identity.role === "staff" ? STAFF_TTL_SECONDS : LEARNER_TTL_SECONDS;
  const exp = Math.floor(Date.now() / 1000) + ttl;
  const payload = Buffer.from(JSON.stringify({ ...identity, exp }), "utf8").toString("base64url");
  return `mb.${payload}.${signature(payload)}`;
}

export function readToken(token: string | null | undefined): MobileIdentity | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3 || parts[0] !== "mb") return null;
  const [, payload, mac] = parts;
  const expected = signature(payload);
  if (mac.length !== expected.length) return null;
  if (!timingSafeEqual(Buffer.from(mac), Buffer.from(expected))) return null;
  let parsed: MobileIdentity;
  try {
    parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as MobileIdentity;
  } catch {
    return null;
  }
  if (!parsed?.sub || (parsed.role !== "learner" && parsed.role !== "staff")) return null;
  if (!Number.isFinite(parsed.exp) || parsed.exp * 1000 <= Date.now()) return null;
  return parsed;
}

export function bearerIdentity(request: Request): MobileIdentity | null {
  const header = request.headers.get("authorization") || "";
  if (!header.toLowerCase().startsWith("bearer ")) return null;
  return readToken(header.slice(7).trim());
}

export function tokenExpiry(identity: MobileIdentity): string {
  return new Date(identity.exp * 1000).toISOString();
}
