"use client";

import { useState } from "react";
import { api } from "@/lib/client";

export function AccessRequestForm({ domains }: { domains: string[] }) {
  const [form, setForm] = useState({ name: "", email: "", title: "", reason: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const result = await api("/api/access-requests", { method: "POST", body: JSON.stringify(form) });
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? "Could not send the request.");
      return;
    }
    setSent(true);
  }

  if (sent) {
    return (
      <div className="stack">
        <span className="chip ok">Request sent</span>
        <p className="small" style={{ margin: 0 }}>
          A registrar reviews requests before an account is opened. Once yours is approved you can sign in with{" "}
          <strong>{form.email}</strong> and the password you chose.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="stack">
      <label className="stack-sm">
        <span className="small muted">Full name</span>
        <input className="input" value={form.name} onChange={(event) => set("name", event.target.value)} required />
      </label>
      <label className="stack-sm">
        <span className="small muted">
          Work email — one of {domains.map((domain) => `@${domain}`).join(", ")}
        </span>
        <input
          className="input"
          type="email"
          value={form.email}
          onChange={(event) => set("email", event.target.value)}
          required
        />
      </label>
      <label className="stack-sm">
        <span className="small muted">Title (optional)</span>
        <input className="input" value={form.title} onChange={(event) => set("title", event.target.value)} />
      </label>
      <label className="stack-sm">
        <span className="small muted">What do you need access to?</span>
        <textarea
          className="input"
          rows={3}
          value={form.reason}
          onChange={(event) => set("reason", event.target.value)}
          placeholder="Publishing courses for the spring term"
        />
      </label>
      <label className="stack-sm">
        <span className="small muted">Choose a password (at least 10 characters)</span>
        <input
          className="input"
          type="password"
          minLength={10}
          value={form.password}
          onChange={(event) => set("password", event.target.value)}
          autoComplete="new-password"
          required
        />
      </label>
      {error && <span className="chip danger">{error}</span>}
      <button className="btn primary" type="submit" disabled={busy}>
        {busy ? "Sending…" : "Request an account"}
      </button>
      <span className="tiny muted">
        The password is stored hashed and only becomes an account if a registrar approves the request.
      </span>
    </form>
  );
}
