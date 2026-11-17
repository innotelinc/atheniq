import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, authEnabled, verifySession } from "@/lib/session";
import { publicSiteOrigin } from "@/lib/branding";

/**
 * One app, one public website.
 *
 * The institute's website is atheniq.institute: `web/landing/` in this
 * repository, served from a git checkout behind the edge's NPM proxy host 206.
 * This app is the registrar's staff console and publishes no second site, so
 * `/site` — which used to be a duplicate storefront rendered from settings —
 * now answers by sending the visitor to the real site. One address for a
 * student or an applicant, one place the school's copy lives.
 *
 * What stays public here is what a console has to answer without a session:
 * sign-in, a credential check an employer runs, the payment hand-off, the
 * policy, the form that asks for an account, and the mobile API's own auth.
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

/**
 * Where the old duplicate site's URLs land on the real one. The website is not
 * a copy of the console, so these are not a path strip: `/catalog/` is the one
 * course list, programs are a section of the front page, and the privacy policy
 * — the URL Apple opens — stays on this host, because the site publishes no
 * legal text. 307 rather than 308: the mapping is ours to correct, and a
 * permanent redirect would stay in browsers after we did.
 */
const SITE_MOVES: { pattern: RegExp; path: string; here?: boolean }[] = [
  { pattern: /^\/site\/courses(\/|$)/, path: "/catalog/" },
  { pattern: /^\/site\/programs(\/|$)/, path: "/#programs" },
  { pattern: /^\/site\/privacy(\/|$)/, path: "/privacy", here: true },
  { pattern: /^\/site(\/|$)/, path: "/" },
];

/**
 * Pages a visitor reaches without a session that are not the website: sign-in,
 * verification, the payment hand-off, the policy and the form that asks for an
 * account. They keep the console's styling but not its sidebar — every sidebar
 * link leads to a page the visitor cannot open.
 */
const PUBLIC_SHELL_PATHS = [
  /^\/login(\/|$)/,
  /^\/verify(\/|$)/,
  /^\/pay(\/|$)/,
  /^\/privacy(\/|$)/,
  /^\/request-access(\/|$)/,
];

function publicShellHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);
  headers.set("x-atheniq-public-shell", "1");
  return headers;
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // The storefront used to live here. The website is atheniq.institute, so a
  // link to /site/courses is a link to the site's catalog.
  const move = SITE_MOVES.find((entry) => entry.pattern.test(pathname));
  if (move) {
    const target = new URL(move.path, move.here ? request.nextUrl.origin : publicSiteOrigin());
    if (!move.here) target.search = search;
    return NextResponse.redirect(target, 307);
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
