import { cookies } from "next/headers";
import { ok } from "@/lib/api";
import { SESSION_COOKIE, SESSION_TTL_SECONDS, SSO_SIGNED_OUT_COOKIE, readSession } from "@/lib/session";
import { ssoEnabled, ssoSignOutTarget } from "@/lib/sso";
import { revokeSession } from "@/lib/login-sessions";
import { mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function POST() {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  const session = await readSession(token);
  // Clearing the cookie is not enough: free the address's slot as well.
  if (session) await mutate((store) => revokeSession(store, session.sid, { reason: "signed_out" }));
  jar.delete(SESSION_COOKIE);
  // With a proxy in front, clearing this cookie alone would be undone by the
  // next page load: the proxy still holds a session and would sign the person
  // straight back in. The browser is told where to go to end that one too.
  if (ssoEnabled()) {
    // The marker is what makes signing out stick: the proxy still holds a
    // session, and without this the next page load would be signed straight
    // back in.
    jar.set(SSO_SIGNED_OUT_COOKIE, "1", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: SESSION_TTL_SECONDS,
    });
  }
  return ok({ signedOut: true, ssoSignOut: ssoEnabled() ? ssoSignOutTarget() : null });
}
