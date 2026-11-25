"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import type { LogoPlacement, Settings } from "@/lib/types";

export function WebsiteForm({ settings }: { settings: Settings }) {
  const router = useRouter();
  const [brand, setBrand] = useState(settings.brand);
  const [site, setSite] = useState(settings.site);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function setB<K extends keyof typeof brand>(key: K, value: (typeof brand)[K]) {
    setBrand((current) => ({ ...current, [key]: value }));
  }
  function setS<K extends keyof typeof site>(key: K, value: (typeof site)[K]) {
    setSite((current) => ({ ...current, [key]: value }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const result = await api<Settings>("/api/integrations", {
      method: "PUT",
      body: JSON.stringify({ brand, site }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error ?? "Could not save the website settings.");
      return;
    }
    setMessage(site.published ? "Saved — the public site is live." : "Saved — the public site is offline.");
    router.refresh();
  }

  const placements: LogoPlacement[] = ["left", "center", "right"];

  return (
    <form onSubmit={save} className="stack mt">
      <div className="split">
        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">Brand</h2>
              <div className="card-sub">What a visitor sees. This is the white-label surface.</div>
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

            <label className="row small" style={{ gap: 8, marginTop: 4 }}>
              <input
                type="checkbox"
                checked={brand.poweredBy}
                onChange={(event) => setB("poweredBy", event.target.checked)}
              />
              Show “Powered by AthenIQ” in the footer
            </label>
          </div>
        </section>

        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">Public site</h2>
              <div className="card-sub">Copy, sections and whether the domain answers.</div>
            </div>
          </header>
          <div className="card-body stack-sm">
            <label className="row small" style={{ gap: 8 }}>
              <input
                type="checkbox"
                checked={site.published}
                onChange={(event) => setS("published", event.target.checked)}
              />
              Publish the site at {brand.domain}
            </label>

            <label className="label" htmlFor="headline">
              Headline
            </label>
            <input
              id="headline"
              className="input"
              value={site.headline}
              onChange={(event) => setS("headline", event.target.value)}
            />

            <label className="label" htmlFor="intro">
              Introduction
            </label>
            <textarea
              id="intro"
              className="input"
              rows={4}
              value={site.intro}
              onChange={(event) => setS("intro", event.target.value)}
            />

            <div className="row" style={{ gap: 8 }}>
              <div style={{ flex: 1 }}>
                <label className="label" htmlFor="cta-label">
                  Button label
                </label>
                <input
                  id="cta-label"
                  className="input"
                  value={site.ctaLabel}
                  onChange={(event) => setS("ctaLabel", event.target.value)}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="label" htmlFor="cta-href">
                  Button link
                </label>
                <input
                  id="cta-href"
                  className="input"
                  value={site.ctaHref}
                  onChange={(event) => setS("ctaHref", event.target.value)}
                />
              </div>
            </div>

            <label className="row small" style={{ gap: 8 }}>
              <input
                type="checkbox"
                checked={site.showPrices}
                onChange={(event) => setS("showPrices", event.target.checked)}
              />
              Show tuition and course prices (USD)
            </label>
            <label className="row small" style={{ gap: 8 }}>
              <input
                type="checkbox"
                checked={site.showPrograms}
                onChange={(event) => setS("showPrograms", event.target.checked)}
              />
              Show degree programs
            </label>
            <label className="row small" style={{ gap: 8 }}>
              <input
                type="checkbox"
                checked={site.showVerify}
                onChange={(event) => setS("showVerify", event.target.checked)}
              />
              Show the public verification link
            </label>

            <div className="row" style={{ gap: 8, marginTop: 6 }}>
              <button className="btn primary" type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save website"}
              </button>
              <Link className="btn ghost" href="/site" target="_blank">
                Preview
              </Link>
            </div>
            {message && <span className="chip ok">{message}</span>}
            {error && <span className="chip danger">{error}</span>}
          </div>
        </section>
      </div>
    </form>
  );
}
