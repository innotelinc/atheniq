import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  SESSION_COOKIE,
  SESSION_TTL_SECONDS,
  SSO_SIGNED_OUT_COOKIE,
  authEnabled,
  issueSession,
  requestOrigin,
  safeNext,
} from "@/lib/session";
import { describeDomains, emailAllowed } from "@/lib/email-policy";
import { getDb, logAuthEvent, mutate, nowIso } from "@/lib/store";
import { openLoginSession } from "@/lib/login-sessions";
import { notifyNewSource } from "@/lib/alerts";
import { requestSource } from "@/lib/request-source";
import { ssoEnabled, ssoGroupAllowed, ssoIdentity, ssoStaff } from "@/lib/sso";

export const dynamic = "force-dynamic";

/**
 * Turns the proxy's identity headers into a console session.
 *
 * Middleware sends a signed-out browser here when the proxy already knows who it
 * is, so a person who authenticated to Authentik lands on the page they asked
 * for instead of the password form. Everything the password route checks still
 * applies — the account must exist, be active, and sit on a registered domain —
 * and the result is an ordinary console session, so publishing and awarding are
 * still attributed to the same account they always were.
 *
 * What this deliberately does not do is ask for the authenticator code. The
 * proxy has already run the school's sign-in, and requiring a second factor on
 * top of a second password would be the duplication this removes. Accounts that
 * only ever use SSO should still enrol from /security if they want a
 * password-and-code way in.
 */
export async function GET(request: Request) {
  const origin = requestOrigin(request);
  const next = safeNext(new URL(request.url).searchParams.get("next"));

  const bounce = (reason: string) => {
    const url = new URL("/login", origin);
    url.searchParams.set("next", next);
    url.searchParams.set("error", reason);
    return NextResponse.redirect(url, 303);
  };

  if (!authEnabled()) return NextResponse.redirect(new URL(next, origin), 303);
  if (!ssoEnabled()) return bounce("required");

  const identity = ssoIdentity(request);
  if (!identity) return bounce("required");

  const db = getDb();
  const source = requestSource(request);

  if (!ssoGroupAllowed(identity)) {
    await mutate((store) =>
      logAuthEvent(
        store,
        identity.email,
        "blocked_domain",
        "Single sign-on refused: the account is not in the group this console allows.",
        source,
      ),
    );
    return bounce("sso_group");
  }

  const member = ssoStaff(db, identity);
  if (!member) {
    await mutate((store) =>
      logAuthEvent(
        store,
        identity.email,
        "unknown_account",
        "Single sign-on succeeded but no active console account uses that address.",
        source,
      ),
    );
    return bounce("sso_unknown");
  }

  if (!emailAllowed(member.email, db.settings.auth.allowedDomains)) {
    const message = `Sign-in is limited to registered domains: ${describeDomains(db.settings.auth.allowedDomains)}.`;
    await mutate((store) => logAuthEvent(store, member.email, "blocked_domain", message, source));
    return bounce("domain");
  }

  await mutate((store) => {
    const record = store.staff.find((person) => person.id === member.id);
    if (record) record.lastLoginAt = nowIso();
    logAuthEvent(store, member.email, "success", "Single sign-on (Authentik).", source);
  });
  const session = await mutate((store) => openLoginSession(store, member.id, source));

  const jar = await cookies();
  // A deliberate sign-in clears the signed-out marker the sign-out left behind.
  jar.delete(SSO_SIGNED_OUT_COOKIE);
  jar.set(SESSION_COOKIE, await issueSession(member.id, session.sid), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  if (session.newSource) notifyNewSource(member, source);

  return NextResponse.redirect(new URL(next, origin), 303);
}
