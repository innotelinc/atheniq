import { createHash, createHmac, createPublicKey, randomBytes, timingSafeEqual, verify as cryptoVerify, type KeyObject } from "node:crypto";
import { decodeCborFirst, type CborValue } from "./cbor";
import type { PasskeyRecord } from "./types";

/**
 * Server side of WebAuthn (passkeys) without a dependency: none-attestation
 * registration, discoverable-credential sign-in, ES256 and RS256 signatures,
 * origin + RP-ID + challenge checks, and a monotonic signature counter.
 *
 * Only route handlers import this module (node:crypto).
 */

export const PASSKEY_COOKIE = "atheniq_pk";
const COOKIE_TTL_SECONDS = 5 * 60;

export function newChallenge(): string {
  return randomBytes(32).toString("base64url");
}

function secret(): string {
  return process.env.AUTH_SECRET || process.env.AUTH_PASSWORD || "atheniq-dev";
}

function sign(value: string): string {
  return createHmac("sha256", secret()).update(value).digest("base64url");
}

export function challengeCookie(challenge: string): string {
  return `${challenge}.${sign(challenge)}`;
}

export function readChallengeCookie(value: string | null | undefined): string | null {
  if (!value) return null;
  const index = value.lastIndexOf(".");
  if (index < 1) return null;
  const challenge = value.slice(0, index);
  const signature = Buffer.from(value.slice(index + 1));
  const expected = Buffer.from(sign(challenge));
  if (signature.length !== expected.length || !timingSafeEqual(signature, expected)) return null;
  return challenge;
}

export { COOKIE_TTL_SECONDS };

/** Ceremony cookie for confirming a destructive action with a passkey. */
export const STEP_UP_COOKIE = "atheniq_step";
const STEP_UP_TTL_SECONDS = 2 * 60;

/**
 * A short-lived proof that this account just confirmed with a passkey. Bound to
 * the account and valid for two minutes — about as long as an authenticator
 * code's window — because the assertion itself is what proved presence.
 */
export function issueStepUpTicket(staffId: string): string {
  const issued = Date.now().toString(36);
  const body = `${staffId}.${issued}`;
  return `${body}.${sign(`stepup:${body}`)}`;
}

export function readStepUpTicket(value: string | null | undefined): { staffId: string } | null {
  if (!value) return null;
  const parts = value.split(".");
  if (parts.length !== 3) return null;
  const [staffId, issued, signature] = parts;
  if (!staffId || !issued) return null;
  const expected = Buffer.from(sign(`stepup:${staffId}.${issued}`));
  const actual = Buffer.from(signature);
  if (expected.length !== actual.length || !timingSafeEqual(expected, actual)) return null;
  const issuedAt = parseInt(issued, 36);
  if (!Number.isFinite(issuedAt)) return null;
  if (Date.now() - issuedAt >= STEP_UP_TTL_SECONDS * 1000) return null;
  return { staffId };
}

export interface RelyingParty {
  rpId: string;
  origin: string;
  name: string;
}

/** The site the ceremony belongs to, taken from the request the browser made. */
export function relyingParty(request: Request, name: string): RelyingParty {
  const url = new URL(request.url);
  const host = (request.headers.get("x-forwarded-host") || request.headers.get("host") || url.host)
    .split(",")[0]
    .trim();
  const proto = (request.headers.get("x-forwarded-proto") || url.protocol.replace(":", ""))
    .split(",")[0]
    .trim();
  return {
    rpId: host.replace(/:\d+$/, "").toLowerCase(),
    origin: `${proto}://${host}`.toLowerCase(),
    name,
  };
}

interface ClientData {
  type: string;
  challenge: string;
  origin: string;
}

function parseClientData(raw: string, expectedType: string, challenge: string, origin: string): ClientData {
  let data: ClientData;
  try {
    data = JSON.parse(Buffer.from(raw, "base64url").toString("utf8")) as ClientData;
  } catch {
    throw new Error("The browser sent unreadable client data.");
  }
  if (data.type !== expectedType) throw new Error(`Unexpected ceremony type "${data.type}".`);
  if (data.challenge !== challenge) throw new Error("The passkey challenge did not match — try again.");
  if (data.origin.toLowerCase() !== origin) throw new Error("That passkey was made for a different site.");
  return data;
}

function mapOf(value: CborValue): Map<number | string, CborValue> {
  if (!(value instanceof Map)) throw new Error("Expected a CBOR map.");
  return value;
}

function checkRpId(authData: Buffer, rpId: string): void {
  if (authData.length < 37) throw new Error("The authenticator data is too short.");
  const expected = createHash("sha256").update(rpId).digest();
  if (!timingSafeEqual(authData.subarray(0, 32), expected)) {
    throw new Error("That passkey belongs to a different site.");
  }
}

export function publicKeyFromCose(cose: Buffer): KeyObject {
  const map = mapOf(decodeCborFirst(cose));
  const kty = Number(map.get(1));
  if (kty === 2) {
    const curve = Number(map.get(-1));
    const x = map.get(-2);
    const y = map.get(-3);
    if (!Buffer.isBuffer(x) || !Buffer.isBuffer(y)) throw new Error("The EC passkey is missing its coordinates.");
    const crv = curve === 1 ? "P-256" : curve === 2 ? "P-384" : "P-521";
    return createPublicKey({
      key: { kty: "EC", crv, x: x.toString("base64url"), y: y.toString("base64url") },
      format: "jwk",
    });
  }
  if (kty === 3) {
    const n = map.get(-1);
    const e = map.get(-2);
    if (!Buffer.isBuffer(n) || !Buffer.isBuffer(e)) throw new Error("The RSA passkey is missing its modulus.");
    return createPublicKey({
      key: { kty: "RSA", n: n.toString("base64url"), e: e.toString("base64url") },
      format: "jwk",
    });
  }
  throw new Error("Unsupported passkey key type.");
}

function coseAlgorithm(cose: Buffer): number {
  const map = mapOf(decodeCborFirst(cose));
  return Number(map.get(3));
}

export interface RegistrationResponse {
  clientDataJSON: string;
  attestationObject: string;
  transports?: string[];
}

export interface RegistrationResult {
  credentialId: string;
  publicKey: string;
  algorithm: number;
  signCount: number;
  transports: string[];
}

export function verifyRegistration(
  response: RegistrationResponse,
  challenge: string,
  rp: RelyingParty,
): RegistrationResult {
  parseClientData(response.clientDataJSON, "webauthn.create", challenge, rp.origin);

  const attestation = mapOf(decodeCborFirst(Buffer.from(response.attestationObject, "base64url")));
  const authData = attestation.get("authData");
  if (!Buffer.isBuffer(authData)) throw new Error("The attestation carried no authenticator data.");
  checkRpId(authData, rp.rpId);

  const flags = authData[32];
  if (!(flags & 0x01)) throw new Error("The authenticator did not confirm a person was present.");
  if (!(flags & 0x40)) throw new Error("The authenticator did not create a credential.");

  const signCount = authData.readUInt32BE(33);
  const idLength = authData.readUInt16BE(53);
  const credentialId = authData.subarray(55, 55 + idLength);
  const cose = authData.subarray(55 + idLength);
  const algorithm = coseAlgorithm(cose);
  publicKeyFromCose(cose);

  return {
    credentialId: credentialId.toString("base64url"),
    publicKey: cose.toString("base64url"),
    algorithm,
    signCount,
    transports: Array.isArray(response.transports) ? response.transports.slice(0, 6) : [],
  };
}

export interface AssertionResponse {
  id?: string;
  clientDataJSON: string;
  authenticatorData: string;
  signature: string;
  userHandle?: string | null;
}

export function verifyAssertion(
  response: AssertionResponse,
  challenge: string,
  rp: RelyingParty,
  passkey: Pick<PasskeyRecord, "publicKey" | "algorithm" | "signCount">,
): { signCount: number } {
  parseClientData(response.clientDataJSON, "webauthn.get", challenge, rp.origin);

  const authData = Buffer.from(response.authenticatorData, "base64url");
  checkRpId(authData, rp.rpId);
  if (!(authData[32] & 0x01)) throw new Error("The authenticator did not confirm a person was present.");

  const signCount = authData.readUInt32BE(33);
  if (passkey.signCount > 0 && signCount <= passkey.signCount) {
    throw new Error("This passkey's signature counter did not advance — it may be a clone.");
  }

  const clientHash = createHash("sha256")
    .update(Buffer.from(response.clientDataJSON, "base64url"))
    .digest();
  const signed = Buffer.concat([authData, clientHash]);
  const key = publicKeyFromCose(Buffer.from(passkey.publicKey, "base64url"));
  const signature = Buffer.from(response.signature, "base64url");
  const ok =
    passkey.algorithm === -257 || passkey.algorithm === -37
      ? cryptoVerify("sha256", signed, key, signature)
      : cryptoVerify("sha256", signed, key, signature);

  if (!ok) throw new Error("The passkey signature did not verify.");
  return { signCount };
}
