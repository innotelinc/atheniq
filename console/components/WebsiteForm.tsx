"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { LogoPlacement, Settings } from "@/lib/types";

/**
 * The school's own details, not a site builder. The website at atheniq.institute
 * is `web/landing/` in this repository and is published from git, so what this
 * form owns is what the console and the institute are called, where admissions
 * is written, and which domain the school answers on.
 */
export function WebsiteForm({ settings }: { settings: Settings }) {
  const router = useRouter();
  const [brand, setBrand] = useState(settings.brand);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function setB<K extends keyof typeof brand>(key: K, value: (typeof brand)[K]) {
    setBrand((current) => ({ ...current, [key]: value }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await api<Settings>("/api/integrations", {
      method: "PUT",
      body: JSON.stringify({ brand }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? "Could not save the website settings.");
      return;
    }
    setMessage("Saved — the school's details are updated.");
    router.refresh();
  }

  const placements: LogoPlacement[] = ["left", "center", "right"];

  return (
    <form onSubmit={save} className="stack mt">
      <div className="split">
        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">The institute</h2>
              <div className="card-sub">What the school is called, and how it signs itself.</div>
            </div>
          </header>
          <div className="card-body stack-sm">
            <label className="label" htmlFor="site-name">
              Institution name
            </label>
            <input
              id="site-name"
              className="input"
              value={brand.siteName}
              onChange={(event) => setB("siteName", event.target.value)}
              placeholder="Your school"
            />

            <label className="label" htmlFor="site-tagline">
              Tagline
            </label>
            <input
              id="site-tagline"
              className="input"
              value={brand.tagline}
              onChange={(event) => setB("tagline", event.target.value)}
            />

            <label className="label" htmlFor="logo-url">
              Logo image URL
            </label>
            <input
              id="logo-url"
              className="input"
              value={brand.logoUrl}
              onChange={(event) => setB("logoUrl", event.target.value)}
              placeholder="https://…/logo.svg — leave empty to use the monogram"
            />
            <div className="row" style={{ gap: 8 }}>
              <div style={{ flex: 1 }}>
                <label className="label" htmlFor="logo-text">
                  Monogram
                </label>
                <input
                  id="logo-text"
                  className="input"
                  maxLength={3}
                  value={brand.logoText}
                  onChange={(event) => setB("logoText", event.target.value)}
                  placeholder="AI"
                />
              </div>
              <div>
                <label className="label" htmlFor="accent">
                  Accent
                </label>
                <input
                  id="accent"
                  className="input"
                  type="color"
                  value={brand.accent}
                  onChange={(event) => setB("accent", event.target.value)}
                  style={{ width: 64, padding: 4 }}
                />
              </div>
            </div>

            <span className="label">Logo placement</span>
            <div className="row" style={{ gap: 6 }}>
              {placements.map((placement) => (
                <button
                  key={placement}
                  type="button"
                  className={`btn small ${brand.logoPlacement === placement ? "primary" : "ghost"}`}
                  onClick={() => setB("logoPlacement", placement)}
                >
                  {placement[0].toUpperCase() + placement.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">Domain and contact</h2>
              <div className="card-sub">Where the school answers, and where an applicant writes.</div>
            </div>
          </header>
          <div className="card-body stack-sm">
            <label className="label" htmlFor="domain">
              Public domain
            </label>
            <input
              id="domain"
              className="input"
              value={brand.domain}
              onChange={(event) => setB("domain", event.target.value)}
              placeholder="atheniq.institute"
            />
            <span className="tiny muted">
              The name the website is published under. The site itself is served from the repository's{" "}
              <span className="mono">web/landing</span> — this field is what every link and every email here points at.
            </span>

            <label className="label" htmlFor="support-email">
              Admissions email
            </label>
            <input
              id="support-email"
              className="input"
              type="email"
              value={brand.supportEmail}
              onChange={(event) => setB("supportEmail", event.target.value)}
            />

            <label className="row small" style={{ gap: 8, marginTop: 4 }}>
              <input
                type="checkbox"
                checked={brand.poweredBy}
                onChange={(event) => setB("poweredBy", event.target.checked)}
              />
              Show “Powered by AthenIQ” in the footer
            </label>

            <div className="row" style={{ gap: 8, marginTop: 6 }}>
              <button className="btn primary" type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save website settings"}
              </button>
            </div>
            {message && <span className="chip ok">{message}</span>}
            {error && <span className="chip danger">{error}</span>}
          </div>
        </section>
      </div>
    </form>
  );
}
