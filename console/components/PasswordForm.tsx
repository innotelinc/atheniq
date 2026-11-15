"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/client";

/** Change your own console password, after proving the current one. */
export function PasswordForm() {
  const router = useRouter();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const mismatch = form.confirm.length > 0 && form.next !== form.confirm;
  const ready = form.current.length > 0 && form.next.length >= 10 && form.next === form.confirm;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await api<{ sessionsEnded?: number }>("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ current: form.current, next: form.next }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? "That did not work.");
      return;
    }
    const ended = result.data?.sessionsEnded ?? 0;
    setNotice(
      `Password changed.${ended > 0 ? ` ${ended} other session(s) signed out.` : ""} Next time, sign in with the new one.`,
    );
    setForm({ current: "", next: "", confirm: "" });
    router.refresh();
  }

  return (
    <form className="stack-sm" onSubmit={submit} style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
      <div className="small strong">Change your password</div>
      <div className="field">
        <label className="label" htmlFor="current-password">
          Current password
        </label>
        <input
          id="current-password"
          className="input"
          type="password"
          autoComplete="current-password"
          value={form.current}
          onChange={(event) => setForm((prev) => ({ ...prev, current: event.target.value }))}
          required
        />
      </div>
      <div className="field">
        <label className="label" htmlFor="next-password">
          New password
        </label>
        <input
          id="next-password"
          className="input"
          type="password"
          autoComplete="new-password"
          minLength={10}
          value={form.next}
          onChange={(event) => setForm((prev) => ({ ...prev, next: event.target.value }))}
          required
        />
      </div>
      <div className="field">
        <label className="label" htmlFor="confirm-password">
          Repeat it
        </label>
        <input
          id="confirm-password"
          className="input"
          type="password"
          autoComplete="new-password"
          minLength={10}
          value={form.confirm}
          onChange={(event) => setForm((prev) => ({ ...prev, confirm: event.target.value }))}
          required
        />
      </div>
      <button className="btn small primary" type="submit" disabled={!ready || busy}>
        {busy ? "Changing…" : "Change password"}
      </button>
      {mismatch && <span className="chip warn">The two new passwords do not match.</span>}
      {error && <span className="chip danger">{error}</span>}
      {notice && <span className="chip ok">{notice}</span>}
      <span className="tiny muted">
        At least 10 characters. Your other sessions are signed out; this one keeps working. The vault has its own
        password and is not changed here.
      </span>
    </form>
  );
}
