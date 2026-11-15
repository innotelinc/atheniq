"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";

interface Passkey {
  id: string;
  label: string;
  createdAt: string;
  lastUsedAt: string | null;
  algorithm: number;
}

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
  rp: { id: string; name: string };
  user: { id: string; name: string; displayName: string };
  pubKeyCredParams: { type: string; alg: number }[];
  timeout: number;
  authenticatorSelection: AuthenticatorSelectionCriteria;
  excludeCredentials: { type: string; id: string; transports: string[] }[];
}

export function PasskeyManager({ passkeys }: { passkeys: Passkey[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [confirmFor, setConfirmFor] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!window.isSecureContext) setHint("Passkeys need HTTPS or localhost — this page is not a secure context.");
    else if (/^(\d+\.\d+\.\d+\.\d+|\[.*\])$/.test(window.location.hostname)) {
      setHint("Passkeys need a domain, not an IP — open the console at its HTTPS hostname to add one.");
    }
  }, []);

  async function add() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (!window.PublicKeyCredential) {
        setError("This browser does not support passkeys.");
        return;
      }
      const begin = await api<BeginResponse>("/api/auth/passkey/register/begin", {
        method: "POST",
        body: "{}",
      });
      if (!begin.ok || !begin.data) {
        setError(begin.error ?? "Could not start passkey setup.");
        return;
      }
      const options = begin.data;
      const credential = (await navigator.credentials.create({
        publicKey: {
          challenge: toBuffer(options.challenge),
          rp: options.rp,
          user: {
            id: toBuffer(options.user.id),
            name: options.user.name,
            displayName: options.user.displayName,
          },
          pubKeyCredParams: options.pubKeyCredParams as PublicKeyCredentialParameters[],
          timeout: options.timeout,
          attestation: "none",
          authenticatorSelection: options.authenticatorSelection,
          excludeCredentials: options.excludeCredentials.map((entry) => ({
            type: "public-key" as const,
            id: toBuffer(entry.id),
            transports: entry.transports as AuthenticatorTransport[],
          })),
        },
      })) as PublicKeyCredential | null;
      if (!credential) {
        setError("The passkey was not created.");
        return;
      }
      const response = credential.response as AuthenticatorAttestationResponse;
      const finish = await api<{ credentialId: string; label: string }>("/api/auth/passkey/register/finish", {
        method: "POST",
        body: JSON.stringify({
          response: {
            clientDataJSON: toBase64Url(response.clientDataJSON),
            attestationObject: toBase64Url(response.attestationObject),
            transports: response.getTransports?.() ?? [],
          },
          label: describeDevice(),
        }),
      });
      if (!finish.ok) {
        setError(finish.error ?? "That passkey could not be saved.");
        return;
      }
      setNotice("Passkey added. You can sign in with it from the login page.");
      router.refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Passkey setup failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(passkey: Passkey) {
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await api(`/api/auth/passkey/delete`, {
      method: "POST",
      body: JSON.stringify({ id: passkey.id }),
    });
    setBusy(false);
    setConfirmFor(null);
    if (!result.ok) {
      setError(result.error ?? "Could not remove that passkey.");
      return;
    }
    setNotice("Passkey removed.");
    router.refresh();
  }

  return (
    <div className="stack-sm">
      {passkeys.length === 0 ? (
        <span className="small muted">No passkeys yet. Add one to sign in with your device instead of a code.</span>
      ) : (
        passkeys.map((passkey) => (
          <div key={passkey.id} className="between">
            <div>
              <div className="small strong">{passkey.label}</div>
              <div className="tiny muted">
                Added {passkey.createdAt.slice(0, 10)} ·{" "}
                {passkey.lastUsedAt ? `last used ${passkey.lastUsedAt.slice(0, 10)}` : "never used"} ·{" "}
                {passkey.algorithm === -257 ? "RS256" : "ES256"}
              </div>
            </div>
            {confirmFor === passkey.id ? (
              <div className="row" style={{ gap: 6 }}>
                <button className="btn small danger" type="button" disabled={busy} onClick={() => void remove(passkey)}>
                  Yes, remove
                </button>
                <button className="btn small ghost" type="button" disabled={busy} onClick={() => setConfirmFor(null)}>
                  Keep
                </button>
              </div>
            ) : (
              <button className="btn small ghost" type="button" disabled={busy} onClick={() => setConfirmFor(passkey.id)}>
                Remove
              </button>
            )}
          </div>
        ))
      )}

      <div className="row">
        <button className="btn small primary" type="button" onClick={add} disabled={busy}>
          {busy ? "Waiting for the device…" : "Add a passkey"}
        </button>
        {notice && <span className="chip ok">{notice}</span>}
        {error && <span className="chip danger">{error}</span>}
      </div>
      {hint && <span className="tiny warn">{hint}</span>}
      <span className="tiny muted">
        A passkey replaces the authenticator code at sign-in, and you can remove one here at any time — removing
        your last passkey leaves the authenticator code as your only second factor. Keep your recovery codes as the
        fallback.
      </span>
    </div>
  );
}

function describeDevice(): string {
  if (typeof navigator === "undefined") return "Passkey";
  const platform = /iPhone|iPad|Android/i.test(navigator.userAgent) ? "Phone" : "This device";
  return `${platform} passkey`;
}
