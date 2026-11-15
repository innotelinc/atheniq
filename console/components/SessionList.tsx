"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { passkeyStepUp } from "@/lib/passkey-client";

export interface SessionEntry {
  id: string;
  name: string;
  email: string;
  source: string;
  createdAt: string;
  expiresAt: string;
  /** Time until the session expires, phrased for reading, e.g. "7h 12m left". */
  remaining: string;
  /** First sign-in this person has ever made from this source. */
  newSource: boolean;
  current: boolean;
}

type Pending = { kind: "one"; entry: SessionEntry } | { kind: "all" };

/**
 * Every sign-in that can still reach the console, with the source it came from.
 * Ending one is immediate; ending all of them includes this browser, so it lands
 * on the sign-in page rather than pretending it survived. When the registrar has
 * a second factor, ending anyone else's session asks for a fresh code or a
 * passkey confirmation first.
 */
export function SessionList({
  entries,
  stepUp,
  confirmed,
  passkeyCount,
}: {
  entries: SessionEntry[];
  stepUp: boolean;
  /** A confirmation in this session is still fresh; skip the prompt. */
  confirmed: boolean;
  passkeyCount: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [code, setCode] = useState("");
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function endSession(entry: SessionEntry, proof = "", ticket = "") {
    setBusy(entry.id);
    setError(null);
    setNotice(null);
    const result = await api<{ ended: number }>("/api/security/sessions", {
      method: "POST",
      body: JSON.stringify({ scope: "session", id: entry.id, code: proof, stepUp: ticket }),
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.error ?? "That did not work.");
      // The remembered confirmation may have lapsed while the page was open.
      if (stepUp && !entry.current && !proof && !ticket) setPending({ kind: "one", entry });
      return;
    }
    setPending(null);
    setCode("");
    if (entry.current) {
      router.push("/login");
      return;
    }
    setNotice(`${entry.name}'s session from ${entry.source} has ended.`);
    router.refresh();
  }

  async function endAll(proof = "", ticket = "") {
    setBusy("all");
    setError(null);
    setNotice(null);
    const result = await api<{ ended: number }>("/api/security/sessions", {
      method: "POST",
      body: JSON.stringify({ scope: "all", code: proof, stepUp: ticket }),
    });
    setBusy(null);
    setConfirming(false);
    if (!result.ok) {
      setError(result.error ?? "That did not work.");
      if (stepUp && !proof && !ticket) {
        setConfirming(true);
        setPending({ kind: "all" });
      }
      return;
    }
    // This browser was one of the sessions that just ended.
    router.push("/login");
  }

  function requestEnd(entry: SessionEntry) {
    setError(null);
    setNotice(null);
    if (!stepUp || entry.current || confirmed) {
      void endSession(entry);
      return;
    }
    setCode("");
    setPending({ kind: "one", entry });
  }

  function requestEndAll() {
    setError(null);
    setNotice(null);
    if (!stepUp || confirmed) {
      void endAll();
      return;
    }
    setCode("");
    setPending({ kind: "all" });
  }

  function confirmPending() {
    if (!pending) return;
    if (pending.kind === "one") void endSession(pending.entry, code);
    else void endAll(code);
  }

  /** A completed passkey ceremony is itself the confirmation. */
  async function confirmWithPasskey() {
    if (!pending) return;
    setPasskeyBusy(true);
    setError(null);
    setNotice(null);
    const step = await passkeyStepUp();
    if (!step.ok) {
      setPasskeyBusy(false);
      setError(step.error);
      return;
    }
    if (pending.kind === "one") await endSession(pending.entry, "", step.ticket);
    else await endAll("", step.ticket);
    setPasskeyBusy(false);
  }

  if (entries.length === 0) {
    return <span className="small muted">No session can reach the console right now.</span>;
  }

  return (
    <div className="stack-sm">
      {entries.map((entry) => (
        <div key={entry.id} className="between" style={{ alignItems: "flex-start" }}>
          <div>
            <div className="small strong">
              {entry.name}
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
              {entry.email} · from {entry.source}
            </div>
            <div className="tiny muted">
              started {entry.createdAt} · ends {entry.expiresAt} · {entry.remaining}
            </div>
          </div>
          <button
            className="btn small ghost"
            type="button"
            disabled={busy === entry.id}
            onClick={() => requestEnd(entry)}
          >
            {busy === entry.id ? "Ending…" : entry.current ? "Sign out" : "End"}
          </button>
        </div>
      ))}

      {pending && (
        <div className="field" style={{ maxWidth: 360 }}>
          <label className="tiny muted" htmlFor="session-step-up">
            Authenticator code
          </label>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <input
              id="session-step-up"
              className="input"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="123456"
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
            <button className="btn small" type="button" onClick={confirmPending} disabled={busy !== null || passkeyBusy}>
              Confirm
            </button>
            {passkeyCount > 0 && (
              <button
                className="btn small ghost"
                type="button"
                onClick={() => void confirmWithPasskey()}
                disabled={busy !== null || passkeyBusy}
              >
                {passkeyBusy ? "Waiting for your device…" : "Use a passkey"}
              </button>
            )}
            <button
              className="btn small ghost"
              type="button"
              onClick={() => {
                setPending(null);
                setCode("");
              }}
              disabled={busy !== null || passkeyBusy}
            >
              Cancel
            </button>
          </div>
          <span className="tiny muted">
            Ending a session other than your own needs a fresh code from your authenticator, or a passkey.
          </span>
        </div>
      )}

      {notice && <span className="chip ok">{notice}</span>}
      {error && <span className="chip danger">{error}</span>}
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        {!confirming ? (
          <button className="btn small danger" type="button" onClick={() => setConfirming(true)}>
            Sign out everywhere
          </button>
        ) : (
          <>
            <button className="btn small danger" type="button" onClick={requestEndAll} disabled={busy === "all"}>
              {busy === "all" ? "Ending…" : `Yes, end all ${entries.length}`}
            </button>
            <button
              className="btn small ghost"
              type="button"
              onClick={() => setConfirming(false)}
              disabled={busy === "all"}
            >
              Keep them
            </button>
          </>
        )}
      </div>
      <span className="tiny muted">
        Signing out everywhere ends every session above, this one included; each person signs in again with their second
        factor. Ending one session takes effect immediately, even if that browser stays open.{" "}
        <strong>new source</strong> marks the first sign-in that person has made from that address since their account was
        created, so a session from somewhere they have never used stands out; it clears once they sign in from there
        again. Each session ends by itself when its time is up.
      </span>
    </div>
  );
}
