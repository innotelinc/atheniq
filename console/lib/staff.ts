import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import type { ActorRef, Staff, StaffTotp } from "./types";

/**
 * Staff accounts. Passwords are scrypt hashes stored with the account; the
 * bootstrap registrar is created from AUTH_PASSWORD on first boot so an
 * existing installation keeps working with the password it already had.
 *
 * Only route handlers and server components import this module — middleware
 * must stay free of node:crypto, so everything it needs lives in lib/session.ts.
 */

const KEY_LEN = 64;

export function hashPassword(password: string): string {
  const salt = randomBytes(16).toString("hex");
  const hash = scryptSync(password, salt, KEY_LEN).toString("hex");
  return `scrypt$${salt}$${hash}`;
}

export function verifyPassword(password: string, stored: string): boolean {
  const [scheme, salt, hash] = stored.split("$");
  if (scheme !== "scrypt" || !salt || !hash) return false;
  const expected = Buffer.from(hash, "hex");
  if (expected.length !== KEY_LEN) return false;
  return timingSafeEqual(scryptSync(password, salt, KEY_LEN), expected);
}

export function emptyTotp(): StaffTotp {
  return { secret: null, enabled: false, enrolledAt: null, recoveryCodes: [] };
}

export function actorRef(staff: Staff): ActorRef {
  return { id: staff.id, name: staff.name, email: staff.email, role: staff.role };
}

/** The account created from AUTH_PASSWORD when the store has no staff yet. */
export function bootstrapStaff(): Staff {
  const now = new Date().toISOString();
  return {
    id: "stf-bootstrap",
    email: (process.env.AUTH_EMAIL || "registrar@atheniq.institute").trim().toLowerCase(),
    name: (process.env.AUTH_NAME || "D. Hunter").trim(),
    title: (process.env.AUTH_TITLE || "Registrar, AthenIQ Institute").trim(),
    role: "registrar",
    passwordHash: hashPassword(process.env.AUTH_PASSWORD || ""),
    createdAt: now,
    lastLoginAt: null,
    disabled: false,
    totp: emptyTotp(),
    passkeys: [],
  };
}
