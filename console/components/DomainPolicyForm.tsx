"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";

/**
 * The sign-in policy: which email domains may hold an account, and whether an
 * authenticator code is required on every sign-in.
 */
export function DomainPolicyForm({
  domains,
  require2fa,
  blocked,
}: {
  domains: string[];
  require2fa: boolean;
  blocked: string[];
}) {
  const router = useRouter();
  const [text, setText] = useState(domains.join(", "));
  const [twoFactor, setTwoFactor] = useState(require2fa);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const allowedDomains = text
      .split(/[,\s]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    const result = await api("/api/integrations", {
      method: "PUT",
      body: JSON.stringify({ auth: { allowedDomains, require2fa: twoFactor } }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? "Could not save the sign-in policy.");
      return;
    }
    setMessage(
      allowedDomains.length
        ? `Only ${allowedDomains.map((domain) => `@${domain}`).join(", ")} can sign in.`
        : "Saved — but with no domains listed, nobody can hold an account. Add at least one.",
    );
    router.refresh();
  }

  return (
    <form onSubmit={save} className="card">
      <header className="card-head">
        <div>
          <h2 className="card-title">Sign-in policy</h2>
          <div className="card-sub">Accounts are limited to registered domains, and every sign-in needs a second factor.</div>
        </div>
        <span className={`chip ${twoFactor ? "ok" : "warn"}`}>{twoFactor ? "2FA required" : "2FA optional"}</span>
      </header>
      <div className="card-body stack-sm">
        <label className="label" htmlFor="allowed-domains">
          Registered domains
        </label>
        <input
          id="allowed-domains"
          className="input"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="innotel.us, atheniq.institute"
        />
        <span className="tiny muted">
          A staff email must end with one of these domains; subdomains are allowed, look-alikes are not. Changing the
          list blocks existing accounts outside it from signing in — it never deletes them.
        </span>

        <label className="row small" style={{ gap: 8 }}>
          <input type="checkbox" checked={twoFactor} onChange={(event) => setTwoFactor(event.target.checked)} />
          Require an authenticator code for every sign-in
        </label>

        {blocked.length > 0 && (
          <div className="banner warn">
            <div>
              <div className="banner-title">Accounts outside the list</div>
              {blocked.join(", ")} — these people will be refused at sign-in until you add their domain or disable
              the account.
            </div>
          </div>
        )}

        <div className="row">
          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save policy"}
          </button>
          {message && <span className="chip ok">{message}</span>}
          {error && <span className="chip danger">{error}</span>}
        </div>
      </div>
    </form>
  );
}
