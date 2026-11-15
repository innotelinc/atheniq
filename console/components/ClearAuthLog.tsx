"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";

export function ClearAuthLog({ count }: { count: number }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function clear() {
    setBusy(true);
    setError(null);
    const result = await api<{ cleared: number }>("/api/auth/log", { method: "DELETE" });
    setBusy(false);
    setConfirming(false);
    if (!result.ok) {
      setError(result.error ?? "Could not clear the log.");
      return;
    }
    setNotice(`Cleared ${result.data?.cleared ?? count} ${count === 1 ? "entry" : "entries"}.`);
    router.refresh();
  }

  return (
    <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
      {notice && <span className="chip ok">{notice}</span>}
      {error && <span className="chip danger">{error}</span>}
      {!notice && !confirming && (
        <button className="btn small ghost" type="button" onClick={() => setConfirming(true)}>
          Clear log
        </button>
      )}
      {confirming && (
        <>
          <button className="btn small danger" type="button" onClick={clear} disabled={busy}>
            {busy ? "Clearing…" : `Yes, clear ${count}`}
          </button>
          <button className="btn small ghost" type="button" onClick={() => setConfirming(false)} disabled={busy}>
            Keep them
          </button>
        </>
      )}
    </div>
  );
}
