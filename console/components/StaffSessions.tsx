"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { passkeyStepUp } from "@/lib/passkey-client";

export interface StaffSessionEntry {
  id: string;
  source: string;
  createdAt: string;
  expiresAt: string;
  /** Time until the session expires, phrased for reading, e.g. "7h 12m left". */
  remaining: string;
  /** First sign-in this person has ever made from this source. */
  newSource: boolean;
  current: boolean;
}

/**
 * One person's live sign-ins, with a single action that ends all of them. The
 * route is registrar-only; ending a set that includes this browser sends it to
 * the sign-in page rather than a console that will refuse it. Ending someone
 * else's sessions asks for a fresh code or a passkey confirmation when the
 * registrar has a second factor.
 */
export function StaffSessions({
  staffId,
  name,
  entries,
  stepUp,
  confirmed,
  passkeyCount,
  self,
}: {
  staffId: string;
  name: string;
  entries: StaffSessionEntry[];
  stepUp: boolean;
  /** A confirmation in this session is still fresh; skip the prompt. */
  confirmed: boolean;
  passkeyCount: number;
  self: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [code, setCode] = useState("");
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function endAll(proof = "", ticket = "") {
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await api<{ ended: number }>("/api/security/sessions", {
      method: "POST",
      body: JSON.stringify({ scope: "staff", staffId, code: proof, stepUp: ticket }),
    });
    setBusy(false);
    setConfirming(false);
    setPending(false);
    setCode("");
    if (!result.ok) {
      setError(result.error ?? "That did not work.");
      // The remembered confirmation may have lapsed while the page was open.
      if (stepUp && !proof && !ticket) setPending(true);
      return;
    }
    if (entries.some((entry) => entry.current)) {
      router.push("/login");
      return;
    }
    setNotice(`Ended ${result.data?.ended ?? entries.length} live session(s) for ${name}.`);
    router.refresh();
  }

  function requestEndAll() {
    setError(null);
    setNotice(null);
    if (!stepUp || self || confirmed) {
      void endAll();
      return;
    }
    setCode("");
    setPending(true);
  }

  async function confirmWithPasskey() {
    setPasskeyBusy(true);
    setError(null);
    setNotice(null);
    const step = await passkeyStepUp();
    if (!step.ok) {
      setPasskeyBusy(false);
      setError(step.error);
      return;
    }
    await endAll("", step.ticket);
    setPasskeyBusy(false);
  }

  if (entries.length === 0) {
    return <span className="small muted">No session can reach the console for this account right now.</span>;
  }

  return (
    <div className="stack-sm">
      {entries.map((entry) => (
        <div key={entry.id} className="between" style={{ alignItems: "flex-start" }}>
          <div>
            <div className="small strong">
              from {entry.source}
              {entry.current && (
                <span className="chip ok" style={{ marginLeft: 8 }}>
                  this browser
                </span>
              )}
              {entry.newSource && (
                <span className="chip warn" style={{ marginLeft: 8 }}>
                  new source
                </span>
              )}
            </div>
            <div className="tiny muted">
              started {entry.createdAt} · ends {entry.expiresAt} · {entry.remaining}
            </div>
          </div>
        </div>
      ))}

      {pending && (
        <div className="field" style={{ maxWidth: 360 }}>
          <label className="tiny muted" htmlFor="staff-step-up">
            Authenticator code
          </label>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input
              id="staff-step-up"
              className="input"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="123456"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            <button className="btn small" type="button" onClick={() => void endAll(code)} disabled={busy || passkeyBusy}>
              Confirm
            </button>
            {passkeyCount > 0 && (
              <button
                className="btn small ghost"
                type="button"
                onClick={() => void confirmWithPasskey()}
                disabled={busy || passkeyBusy}
              >
                {passkeyBusy ? "Waiting for your device…" : "Use a passkey"}
              </button>
            )}
            <button
              className="btn small ghost"
              type="button"
              onClick={() => {
                setPending(false);
                setCode("");
              }}
              disabled={busy || passkeyBusy}
            >
              Cancel
            </button>
          </div>
          <span className="tiny muted">
            Ending another person&apos;s sessions needs a fresh code from your authenticator, or a passkey.
          </span>
        </div>
      )}

      {notice && <span className="chip ok">{notice}</span>}
      {error && <span className="chip danger">{error}</span>}
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        {!confirming ? (
          <button className="btn small danger" type="button" onClick={() => setConfirming(true)}>
            End all for {name}
          </button>
        ) : (
          <>
            <button className="btn small danger" type="button" onClick={requestEndAll} disabled={busy}>
              {busy ? "Ending…" : `Yes, end all ${entries.length}`}
            </button>
            <button className="btn small ghost" type="button" onClick={() => setConfirming(false)} disabled={busy}>
              Keep them
            </button>
          </>
        )}
      </div>
    </div>
  );
}
