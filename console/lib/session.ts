/**
 * Staff sign-in for the registrar console.
 *
 * Sessions are signed cookies that name the staff member they belong to, so
 * every publish or award can be attributed. Everything here uses Web Crypto
 * because middleware (edge runtime) imports this module; the scrypt password
 * work lives in lib/staff.ts, which only route handlers import.
 *
 * When AUTH_PASSWORD is unset the console stays open — that is how local
 * development works and it is what the README documents.
 */

export const SESSION_COOKIE = "atheniq_session";
export const SESSION_TTL_SECONDS = 12 * 60 * 60;

/** Short-lived proof that the password step passed, held until the TOTP step. */
export const CHALLENGE_COOKIE = "atheniq_login";
/**
 * Set when someone signs out behind the SSO proxy. Without it the very next
 * page load would be signed straight back in by the identity the proxy still
 * holds, which would make signing out do nothing.
 */
export const SSO_SIGNED_OUT_COOKIE = "atheniq_sso_signed_out";
export const LOGIN_NEXT_COOKIE = "atheniq_login_next";
export const CHALLENGE_TTL_SECONDS = 10 * 60;

export interface SessionPayload {
  staffId: string;
  issuedAt: number;
  /** Registry id, so a session can be counted and revoked. */
  sid: string;
}

export function authEnabled(): boolean {
  return Boolean(process.env.AUTH_PASSWORD);
}

/**
 * The origin the browser actually used. Behind a proxy `request.url` can report
 * the server's own listening address (localhost:3100) while the real host
 * arrives in Host/x-forwarded-host and the scheme in x-forwarded-proto, so a
 * redirect built from request.url would send the browser to the wrong place.
 */
export function requestOrigin(request: { url: string; headers: Headers }): string {
  const first = (value: string | null) => (value || "").split(",")[0].trim();
  const fallback = new URL(request.url);
  const host = first(request.headers.get("x-forwarded-host")) || first(request.headers.get("host"));
  if (!host) return fallback.origin;
  const proto = first(request.headers.get("x-forwarded-proto")) || fallback.protocol.replace(":", "");
  return `${proto}://${host}`;
}

/** Web Crypto wants an ArrayBuffer-backed view, not a possibly shared one. */
function toBuffer(text: string): ArrayBuffer {
  const bytes = new TextEncoder().encode(text);
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  return buffer;
}

async function hmac(payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    toBuffer(process.env.AUTH_SECRET || process.env.AUTH_PASSWORD || "atheniq-dev"),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, toBuffer(payload));
  return Array.from(new Uint8Array(signature))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/** `<staffId>.<issuedAt>.<sid>.<hmac>` — every part is opaque and dot-free. */
export async function issueSession(staffId: string, sid: string): Promise<string> {
  const issued = Date.now().toString(36);
  const body = `${staffId}.${issued}.${sid}`;
  return `${body}.${await hmac(`session:${body}`)}`;
}

/** Same signing scheme as a session, with a 10-minute life and its own label. */
export async function issueLoginChallenge(staffId: string): Promise<string> {
  const issued = Date.now().toString(36);
  const body = `${staffId}.${issued}`;
  return `${body}.${await hmac(`challenge:${body}`)}`;
}

export async function readLoginChallenge(
  token: string | undefined | null,
): Promise<{ staffId: string } | null> {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [staffId, issued, signature] = parts;
  if (!staffId || !issued) return null;
  if (!equal(signature, await hmac(`challenge:${staffId}.${issued}`))) return null;
  const issuedAt = parseInt(issued, 36);
  if (!Number.isFinite(issuedAt)) return null;
  if (Date.now() - issuedAt >= CHALLENGE_TTL_SECONDS * 1000) return null;
  return { staffId };
}

function equal(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i += 1) mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return mismatch === 0;
}

export async function readSession(token: string | undefined | null): Promise<SessionPayload | null> {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 4) return null;
  const [staffId, issued, sid, signature] = parts;
  if (!staffId || !issued || !sid) return null;
  const expected = await hmac(`session:${staffId}.${issued}.${sid}`);
  if (!equal(signature, expected)) return null;
  const issuedAt = parseInt(issued, 36);
  if (!Number.isFinite(issuedAt)) return null;
  if (Date.now() - issuedAt >= SESSION_TTL_SECONDS * 1000) return null;
  return { staffId, issuedAt, sid };
}

export async function verifySession(token: string | undefined | null): Promise<boolean> {
  return (await readSession(token)) !== null;
}

/** Only allow post-login redirects back into this console. */
export function safeNext(value: string | null | undefined): string {
  if (!value) return "/";
  if (!value.startsWith("/") || value.startsWith("//")) return "/";
  return value;
}
