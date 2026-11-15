"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";

export interface PausedEntry {
  kind: "email" | "source";
  value: string;
  attempts: number;
  retryAfterSeconds: number;
}

export function LockoutList({ entries }: { entries: PausedEntry[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function unlock(entry: PausedEntry) {
    const key = `${entry.kind}:${entry.value}`;
    setBusy(key);
    setError(null);
    setNotice(null);
    const result = await api<{ removed: number }>("/api/security/unlock", {
      method: "POST",
      body: JSON.stringify({ kind: entry.kind, value: entry.value }),
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error ?? "That did not work.");
      return;
    }
    setNotice(`${entry.value} can sign in again.`);
    router.refresh();
  }

  if (entries.length === 0) {
    return <span className="small muted">Nothing is paused.</span>;
  }

  return (
    <div className="stack-sm">
      {entries.map((entry) => {
        const key = `${entry.kind}:${entry.value}`;
        return (
          <div key={key} className="between" style={{ alignItems: "flex-start" }}>
            <div>
              <div className="small strong mono">{entry.value}</div>
              <div className="tiny muted">
                {entry.attempts} refusals · {entry.kind === "email" ? "password and codes" : "every password and code sign-in from here"} ·
                about {Math.max(1, Math.ceil(entry.retryAfterSeconds / 60))} min left
              </div>
            </div>
            <button
              className="btn small ghost"
              type="button"
              disabled={busy === key}
              onClick={() => unlock(entry)}
            >
              {busy === key ? "Unlocking…" : "Unlock"}
            </button>
          </div>
        );
      })}
      {notice && <span className="chip ok">{notice}</span>}
      {error && <span className="chip danger">{error}</span>}
    </div>
  );
}
