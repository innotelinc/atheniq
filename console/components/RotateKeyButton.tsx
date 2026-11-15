"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";

interface RotateResult {
  prefix: string;
  expiresAt: string | null;
  verification: string;
  envKeys: string[];
  note: string;
}

/**
 * One-click rotation. The new key is verified against Signara before it is
 * saved, so a failed rotation leaves the working key in place.
 */
export function RotateKeyButton({ ready, prefix }: { ready: boolean; prefix: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RotateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function rotate() {
    if (!window.confirm("Mint a new Signara key and replace the one in use? The old key stays active in Signara until you revoke it there.")) {
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    const response = await api<RotateResult>("/api/keys/rotate", {
      method: "POST",
      body: JSON.stringify({ confirm: true, expiresInDays: 365 }),
    });
    setBusy(false);
    if (!response.ok || !response.data) {
      setError(response.error ?? "Rotation failed.");
      return;
    }
    setResult(response.data);
    router.refresh();
  }

  if (!ready) {
    return (
      <div className="stack-sm">
        <span className="chip muted">Not configured</span>
        <span className="small muted">
          Rotation needs <span className="mono">SIGNARA_ADMIN_SECRET</span> — the Signara{" "}
          <span className="mono">JWT_ACCESS_SECRET</span> from <span className="mono">cerulean/signara</span>. Add it
          to .env and restart; the console signs a short-lived admin JWT to mint the key, and never stores the secret.
        </span>
        <span className="tiny muted">Current key: {prefix || "—"}</span>
      </div>
    );
  }

  return (
    <div className="stack-sm">
      <div className="between">
        <span className="small muted">Current key</span>
        <span className="small mono">{prefix || "—"}</span>
      </div>
      <p className="small muted" style={{ margin: 0 }}>
        Mints a scoped replacement, calls Signara with it to prove it works, then swaps it into settings and .env. If
        the new key fails, nothing changes.
      </p>
      <button className="btn small primary" type="button" onClick={rotate} disabled={busy}>
        {busy ? "Rotating…" : "Rotate key now"}
      </button>
      {result && (
        <div className="stack-sm">
          <div className="between">
            <span className="small">New key</span>
            <span className="small mono">{result.prefix}</span>
          </div>
          <div className="between">
            <span className="small">Expires</span>
            <span className="small mono">{result.expiresAt ? result.expiresAt.slice(0, 10) : "—"}</span>
          </div>
          <span className="chip ok">{result.verification}</span>
          <span className="tiny muted">Updated .env: {result.envKeys.join(", ") || "already current"}</span>
          <span className="tiny muted">{result.note}</span>
        </div>
      )}
      {error && <span className="chip danger">{error}</span>}
    </div>
  );
}
