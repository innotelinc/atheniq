"use client";

import { useState } from "react";

interface MailTestResult {
  configured: boolean;
  sent: boolean;
  detail: string;
  skipped?: boolean;
  to: string[];
}

export function MailTestButton() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<MailTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/security/mail-test", { method: "POST" });
      const body = (await response.json()) as { ok?: boolean; data?: MailTestResult; error?: string };
      if (!body.ok || !body.data) {
        setError(body.error ?? "The console could not run the test.");
        return;
      }
      setResult(body.data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The console could not run the test.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack-sm">
      <button className="btn small" type="button" onClick={send} disabled={busy}>
        {busy ? "Asking the relay…" : "Send a test alert"}
      </button>
      {error && <span className="chip danger">{error}</span>}
      {result && (
        <span className={`chip ${result.sent ? "ok" : "warn"}`}>
          {result.sent ? `Sent to ${result.to.join(", ")}` : result.detail}
        </span>
      )}
    </div>
  );
}
