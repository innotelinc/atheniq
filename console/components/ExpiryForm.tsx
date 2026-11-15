"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";

export function ExpiryForm({ value }: { value: string }) {
  const router = useRouter();
  const [date, setDate] = useState(value);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await api("/api/integrations", {
      method: "PUT",
      body: JSON.stringify({ signara: { keyExpiresAt: date || null } }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? "Could not save the expiry.");
      return;
    }
    setMessage(date ? "Expiry recorded." : "Expiry cleared.");
    router.refresh();
  }

  return (
    <form onSubmit={save} className="stack-sm" style={{ gap: 6 }}>
      <label className="label" htmlFor="key-expiry">
        Record expiry
      </label>
      <div className="row" style={{ gap: 6 }}>
        <input
          id="key-expiry"
          className="input"
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />
        <button className="btn small primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
      {message && <span className="chip ok">{message}</span>}
      {error && <span className="chip danger">{error}</span>}
    </form>
  );
}
