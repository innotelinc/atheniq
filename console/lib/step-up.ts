import { createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { currentSessionId } from "./current-staff";
import { verifyTotp } from "./totp";
import { readStepUpTicket } from "./webauthn";
import type { Staff } from "./types";

/**
 * Confirming a destructive action. There are two ways to prove it is really the
 * registrar at the keyboard: a current authenticator code, or a passkey
 * assertion completed moments ago. Both are short-lived, so a browser left
 * signed in elsewhere cannot take access away on its own.
 */
export interface StepUpProof {
  code?: string;
  /** Ticket from a just-completed passkey ceremony. */
  stepUp?: string;
}

/** Whether this account has any second factor to confirm with. */
export function hasSecondFactor(staff: Staff | null | undefined): boolean {
  return Boolean(staff?.totp?.enabled || (staff?.passkeys?.length ?? 0) > 0);
}

/** null when the proof is good, otherwise the message to return to the browser. */
export function checkStepUp(
  staff: Staff,
  proof: StepUpProof | null | undefined,
  messages: { missing: string; wrong: string },
): string | null {
  const ticket = typeof proof?.stepUp === "string" ? proof.stepUp : "";
  if (ticket) {
    const read = readStepUpTicket(ticket);
    if (read?.staffId === staff.id) return null;
  }

  const code = typeof proof?.code === "string" ? proof.code.replace(/\s+/g, "") : "";
  if (!code) return messages.missing;
  if (!staff.totp?.enabled || !verifyTotp(staff.totp.secret ?? "", code)) return messages.wrong;
  return null;
}

/* ------------------------------------------------------------------ */
/* A short memory of the last confirmation, so a run of changes does   */
/* not ask for the code or passkey again for every single one.         */
/* ------------------------------------------------------------------ */

export const CONFIRM_COOKIE = "atheniq_confirm";
/** How long one confirmation covers further destructive actions. */
const CONFIRM_TTL_SECONDS = 5 * 60;

function secret(): string {
  return process.env.AUTH_SECRET || process.env.AUTH_PASSWORD || "atheniq-dev";
}

function signature(payload: string): string {
  return createHmac("sha256", secret()).update(`confirm:${payload}`).digest("base64url");
}

/**
 * Remember a confirmation for this browser. It is bound to the account *and*
 * the session it was made in, so ending that session or signing in elsewhere
 * does not carry the permission with it.
 */
async function rememberConfirmation(staffId: string): Promise<void> {
  const sid = await currentSessionId();
  if (!sid) return;
  const issued = Date.now().toString(36);
  const payload = `${staffId}.${sid}.${issued}`;
  (await cookies()).set(CONFIRM_COOKIE, `${payload}.${signature(payload)}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    // Deliberately no maxAge: this is a browser-session cookie, so closing the
    // browser ends the memory too. The signed timestamp still caps it at five
    // minutes while the window stays open.
  });
}

/**
 * Seconds left on this browser's confirmation, or 0 when there is none. The
 * signed value only counts if it names this account and the session asking.
 */
export async function confirmationRemaining(staffId: string): Promise<number> {
  const raw = (await cookies()).get(CONFIRM_COOKIE)?.value;
  const sid = await currentSessionId();
  if (!raw || !sid) return 0;
  const parts = raw.split(".");
  if (parts.length !== 4) return 0;
  const [id, sessionId, issued, received] = parts;
  if (id !== staffId || sessionId !== sid) return 0;
  const expected = Buffer.from(signature(`${id}.${sessionId}.${issued}`));
  const actual = Buffer.from(received);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return 0;
  const issuedAt = parseInt(issued, 36);
  if (!Number.isFinite(issuedAt)) return 0;
  const remaining = CONFIRM_TTL_SECONDS * 1000 - (Date.now() - issuedAt);
  return remaining > 0 ? Math.ceil(remaining / 1000) : 0;
}

/** True while this browser's last confirmation is still fresh. */
export async function recentlyConfirmed(staffId: string): Promise<boolean> {
  return (await confirmationRemaining(staffId)) > 0;
}

/**
 * Check a destructive action's proof: an explicit code or passkey ticket, or a
 * confirmation made within the last few minutes in this same session. A
 * successful explicit proof is remembered for what follows.
 */
export async function confirmDestructiveAction(
  staff: Staff,
  proof: StepUpProof | null | undefined,
  messages: { missing: string; wrong: string },
): Promise<string | null> {
  const offered =
    (typeof proof?.stepUp === "string" && proof.stepUp.length > 0) ||
    (typeof proof?.code === "string" && proof.code.trim().length > 0);

  if (!offered && (await recentlyConfirmed(staff.id))) return null;

  const problem = checkStepUp(staff, proof, messages);
  if (!problem) await rememberConfirmation(staff.id);
  return problem;
}
