import type { Database, Staff } from "./types";

/**
 * Single sign-on, as the proxy in front of the console reports it.
 *
 * oauth2-proxy authenticates the browser against Authentik and forwards who the
 * person is in headers. With SSO_TRUST_HEADERS=on the console accepts that as
 * its own sign-in, so staff sign in once instead of once to Authentik and again
 * here. The password and authenticator remain for anyone who reaches the console
 * another way — the public site and /verify are unaffected either way.
 *
 * Trusting headers is only safe while the proxy is the only client that can
 * reach the port: the deployment publishes the console on loopback
 * (127.0.0.1:8090) behind the proxy. Anyone who can connect to the port directly
 * could claim any address in that header, which is exactly why this stays
 * opt-in and must not be turned on for a port the network can reach.
 *
 * Kept free of node:crypto and next/* so middleware (edge runtime) can import it.
 */

/**
 * oauth2-proxy forwards the identity in X-Forwarded-* when it proxies to an
 * upstream (--pass-user-headers). X-Auth-Request-* is the other family it can
 * emit, and is read too so a deployment using an auth-request setup works
 * unchanged.
 */
const EMAIL_HEADERS = ["x-forwarded-email", "x-auth-request-email"];
const GROUPS_HEADERS = ["x-forwarded-groups", "x-auth-request-groups"];

function header(request: { headers: Headers }, names: string[]): string {
  for (const name of names) {
    const value = request.headers.get(name);
    if (value) return value;
  }
  return "";
}

export function ssoEnabled(): boolean {
  return (process.env.SSO_TRUST_HEADERS || "").trim().toLowerCase() === "on";
}

/** The Authentik group a person must hold; an empty value drops the check. */
export function ssoRequiredGroup(): string {
  return (process.env.SSO_GROUP ?? "atheniq-admins").trim();
}

/**
 * Where "Sign out" goes when a proxy is in front. The default ends the proxy's
 * session and returns to the console's login page; a deployment whose identity
 * provider keeps its own browser session should point this at that provider's
 * logout first, or the next page load will quietly sign the person back in.
 */
export function ssoSignOutTarget(): string {
  return (process.env.SSO_SIGN_OUT || "/oauth2/sign_out?rd=/login").trim();
}

export interface SsoIdentity {
  email: string;
  groups: string[];
}

/** What the proxy says about this request, when it says anything at all. */
export function ssoIdentity(request: { headers: Headers }): SsoIdentity | null {
  const email = header(request, EMAIL_HEADERS).trim().toLowerCase();
  if (!email || !email.includes("@")) return null;
  const groups = header(request, GROUPS_HEADERS)
    .split(/[,;]/)
    .map((group) => group.trim())
    .filter(Boolean);
  return { email, groups };
}

export function ssoGroupAllowed(identity: SsoIdentity): boolean {
  const required = ssoRequiredGroup();
  if (!required) return true;
  const wanted = required.toLowerCase();
  return identity.groups.some((group) => group.toLowerCase() === wanted);
}

/** The console account this identity names, if it has one and it is active. */
export function ssoStaff(db: Pick<Database, "staff">, identity: SsoIdentity): Staff | undefined {
  return db.staff.find((member) => !member.disabled && member.email.toLowerCase() === identity.email);
}
