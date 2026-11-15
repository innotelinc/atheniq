import { api } from "./client";

/**
 * Browser side of confirming a destructive action with a passkey. The server
 * offers only this account's credentials, verifies the assertion, and returns a
 * two-minute ticket that stands in for the authenticator code.
 */

function toBuffer(value: string): ArrayBuffer {
  const binary = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

function toBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

interface BeginResponse {
  challenge: string;
  rpId: string;
  timeout: number;
  userVerification: UserVerificationRequirement;
  allowCredentials: { id: string; transports?: string[] }[];
}

export type StepUpResult = { ok: true; ticket: string } | { ok: false; error: string };

export async function passkeyStepUp(): Promise<StepUpResult> {
  try {
    if (typeof window === "undefined" || !window.PublicKeyCredential) {
      return { ok: false, error: "This browser does not support passkeys." };
    }
    const begin = await api<BeginResponse>("/api/auth/passkey/step-up/begin", { method: "POST", body: "{}" });
    if (!begin.ok || !begin.data) {
      return { ok: false, error: begin.error ?? "Could not start the passkey check." };
    }
    const options = begin.data;
    const credential = (await navigator.credentials.get({
      publicKey: {
        challenge: toBuffer(options.challenge),
        rpId: options.rpId,
        timeout: options.timeout,
        userVerification: options.userVerification,
        allowCredentials: options.allowCredentials.map((entry) => ({
          id: toBuffer(entry.id),
          type: "public-key" as const,
          transports: entry.transports as AuthenticatorTransport[] | undefined,
        })),
      },
    })) as PublicKeyCredential | null;
    if (!credential) return { ok: false, error: "No passkey was chosen." };

    const response = credential.response as AuthenticatorAssertionResponse;
    const finish = await api<{ ticket: string }>("/api/auth/passkey/step-up/finish", {
      method: "POST",
      body: JSON.stringify({
        response: {
          id: credential.id,
          clientDataJSON: toBase64Url(response.clientDataJSON),
          authenticatorData: toBase64Url(response.authenticatorData),
          signature: toBase64Url(response.signature),
          userHandle: response.userHandle ? toBase64Url(response.userHandle) : null,
        },
      }),
    });
    if (!finish.ok || !finish.data?.ticket) {
      return { ok: false, error: finish.error ?? "That passkey was not accepted." };
    }
    return { ok: true, ticket: finish.data.ticket };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "The passkey check did not finish." };
  }
}
