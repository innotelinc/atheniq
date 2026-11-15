import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { fail, ok, str } from "@/lib/api";
import {
  CHALLENGE_COOKIE,
  LOGIN_NEXT_COOKIE,
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  issueSession,
  readLoginChallenge,
  safeNext,
} from "@/lib/session";
import { getDb, logActivity, logAuthEvent, mutate, nowIso } from "@/lib/store";
import { consumeRecoveryCode, generateRecoveryCodes, verifyTotp } from "@/lib/totp";
import { noteAuthFailure, notifyNewSource } from "@/lib/alerts";
import { lockoutMessage, signInLockout, sourceLockout } from "@/lib/throttle";
import { openLoginSession } from "@/lib/login-sessions";
import { requestSource } from "@/lib/request-source";

export const dynamic = "force-dynamic";

/**
 * Finish the password step with either the authenticator code (enrolling on the
 * way if needed) or a single-use recovery code. Only here is the session cookie
 * written, so a password alone never becomes a signed-in session while
 * two-factor is required.
 */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { code?: string } | null;
  const code = str(body?.code);
  if (!code) return fail("Enter the 6-digit code from your authenticator.");

  const source = requestSource(request);
  const jar = await cookies();
  const challenge = await readLoginChallenge(jar.get(CHALLENGE_COOKIE)?.value);
  if (!challenge) return fail("That sign-in attempt expired. Sign in again.", 401);

  const db = getDb();
  const staff = db.staff.find((member) => member.id === challenge.staffId && !member.disabled);
  if (!staff) return fail("That account cannot sign in.", 403);

  // A passkey is exempt; codes are throttled like passwords.
  const lockout = signInLockout(staff.email);
  if (lockout.locked) return fail(lockoutMessage(lockout.retryAfterSeconds), 429);
  const sourceLock = sourceLockout(source);
  if (sourceLock.locked) return fail(lockoutMessage(sourceLock.retryAfterSeconds), 429);

  if (!staff.totp?.secret) return fail("Start the two-factor setup again.", 409);

  const enrolling = !staff.totp.enabled;
  let recoveryCodes: string[] | null = null;
  let failure: string | null = null;

  if (enrolling) {
    if (!verifyTotp(staff.totp.secret, code)) {
      failure = "That code is not right. Check the authenticator's clock and try the next one.";
    } else {
      const generated = generateRecoveryCodes();
      recoveryCodes = generated.plain;
      await mutate((store) => {
        const record = store.staff.find((member) => member.id === staff.id);
        if (!record) return;
        record.totp = {
          secret: staff.totp!.secret,
          enabled: true,
          enrolledAt: nowIso(),
          recoveryCodes: generated.hashes,
        };
        logActivity(store, "settings.updated", `Enabled two-factor for ${record.name}`, record.id);
      });
    }
  } else if (/^\d{6}$/.test(code.replace(/\s+/g, ""))) {
    if (!verifyTotp(staff.totp.secret, code)) failure = "That code is not right.";
  } else {
    const consumed = consumeRecoveryCode(staff.totp.recoveryCodes ?? [], code);
    if (!consumed.ok) {
      failure = "That recovery code has already been used, or is not one of this account's codes.";
    } else {
      await mutate((store) => {
        const record = store.staff.find((member) => member.id === staff.id);
        if (record) record.totp.recoveryCodes = consumed.remaining;
      });
    }
  }

  if (failure) {
    await mutate((store) => logAuthEvent(store, staff.email, "totp_failed", failure ?? "Code rejected.", source));
    noteAuthFailure(staff.email, "totp_failed");
    return fail(failure, 401);
  }

  const next = safeNext(jar.get(LOGIN_NEXT_COOKIE)?.value);
  const secure = process.env.NODE_ENV === "production";
  const opened = await mutate((store) => openLoginSession(store, staff.id, source));
  jar.set(SESSION_COOKIE, await issueSession(staff.id, opened.sid), {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  if (opened.newSource) notifyNewSource(staff, source);
  jar.delete(CHALLENGE_COOKIE);
  jar.delete(LOGIN_NEXT_COOKIE);
  await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id);
    if (record) record.lastLoginAt = nowIso();
    logAuthEvent(
      store,
      staff.email,
      enrolling ? "success" : /^\d{6}$/.test(code.replace(/\s+/g, "")) ? "success" : "recovery_used",
      enrolling ? "Two-factor enrolled and signed in." : "Two-factor sign-in.",
      source,
    );
  });

  return NextResponse.json({
    ok: true,
    data: { next, enrolled: enrolling, recoveryCodes, sessionsEnded: opened.ended },
  });
}
