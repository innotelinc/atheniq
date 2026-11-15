import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, SSO_SIGNED_OUT_COOKIE, authEnabled, verifySession } from "@/lib/session";
import { ssoEnabled, ssoIdentity } from "@/lib/sso";
import { normalizeDomain, publicHosts } from "@/lib/branding";

/**
 * Two surfaces, one app:
 *   • the registrar console — session required, except sign-in and verification
 *   • the public website  — no session, white-labelled from settings
 *
 * The public site is served at /site on the console host, and rewritten to the
 * root for any host in PUBLIC_SITE_HOSTS (atheniq.institute by default). The
 * root layout reads x-atheniq-public and renders those pages without the
 * console chrome.
 */
const PUBLIC_PATHS = [
  /^\/login(\/|$)/,
  /^\/api\/auth\//,
  /^\/verify(\/|$)/,
  /^\/api\/verify(\/|$)/,
  /^\/request-access(\/|$)/,
  /^\/api\/access-requests(\/|$)/,
  // The digest answers a scheduler holding DIGEST_TOKEN; the route itself
  // rejects anything without a valid token or a registrar session.
  /^\/api\/health\/digest(\/|$)/,
  /^\/_next\//,
  /^\/favicon\.ico$/,
];

const PUBLIC_SITE = /^\/site(\/|$)/;

function publicHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);
  headers.set("x-atheniq-public", "1");
  return headers;
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const host = normalizeDomain(request.headers.get("host") || "");
  const onPublicHost = publicHosts().includes(host);

  if (onPublicHost) {
    const headers = publicHeaders(request);
    if (pathname.startsWith("/_next/") || pathname === "/favicon.ico" || pathname.startsWith("/api/")) {
      return NextResponse.next({ request: { headers } });
    }
    const url = request.nextUrl.clone();
    const publicPath = PUBLIC_SITE.test(pathname) || pathname === "/verify" || pathname.startsWith("/verify/");
    if (!publicPath) {
      url.pathname = pathname === "/" ? "/site" : `/site${pathname}`;
    }
    return NextResponse.rewrite(url, { request: { headers } });
  }

  if (PUBLIC_SITE.test(pathname)) {
    return NextResponse.next({ request: { headers: publicHeaders(request) } });
  }

  if (!authEnabled()) return NextResponse.next();

  if (PUBLIC_PATHS.some((pattern) => pattern.test(pathname))) return NextResponse.next();

  if (await verifySession(request.cookies.get(SESSION_COOKIE)?.value)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ ok: false, error: "Sign in to use the console." }, { status: 401 });
  }

  // The proxy in front already authenticated this browser against Authentik, so
  // trade its identity for a console session rather than asking for the password
  // again. The route re-checks the account, its group and its domain.
  const signedOut = request.cookies.get(SSO_SIGNED_OUT_COOKIE)?.value === "1";
  if (ssoEnabled() && !signedOut && ssoIdentity(request)) {
    const sso = request.nextUrl.clone();
    sso.pathname = "/api/auth/sso";
    sso.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(sso);
  }

  const login = request.nextUrl.clone();
  login.pathname = "/login";
  login.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
