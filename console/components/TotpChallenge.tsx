"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { api } from "@/lib/client";

interface BeginResult {
  secret: string;
  otpauthUri: string;
}

interface VerifyResult {
  next: string;
  enrolled: boolean;
  recoveryCodes: string[] | null;
}

/**
 * Step two of sign-in. Enrollment shows the secret for an authenticator app and
 * requires a working code before the account is marked protected; after that
 * the same screen asks for the code (or a recovery code).
 */
export function TotpChallenge({
  setup,
  name,
  email,
  next,
}: {
  setup: boolean;
  name: string;
  email: string;
  next: string;
}) {
  const router = useRouter();
  const [secret, setSecret] = useState<string | null>(null);
  const [uri, setUri] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);

  useEffect(() => {
    if (!setup) return;
    let live = true;
    (async () => {
      setBusy(true);
      const result = await api<BeginResult>("/api/auth/totp/begin", { method: "POST", body: "{}" });
      if (!live) return;
      setBusy(false);
      if (!result.ok || !result.data) {
        setError(result.error ?? "Could not start two-factor setup.");
        return;
      }
      setSecret(result.data.secret);
      setUri(result.data.otpauthUri);
    })();
    return () => {
      live = false;
    };
  }, [setup]);

  useEffect(() => {
    if (!uri) {
      setQr(null);
      return;
    }
    let live = true;
    void QRCode.toDataURL(uri, { margin: 1, width: 200 }).then((url) => {
      if (live) setQr(url);
    });
    return () => {
      live = false;
    };
  }, [uri]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const result = await api<VerifyResult>("/api/auth/totp/verify", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    setBusy(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "That code was not accepted.");
      return;
    }
    if (result.data.recoveryCodes?.length) {
      setCodes(result.data.recoveryCodes);
      return;
    }
    router.push(result.data.next || next);
    router.refresh();
  }

  if (codes) {
    return (
      <div className="stack">
        <p className="small" style={{ margin: 0 }}>
          Two-factor is on for <strong>{email}</strong>. These recovery codes are shown once — keep them somewhere
          safe, each works once if you lose the authenticator.
        </p>
        <div className="digest-preview" style={{ fontFamily: "var(--mono)", lineHeight: 1.9 }}>
          {codes.join("\n")}
        </div>
        <button
          className="btn primary"
          type="button"
          onClick={() => {
            router.push(next);
            router.refresh();
          }}
        >
          Continue to the console
        </button>
      </div>
    );
  }

  return (
    <div className="stack">
      {setup ? (
        <>
          <p className="small muted" style={{ margin: 0 }}>
            {name}, this console requires a second factor. Scan the code with your authenticator — Vaultwarden or
            Bitwarden works — or add the key by hand, then enter the six-digit code it shows.
          </p>
          {qr && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={qr}
              alt="Authenticator setup QR code"
              width={200}
              height={200}
              style={{ background: "#fff", borderRadius: 8 }}
            />
          )}
          <div className="between">
            <span className="small muted">Account</span>
            <span className="small mono">{email}</span>
          </div>
          <div className="between">
            <span className="small muted">Setup key</span>
            <span className="small mono" style={{ letterSpacing: "0.08em" }}>
              {secret ? secret.replace(/(.{4})/g, "$1 ").trim() : busy ? "…" : "—"}
            </span>
          </div>
          {uri && (
            <a className="btn small ghost" href={uri}>
              Open in an authenticator app
            </a>
          )}
        </>
      ) : (
        <p className="small muted" style={{ margin: 0 }}>
          Enter the current code for <strong>{email}</strong>, or use one of your recovery codes.
        </p>
      )}

      <form onSubmit={submit} className="stack">
        <label className="stack-sm">
          <span className="small muted">Code</span>
          <input
            className="input"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            placeholder="123456 or a recovery code"
            required
          />
        </label>
        {error && <span className="chip danger">{error}</span>}
        <button className="btn primary" type="submit" disabled={busy || !code.trim()}>
          {busy ? "Checking…" : setup ? "Confirm and sign in" : "Sign in"}
        </button>
      </form>

      <p className="tiny muted" style={{ margin: 0 }}>
        Lost the authenticator? Use a recovery code above, or ask a registrar to reset two-factor on your account.
      </p>
    </div>
  );
}
