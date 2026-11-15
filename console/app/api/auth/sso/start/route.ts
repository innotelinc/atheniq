import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { SSO_SIGNED_OUT_COOKIE, requestOrigin, safeNext } from "@/lib/session";
import { ssoEnabled } from "@/lib/sso";

export const dynamic = "force-dynamic";

/**
 * "Sign in with single sign-on", chosen deliberately from the login page.
 *
 * Clears the signed-out marker first: without that the person would arrive back
 * at the login page they just left, because the console refuses to sign anyone
 * in behind their back once they have signed out.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const next = safeNext(url.searchParams.get("next"));
  const jar = await cookies();
  jar.delete(SSO_SIGNED_OUT_COOKIE);
  const target = ssoEnabled()
    ? `/oauth2/sign_in?rd=${encodeURIComponent(next)}`
    : `/login?next=${encodeURIComponent(next)}`;
  return NextResponse.redirect(new URL(target, requestOrigin(request)), 303);
}
