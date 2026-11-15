"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";

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
}

export function PasskeySignIn({ next }: { next: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      if (!window.PublicKeyCredential) {
        setError("This browser does not support passkeys.");
        return;
      }
      const begin = await api<BeginResponse>("/api/auth/passkey/login/begin", { method: "POST", body: "{}" });
      if (!begin.ok || !begin.data) {
        setError(begin.error ?? "Could not start passkey sign-in.");
        return;
      }
      const options = begin.data;
      const credential = (await navigator.credentials.get({
        publicKey: {
          challenge: toBuffer(options.challenge),
          rpId: options.rpId,
          timeout: options.timeout,
          userVerification: options.userVerification,
          allowCredentials: [],
        },
      })) as PublicKeyCredential | null;
      if (!credential) {
        setError("No passkey was chosen.");
        return;
      }
      const response = credential.response as AuthenticatorAssertionResponse;
      const finish = await api<{ next: string }>("/api/auth/passkey/login/finish", {
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
      if (!finish.ok) {
        setError(finish.error ?? "That passkey was not accepted.");
        return;
      }
      router.push(finish.data?.next || next);
      router.refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Passkey sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack-sm">
      <button className="btn block" type="button" onClick={signIn} disabled={busy}>
        {busy ? "Waiting for your device…" : "Sign in with a passkey"}
      </button>
      {error && <span className="chip danger">{error}</span>}
    </div>
  );
}
