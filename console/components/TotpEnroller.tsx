"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { api } from "@/lib/client";

interface Setup {
  secret: string;
  otpauthUri: string;
  account: string;
}

/**
 * Add an authenticator code to this account. The secret is shown once and can
 * be pasted into any TOTP app — Vaultwarden/Bitwarden accepts it on a login
 * item's "Authenticator key" field — and the code confirms the app and the
 * server share the same clock before enrolment is switched on.
 */
export function TotpEnroller() {
  const router = useRouter();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!setup) {
      setQr(null);
      return;
    }
    let current = true;
    void QRCode.toDataURL(setup.otpauthUri, { margin: 1, width: 200 }).then((url) => {
      if (current) setQr(url);
    });
    return () => {
      current = false;
    };
  }, [setup]);

  async function begin() {
    setBusy(true);
    setError(null);
    const result = await api<Setup>("/api/auth/totp/enroll", { method: "POST", body: "{}" });
    setBusy(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "Could not start the setup.");
      return;
    }
    setSetup(result.data);
  }

  async function confirm() {
    setBusy(true);
    setError(null);
    const result = await api<{ enabled: boolean; recoveryCodes: string[] }>(
      "/api/auth/totp/enroll",
      { method: "POST", body: JSON.stringify({ code }) },
    );
    setBusy(false);
    if (!result.ok || !result.data) {
      setError(result.error ?? "That code was not accepted.");
      return;
    }
    setCodes(result.data.recoveryCodes);
    setSetup(null);
    router.refresh();
  }

  if (codes) {
    return (
      <div className="stack-sm">
        <span className="chip ok">Authenticator enrolled</span>
        <span className="small muted">
          Save these recovery codes somewhere else — each works once if you lose the authenticator.
        </span>
        <div className="mono small" style={{ columnGap: 18, display: "flex", flexWrap: "wrap" }}>
          {codes.map((entry) => (
            <span key={entry}>{entry}</span>
          ))}
        </div>
        <button className="btn small ghost" type="button" onClick={() => setCodes(null)}>
          Done
        </button>
      </div>
    );
  }

  if (!setup) {
    return (
      <div className="stack-sm">
        <button className="btn small" type="button" onClick={begin} disabled={busy}>
          {busy ? "Preparing…" : "Set up authenticator"}
        </button>
        {error && <span className="chip danger">{error}</span>}
        <span className="tiny muted">
          Use any TOTP app. In Vaultwarden or Bitwarden, add the secret to a login item&apos;s authenticator
          field so the code lives beside the password.
        </span>
      </div>
    );
  }

  return (
    <div className="stack-sm">
      <span className="small">
        Scan this with your authenticator for <span className="mono">{setup.account}</span>:
      </span>
      {qr && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={qr} alt="Authenticator setup QR code" width={200} height={200} style={{ background: "#fff", borderRadius: 8 }} />
      )}
      <code className="mono small" style={{ wordBreak: "break-all" }}>
        {setup.secret}
      </code>
      <span className="tiny muted" style={{ wordBreak: "break-all" }}>
        {setup.otpauthUri}
      </span>
      <div className="row" style={{ gap: 8 }}>
        <input
          className="input"
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="6-digit code"
          value={code}
          maxLength={6}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
        />
        <button className="btn small primary" type="button" onClick={confirm} disabled={busy || code.length !== 6}>
          {busy ? "Checking…" : "Turn on"}
        </button>
        <button className="btn small ghost" type="button" onClick={() => setSetup(null)} disabled={busy}>
          Cancel
        </button>
      </div>
      {error && <span className="chip danger">{error}</span>}
    </div>
  );
}
