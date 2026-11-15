import { cookies } from "next/headers";
import { fail, ok, str } from "@/lib/api";
import { emailAllowed } from "@/lib/email-policy";
import {
  CHALLENGE_COOKIE,
  LOGIN_NEXT_COOKIE,
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  issueSession,
  readLoginChallenge,
  safeNext,
} from "@/lib/session";
import { getDb, logAuthEvent, mutate, nowIso } from "@/lib/store";
import { PASSKEY_COOKIE, readChallengeCookie, relyingParty, verifyAssertion } from "@/lib/webauthn";
import type { AssertionResponse } from "@/lib/webauthn";
import type { Staff } from "@/lib/types";
import { requestSource } from "@/lib/request-source";
import { openLoginSession } from "@/lib/login-sessions";
import { notifyNewSource } from "@/lib/alerts";

export const dynamic = "force-dynamic";

/**
 * A passkey is possession plus user verification, so a successful assertion is
 * a complete sign-in — it satisfies the two-factor requirement. Domain policy,
 * disabled accounts and a moved signature counter still apply.
 */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as
    | {
        response?: {
          id?: string;
          clientDataJSON?: string;
          authenticatorData?: string;
          signature?: string;
          userHandle?: string | null;
        };
      }
    | null;
  const response = body?.response;
  if (!response?.clientDataJSON || !response.authenticatorData || !response.signature) {
    return fail("The browser did not return a passkey assertion.");
  }

  const source = requestSource(request);
  const jar = await cookies();
  const challenge = readChallengeCookie(jar.get(PASSKEY_COOKIE)?.value);
  if (!challenge) return fail("That passkey attempt expired. Start again.", 401);

  const db = getDb();
  const rp = relyingParty(request, db.settings.brand.siteName);

  const staffId = response.userHandle
    ? Buffer.from(response.userHandle, "base64url").toString("utf8")
    : "";
  let staff: Staff | undefined = staffId
    ? db.staff.find((member) => member.id === staffId && !member.disabled)
    : undefined;
  if (!staff && response.id) {
    staff = db.staff.find(
      (member) => !member.disabled && member.passkeys?.some((passkey) => passkey.credentialId === response.id),
    );
  }
  if (!staff) {
    await mutate((store) =>
      logAuthEvent(store, "unknown passkey", "passkey_failed", "No account for that credential.", source),
    );
    return fail("That passkey is not registered here.", 401);
  }

  const passkey =
    staff.passkeys?.find((entry) => entry.credentialId === response.id) ??
    (staff.passkeys?.length === 1 ? staff.passkeys[0] : undefined);
  if (!passkey) return fail("That passkey is not registered to this account.", 401);

  if (!emailAllowed(staff.email, db.settings.auth.allowedDomains)) {
    await mutate((store) =>
      logAuthEvent(store, staff.email, "blocked_domain", "Passkey sign-in from an unregistered domain.", source),
    );
    return fail("That account is not on a registered domain.", 403);
  }

  let signCount: number;
  try {
    ({ signCount } = verifyAssertion(response as AssertionResponse, challenge, rp, passkey));
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Passkey verification failed.";
    await mutate((store) => logAuthEvent(store, staff.email, "passkey_failed", detail, source));
    return fail(detail, 401);
  }

  await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id);
    if (record) {
      const stored = record.passkeys?.find((entry) => entry.credentialId === passkey.credentialId);
      if (stored) {
        stored.signCount = Math.max(stored.signCount, signCount);
        stored.lastUsedAt = nowIso();
      }
      record.lastLoginAt = nowIso();
    }
    logAuthEvent(store, staff.email, "success", "Passkey sign-in.", source);
  });

  const next = safeNext(jar.get(LOGIN_NEXT_COOKIE)?.value || null);
  const opened = await mutate((store) => openLoginSession(store, staff.id, source));
  jar.set(SESSION_COOKIE, await issueSession(staff.id, opened.sid), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  if (opened.newSource) notifyNewSource(staff, source);
  jar.delete(PASSKEY_COOKIE);
  jar.delete(CHALLENGE_COOKIE);
  jar.delete(LOGIN_NEXT_COOKIE);

  return ok({ next, staff: { name: staff.name, role: staff.role }, sessionsEnded: opened.ended });
}

export async function GET() {
  return fail("Use POST with the assertion.", 405);
}
