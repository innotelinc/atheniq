"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { Credential } from "@/lib/types";

export function CredentialActions({ credential }: { credential: Credential }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [confirmRevoke, setConfirmRevoke] = useState(false);

  async function act(action: "retry" | "mark_issued" | "revoke") {
    if (action === "revoke" && !confirmRevoke) {
      setConfirmRevoke(true);
      return;
    }
    setBusy(action);
    setError(null);
    setNotice(null);
    const result = await api<Credential | { credential: Credential; error: string | null }>(
      `/api/credentials/${credential.id}`,
      { method: "PATCH", body: JSON.stringify({ action, reason }) },
    );
    setBusy(null);
    if (!result.ok) {
      setError(result.error ?? "The action failed.");
      return;
    }
    const payload = result.data as { credential?: Credential; status?: string } | undefined;
    setNotice(
      action === "revoke"
        ? "Award revoked. Verification now reports the revocation."
        : `Signara responded — award status is now ${payload?.credential?.status ?? payload?.status ?? "updated"}.`,
    );
    setConfirmRevoke(false);
    router.refresh();
  }

  const revoked = credential.status === "revoked";

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">Registrar actions</h2>
          <div className="card-sub">Re-submit to Signara, mark issued, or revoke.</div>
        </div>
      </div>
      <div className="card-body stack">
        <button
          className="btn"
          type="button"
          onClick={() => act("retry")}
          disabled={busy !== null || revoked}
        >
          {busy === "retry" ? "Submitting…" : "Re-submit to Signara"}
        </button>
        <button
          className="btn"
          type="button"
          onClick={() => act("mark_issued")}
          disabled={busy !== null || revoked || credential.status === "issued"}
        >
          {busy === "mark_issued" ? "Updating…" : "Mark issued"}
        </button>

        <div className="field">
          <label className="label" htmlFor="reason">Revocation reason</label>
          <input
            id="reason"
            className="input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. issued in error"
            disabled={revoked}
          />
        </div>
        <button
          className="btn danger"
          type="button"
          onClick={() => act("revoke")}
          disabled={busy !== null || revoked}
        >
          {busy === "revoke" ? "Revoking…" : confirmRevoke ? "Confirm revocation" : "Revoke award"}
        </button>

        {notice && (
          <div className="banner ok">
            <div>{notice}</div>
          </div>
        )}
        {error && (
          <div className="banner bad">
            <div>{error}</div>
          </div>
        )}
        {!credential.signara.apiBase && (
          <div className="banner warn">
            <div>
              Signara is not configured, so this award is held locally. Add an API key in Integrations and choose
              re-submit.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
