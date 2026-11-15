import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { fail, ok } from "@/lib/api";
import {
  CHALLENGE_COOKIE,
  CHALLENGE_TTL_SECONDS,
  LOGIN_NEXT_COOKIE,
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  authEnabled,
  issueLoginChallenge,
  issueSession,
  requestOrigin,
  safeNext,
} from "@/lib/session";
import { emailAllowed, describeDomains } from "@/lib/email-policy";
import { getDb, logAuthEvent, mutate, nowIso } from "@/lib/store";
import { noteAuthFailure, notifyNewSource } from "@/lib/alerts";
import { lockoutMessage, signInLockout, sourceLockout } from "@/lib/throttle";
import { openLoginSession } from "@/lib/login-sessions";
import { requestSource } from "@/lib/request-source";
import { verifyPassword } from "@/lib/staff";
import type { Staff } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Sign-in accepts two shapes on purpose:
 *   - a real <form method="post"> submission, answered with a 303 redirect so the
 *     login page works with JavaScript disabled or before hydration;
 *   - a JSON fetch, answered with { ok, data }.
 *
 * Two gates sit behind the password: the account's email domain must be one the
 * school registered, and when two-factor is required the password step only
 * yields a short-lived challenge — the session cookie is issued after the
 * authenticator code (or a recovery code) is accepted.
 */
export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") ?? "";
  const wantsJson = contentType.includes("application/json");

  let password = "";
  let email = "";
  let next = "/";
  if (wantsJson) {
    const body = (await request.json().catch(() => ({}))) as {
      password?: string;
      email?: string;
      next?: string;
    };
    password = typeof body.password === "string" ? body.password : "";
    email = typeof body.email === "string" ? body.email : "";
    next = safeNext(body.next);
  } else {
    const form = await request.formData().catch(() => null);
    const value = (key: string) => {
      const raw = form?.get(key);
      return typeof raw === "string" ? raw : "";
    };
    password = value("password");
    email = value("email");
    next = safeNext(value("next"));
  }

  // Absolute URLs come from the browser's origin, not the server's address:
  // behind the proxy request.url names this process (localhost:3100).
  const origin = requestOrigin(request);

  const bounce = (reason: string) => {
    const url = new URL("/login", origin);
    url.searchParams.set("next", next);
    url.searchParams.set("error", reason);
    return NextResponse.redirect(url, 303);
  };

  if (!authEnabled()) {
    return wantsJson ? ok({ authEnabled: false, next }) : NextResponse.redirect(new URL(next, origin), 303);
  }
  if (!password) {
    return wantsJson ? fail("Enter the console password.", 400) : bounce("required");
  }

  const db = getDb();
  const source = requestSource(request);
  const accounts = db.staff.filter((member) => !member.disabled);
  const normalisedEmail = email.trim().toLowerCase();

  // Five refusals for one address inside the window pause the password step.
  const lockout = signInLockout(normalisedEmail);
  if (lockout.locked) {
    const message = lockoutMessage(lockout.retryAfterSeconds);
    return wantsJson ? fail(message, 429) : bounce("locked");
  }

  // A source spraying many addresses trips this one; 3x the per-address room.
  const sourceLock = sourceLockout(source);
  if (sourceLock.locked) {
    const message = lockoutMessage(sourceLock.retryAfterSeconds);
    return wantsJson ? fail(message, 429) : bounce("locked");
  }

  let found: Staff | undefined;
  if (normalisedEmail) {
    const candidate = accounts.find((member) => member.email.toLowerCase() === normalisedEmail);
    if (candidate && verifyPassword(password, candidate.passwordHash)) found = candidate;
  } else {
    found = accounts.find((member) => verifyPassword(password, member.passwordHash));
  }

  if (!found) {
    // An address nobody holds is a different event from a wrong password, and the
    // security log says so instead of implying someone guessed an account.
    const known = Boolean(
      normalisedEmail && accounts.some((member) => member.email.toLowerCase() === normalisedEmail),
    );
    const outcome = normalisedEmail && !known ? "unknown_account" : "invalid_password";
    const detail =
      outcome === "unknown_account"
        ? "No active account uses that address."
        : "Password did not match any active account.";
    await mutate((store) => logAuthEvent(store, normalisedEmail || "unknown", outcome, detail, source));
    noteAuthFailure(normalisedEmail, outcome);
    return wantsJson ? fail("That password is not right.", 401) : bounce("invalid");
  }

  const signedIn = found;
  const allowedDomains = db.settings.auth.allowedDomains;
  if (!emailAllowed(signedIn.email, allowedDomains)) {
    const message = `Sign-in is limited to registered domains: ${describeDomains(allowedDomains)}.`;
    await mutate((store) => logAuthEvent(store, signedIn.email, "blocked_domain", message, source));
    noteAuthFailure(signedIn.email, "blocked_domain");
    return wantsJson ? fail(message, 403) : bounce("domain");
  }

  const jar = await cookies();
  const secure = process.env.NODE_ENV === "production";

  async function completeSession(target: string) {
    await mutate((store) => {
      const record = store.staff.find((member) => member.id === signedIn.id);
      if (record) record.lastLoginAt = nowIso();
      logAuthEvent(store, signedIn.email, "success", "Password sign-in.", source);
    });
    const session = await mutate((store) => openLoginSession(store, signedIn.id, source));
    jar.set(SESSION_COOKIE, await issueSession(signedIn.id, session.sid), {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      maxAge: SESSION_TTL_SECONDS,
    });
    if (session.newSource) notifyNewSource(signedIn, source);
    return wantsJson
      ? ok({
          authEnabled: true,
          next: target,
          staff: { name: signedIn.name, role: signedIn.role },
          sessionsEnded: session.ended,
        })
      : NextResponse.redirect(new URL(target, origin), 303);
  }

  const setup = !signedIn.totp?.enabled;
  if (db.settings.auth.require2fa || !setup) {
    jar.set(CHALLENGE_COOKIE, await issueLoginChallenge(signedIn.id), {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      maxAge: CHALLENGE_TTL_SECONDS,
    });
    jar.set(LOGIN_NEXT_COOKIE, next, {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      maxAge: CHALLENGE_TTL_SECONDS,
    });
    const target = `/login/totp?next=${encodeURIComponent(next)}`;
    return wantsJson
      ? ok({ twoFactor: true, setup, redirect: target })
      : NextResponse.redirect(new URL(target, origin), 303);
  }

  return completeSession(next);
}
