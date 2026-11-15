"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";

/**
 * Ends the five-minute confirmation memory early. Nothing else changes: the
 * next destructive action simply asks for a code or passkey again.
 */
export function ClearConfirmation() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function clear() {
    setBusy(true);
    setError(null);
    const result = await api("/api/auth/confirm/clear", { method: "POST", body: "{}" });
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? "That did not work.");
      return;
    }
    router.refresh();
  }

  return (
    <>
      <button className="btn small ghost" type="button" onClick={() => void clear()} disabled={busy}>
        {busy ? "Forgetting…" : "Forget"}
      </button>
      {error && <span className="chip danger">{error}</span>}
    </>
  );
}
