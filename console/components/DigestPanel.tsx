"use client";

import { useState } from "react";
import { api } from "@/lib/client";

interface DigestPreview {
  subject: string;
  text: string;
  recipients: string[];
  mailConfigured: boolean;
  lastDigestAt: string | null;
}

/**
 * The weekly digest: readable in-console without a mail relay, sendable when
 * one is configured, and reachable from a scheduler with DIGEST_TOKEN.
 */
export function DigestPanel({
  recipients,
  alertsTo,
  cadenceDays,
  lastDigestAt,
  mailConfigured,
}: {
  recipients: string;
  alertsTo: string;
  cadenceDays: number;
  lastDigestAt: string | null;
  mailConfigured: boolean;
}) {
  const [to, setTo] = useState(recipients);
  const [alerts, setAlerts] = useState(alertsTo);
  const [cadence, setCadence] = useState(String(cadenceDays));
  const [preview, setPreview] = useState<DigestPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"save" | "preview" | "send" | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy("save");
    setError(null);
    setMessage(null);
    const result = await api("/api/health/digest", {
      method: "PUT",
      body: JSON.stringify({ digestTo: to, cadenceDays: Number(cadence), alertsTo: alerts }),
    });
    setBusy(null);
    if (!result.ok) setError(result.error ?? "Could not save.");
    else setMessage("Recipients saved.");
  }

  async function loadPreview() {
    setBusy("preview");
    setError(null);
    const result = await api<DigestPreview>("/api/health/digest");
    setBusy(null);
    if (!result.ok || !result.data) {
      setError(result.error ?? "Could not build the digest.");
      return;
    }
    setPreview(result.data);
  }

  async function send() {
    setBusy("send");
    setError(null);
    setMessage(null);
    const result = await api<{ detail: string }>("/api/health/digest", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error ?? "Could not send the digest.");
      return;
    }
    setMessage(result.data?.detail ?? "Sent.");
  }

  return (
    <div className="stack-sm">
      <form onSubmit={save} className="stack-sm">
        <label className="label" htmlFor="digest-to">
          Recipients
        </label>
        <input
          id="digest-to"
          className="input"
          value={to}
          onChange={(event) => setTo(event.target.value)}
          placeholder="registrar@example.edu, provost@example.edu"
        />
        <label className="label" htmlFor="alerts-to">
          Security alerts to
        </label>
        <input
          id="alerts-to"
          className="input"
          value={alerts}
          onChange={(event) => setAlerts(event.target.value)}
          placeholder="security@example.edu — empty means every registrar"
        />
        <div className="row" style={{ gap: 8 }}>
          <div style={{ maxWidth: 140 }}>
            <label className="label" htmlFor="digest-cadence">
              Every (days)
            </label>
            <input
              id="digest-cadence"
              className="input"
              type="number"
              min={1}
              max={90}
              value={cadence}
              onChange={(event) => setCadence(event.target.value)}
            />
          </div>
          <div style={{ alignSelf: "flex-end" }} className="row">
            <button className="btn small ghost" type="submit" disabled={busy !== null}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button className="btn small ghost" type="button" onClick={loadPreview} disabled={busy !== null}>
              {busy === "preview" ? "Building…" : "Read digest"}
            </button>
            <button className="btn small primary" type="button" onClick={send} disabled={busy !== null}>
              {busy === "send" ? "Sending…" : "Send now"}
            </button>
          </div>
        </div>
      </form>

      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <span className={`chip ${mailConfigured ? "ok" : "warn"}`}>
          {mailConfigured ? "Mail relay configured" : "No mail relay"}
        </span>
        <span className="chip muted">
          {lastDigestAt ? `Last sent ${new Date(lastDigestAt).toLocaleString("en-US")}` : "Never sent"}
        </span>
      </div>

      {!mailConfigured && (
        <span className="tiny muted">
          Set <span className="mono">MAIL_API_KEY</span> and <span className="mono">MAIL_FROM</span> in .env to send —
          any relay that accepts <span className="mono">POST {`{from,to,subject,text,html}`}</span>. Until then the
          digest is readable here. A scheduler can POST <span className="mono">/api/health/digest?token=…</span> with{" "}
          <span className="mono">DIGEST_TOKEN</span> set.
        </span>
      )}

      {message && <span className="chip ok">{message}</span>}
      {error && <span className="chip danger">{error}</span>}

      {preview && (
        <div className="stack-sm">
          <div className="between">
            <span className="strong small">{preview.subject}</span>
            <span className="tiny muted">{preview.recipients.length || 0} recipient(s)</span>
          </div>
          <pre className="digest-preview">{preview.text}</pre>
        </div>
      )}
    </div>
  );
}
