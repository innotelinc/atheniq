import fs from "node:fs";
import path from "node:path";
import { createHmac } from "node:crypto";
import type { Settings } from "./types";

/**
 * Signara API-key rotation.
 *
 * Signara stores keys hashed, so an existing key can never be read back — the
 * only way to roll one is to mint a new key with an access JWT signed by the
 * platform's JWT_ACCESS_SECRET. That secret stays in the environment as
 * SIGNARA_ADMIN_SECRET (it is the same value `cerulean/signara` holds); the
 * console never writes it anywhere.
 */

export function rotationReady(): boolean {
  return Boolean((process.env.SIGNARA_ADMIN_SECRET || "").trim());
}

/** The scopes an award needs: upload, read back, and run a signing request. */
export const DEFAULT_SCOPES = [
  "audit.read",
  "documents.create",
  "documents.read",
  "documents.update",
  "documents.delete",
  "documents.download",
  "signing.read",
  "signing.send",
  "signing.cancel",
  "signing.remind",
];

function rotationScopes(): string[] {
  const configured = (process.env.SIGNARA_KEY_SCOPES || "").trim();
  if (!configured) return DEFAULT_SCOPES;
  return configured.split(",").map((scope) => scope.trim()).filter(Boolean);
}

function b64url(value: Buffer | string): string {
  return Buffer.from(value).toString("base64url");
}

function adminJwt(): string {
  const secret = (process.env.SIGNARA_ADMIN_SECRET || "").trim();
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = b64url(
    JSON.stringify({
      sub: process.env.SIGNARA_ADMIN_SUB || "atheniq-console",
      email: process.env.SIGNARA_ADMIN_EMAIL || process.env.CERT_SIGNER_EMAIL || "dhunter@innotel.us",
      type: "access",
      iat: now,
      exp: now + 300,
      groups: [],
    }),
  );
  const signature = createHmac("sha256", secret).update(`${header}.${payload}`).digest("base64url");
  return `${header}.${payload}.${signature}`;
}

export interface MintedKey {
  apiKey: string;
  prefix: string;
  expiresAt: string | null;
  id: string | null;
  name: string;
}

export async function mintSignaraKey(
  settings: Settings["signara"],
  name: string,
  expiresInDays = 365,
): Promise<{ ok: true; key: MintedKey } | { ok: false; error: string }> {
  if (!rotationReady()) {
    return {
      ok: false,
      error:
        "Rotation needs SIGNARA_ADMIN_SECRET in .env — the Signara JWT access secret from cerulean/signara. Add it, restart, then try again.",
    };
  }
  const base = settings.baseUrl.replace(/\/+$/, "");
  try {
    const response = await fetch(`${base}/api/v1/api-keys`, {
      method: "POST",
      headers: { Authorization: `Bearer ${adminJwt()}`, "Content-Type": "application/json" },
      body: JSON.stringify({ name, expiresInDays, scopes: rotationScopes() }),
      signal: AbortSignal.timeout(20_000),
    });
    const text = await response.text();
    if (!response.ok) {
      return { ok: false, error: `Signara refused the key request (HTTP ${response.status}): ${text.slice(0, 200)}` };
    }
    let body: Record<string, unknown> = {};
    try {
      body = JSON.parse(text) as Record<string, unknown>;
    } catch {
      /* fall through to the error below */
    }
    const apiKey = String(body.apiKey ?? body.key ?? body.plaintext ?? body.token ?? "");
    if (!apiKey) {
      return { ok: false, error: `Signara answered without a key: ${text.slice(0, 200)}` };
    }
    const expiresAt = body.expiresAt
      ? String(body.expiresAt)
      : body.expires_at
        ? String(body.expires_at)
        : new Date(Date.now() + expiresInDays * 86_400_000).toISOString();
    return {
      ok: true,
      key: {
        apiKey,
        prefix: String(body.prefix ?? apiKey.slice(0, 8)),
        expiresAt,
        id: body.id ? String(body.id) : null,
        name,
      },
    };
  } catch (error) {
    return {
      ok: false,
      error: `Could not reach Signara: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

/** Call a signed route with the new key before we commit it to settings. */
export async function verifyKey(
  settings: Settings["signara"],
  apiKey: string,
): Promise<{ ok: boolean; detail: string }> {
  const base = settings.baseUrl.replace(/\/+$/, "");
  try {
    const response = await fetch(`${base}/api/v1/signatures/requests?limit=1`, {
      headers: { "X-API-Key": apiKey },
      signal: AbortSignal.timeout(12_000),
    });
    if (response.ok) return { ok: true, detail: `New key accepted (HTTP ${response.status}).` };
    return { ok: false, detail: `New key rejected (HTTP ${response.status}).` };
  } catch (error) {
    return { ok: false, detail: `Could not verify the new key: ${error instanceof Error ? error.message : String(error)}` };
  }
}

/** Persist the rotated values so a fresh checkout with this .env still signs. */
export function updateEnvFile(values: Record<string, string>): { file: string; changed: string[] } {
  const file = path.join(process.cwd(), ".env");
  let lines: string[] = [];
  try {
    lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
  } catch {
    lines = [];
  }
  const changed: string[] = [];
  for (const [key, value] of Object.entries(values)) {
    const index = lines.findIndex((line) => line.trim().startsWith(`${key}=`));
    if (index >= 0) {
      if (lines[index] !== `${key}=${value}`) {
        lines[index] = `${key}=${value}`;
        changed.push(key);
      }
    } else {
      lines.push(`${key}=${value}`);
      changed.push(key);
    }
  }
  while (lines.length && lines[lines.length - 1] === "") lines.pop();
  fs.writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
  return { file, changed };
}
