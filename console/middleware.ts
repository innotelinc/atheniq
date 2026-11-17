import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, authEnabled, verifySession } from "@/lib/session";
import { normalizeDomain, publicHosts } from "@/lib/branding";

/**
 * Two surfaces, one app:
 *   • the registrar console — session required, except sign-in and verification
 *   • the public website  — no session, white-labeled from settings
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
  // The checkout hand-off CHECKOUT_URL points at: an employer-free, learner-free
  // page that states the amount and the reference. It shows nothing private.
  /^\/pay(\/|$)/,
  // The App Store's privacy policy URL. Public on purpose: Apple's reviewers
  // open it without an account, and it describes no one's data.
  /^\/privacy(\/|$)/,
  /^\/request-access(\/|$)/,
  /^\/api\/access-requests(\/|$)/,
  // The app signs in with its own bearer tokens — a phone cannot hold the
  // console session cookie, and those routes refuse anonymous callers anyway.
  /^\/api\/mobile(\/|$)/,
  // The digest answers a scheduler holding DIGEST_TOKEN; the route itself
  // rejects anything without a valid token or a registrar session.
  /^\/api\/health\/digest(\/|$)/,
  /^\/_next\//,
  /^\/favicon\.ico$/,
];

const PUBLIC_SITE = /^\/site(\/|$)/;

/**
 * Pages a visitor reaches without a session that are not the white-labeled
 * site: sign-in, verification, the payment hand-off, the policy and the form
 * that asks for an account. They keep the console's styling but not its
 * sidebar — every sidebar link leads to a page the visitor cannot open.
 */
const PUBLIC_SHELL_PATHS = [
  /^\/login(\/|$)/,
  /^\/verify(\/|$)/,
  /^\/pay(\/|$)/,
  /^\/privacy(\/|$)/,
  /^\/request-access(\/|$)/,
];

function publicHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);
  headers.set("x-atheniq-public", "1");
  return headers;
}

function publicShellHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);
  headers.set("x-atheniq-public-shell", "1");
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

  // Signed in, these paths render inside the console as before; the root layout
  // only swaps the sidebar for the public header when there is no staff member.
  if (PUBLIC_SHELL_PATHS.some((pattern) => pattern.test(pathname))) {
    return NextResponse.next({ request: { headers: publicShellHeaders(request) } });
  }

  if (!authEnabled()) return NextResponse.next();

  if (PUBLIC_PATHS.some((pattern) => pattern.test(pathname))) return NextResponse.next();

  if (await verifySession(request.cookies.get(SESSION_COOKIE)?.value)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ ok: false, error: "Sign in to use the console." }, { status: 401 });
  }

  const login = request.nextUrl.clone();
  login.pathname = "/login";
  login.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
