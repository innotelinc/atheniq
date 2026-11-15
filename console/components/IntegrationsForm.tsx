"use client";

import { useState } from "react";
import { api } from "@/lib/client";

interface SettingsShape {
  org: string;
  orgShort: string;
  defaultTerm: string;
  tuitionPerCreditCents: number;
  applicationFeeCents: number;
  graduationFeeCents: number;
  lms: { baseUrl: string; studioUrl: string; catalogUrl: string; importUrl: string; apiToken: string };
  signara: { baseUrl: string; apiKey: string; autoSign: boolean; defaultTemplate: string };
  ai: { baseUrl: string; apiKey: string; model: string };
  signer: { name: string; title: string; email: string };
  sites: { instituteUrl: string; coursesUrl: string; workforceUrl: string };
  configured: { signara: boolean; ai: boolean; lmsImport: boolean };
}

type Target = "signara" | "ai" | "lms";

/** Dollars in the form, cents in the store: every amount is entered and read as USD. */
function toDollars(cents: number): string {
  return (cents / 100).toFixed(2);
}

function toCents(dollars: string): number {
  const amount = Number(dollars.replace(/[^0-9.]/g, ""));
  return Number.isFinite(amount) ? Math.round(amount * 100) : 0;
}

export function IntegrationsForm({ settings }: { settings: SettingsShape }) {
  const [form, setForm] = useState(settings);
  const [fees, setFees] = useState({
    tuition: toDollars(settings.tuitionPerCreditCents),
    application: toDollars(settings.applicationFeeCents),
    graduation: toDollars(settings.graduationFeeCents),
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [probe, setProbe] = useState<Record<string, { ok: boolean; detail: string; http?: number | null }>>({});
  const [probing, setProbing] = useState<Target | null>(null);

  function set<T extends keyof SettingsShape>(key: T, value: SettingsShape[T]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function save() {
    setSaving(true);
    setMessage(null);
    const result = await api<SettingsShape>("/api/integrations", {
      method: "PUT",
      body: JSON.stringify({
        org: form.org,
        orgShort: form.orgShort,
        defaultTerm: form.defaultTerm,
        tuitionPerCreditCents: toCents(fees.tuition),
        applicationFeeCents: toCents(fees.application),
        graduationFeeCents: toCents(fees.graduation),
        lms: form.lms,
        signara: form.signara,
        ai: form.ai,
        signer: form.signer,
        sites: form.sites,
      }),
    });
    setSaving(false);
    if (!result.ok) {
      setMessage({ tone: "bad", text: result.error ?? "Could not save settings." });
      return;
    }
    if (result.data) {
      setForm(result.data);
      setFees({
        tuition: toDollars(result.data.tuitionPerCreditCents),
        application: toDollars(result.data.applicationFeeCents),
        graduation: toDollars(result.data.graduationFeeCents),
      });
    }
    setMessage({ tone: "ok", text: "Saved. Probes use the saved values." });
  }

  async function test(target: Target) {
    setProbing(target);
    const result = await api<{ ok: boolean; detail: string; http?: number | null }>(
      "/api/integrations/test",
      { method: "POST", body: JSON.stringify({ target }) },
    );
    setProbing(null);
    setProbe((prev) => ({
      ...prev,
      [target]: { ok: Boolean(result.data?.ok), detail: result.data?.detail ?? result.error ?? "No response." },
    }));
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head">
          <div>
            <h2 className="card-title">Institution</h2>
            <div className="card-sub">Names, fees and the default term new records start in.</div>
          </div>
        </div>
        <div className="card-body form-grid">
          <div className="field">
            <label className="label">Published name</label>
            <input className="input" value={form.org} onChange={(e) => set("org", e.target.value)} />
          </div>
          <div className="field">
            <label className="label">Course-key org</label>
            <input className="input" value={form.orgShort} onChange={(e) => set("orgShort", e.target.value)} />
            <span className="hint">course-v1:{form.orgShort || "ORG"}+CODE+TERM</span>
          </div>
          <div className="field">
            <label className="label">Default term</label>
            <input className="input" value={form.defaultTerm} onChange={(e) => set("defaultTerm", e.target.value)} />
          </div>
          <div className="field">
            <label className="label">Tuition per credit (USD)</label>
            <input
              className="input"
              inputMode="decimal"
              value={fees.tuition}
              onChange={(e) => setFees({ ...fees, tuition: e.target.value })}
            />
          </div>
          <div className="field">
            <label className="label">Application fee (USD)</label>
            <input
              className="input"
              inputMode="decimal"
              value={fees.application}
              onChange={(e) => setFees({ ...fees, application: e.target.value })}
            />
          </div>
          <div className="field">
            <label className="label">Graduation fee (USD)</label>
            <input
              className="input"
              inputMode="decimal"
              value={fees.graduation}
              onChange={(e) => setFees({ ...fees, graduation: e.target.value })}
            />
          </div>
          <div className="field span-2">
            <span className="hint">
              Dollars, not cents. Amounts are shown as USD across the console and the public site.
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Course engine — Open edX</h2>
              <div className="card-sub">Where published courses are imported and listed.</div>
            </div>
            <span className={`chip ${form.configured.lmsImport ? "ok" : "warn"}`}>
              {form.configured.lmsImport ? "Import wired" : "Bundle only"}
            </span>
          </div>
          <div className="card-body stack">
            <div className="field">
              <label className="label">LMS base URL</label>
              <input
                className="input"
                value={form.lms.baseUrl}
                onChange={(e) => set("lms", { ...form.lms, baseUrl: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">Catalog URL</label>
              <input
                className="input"
                value={form.lms.catalogUrl}
                onChange={(e) => set("lms", { ...form.lms, catalogUrl: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">Course import endpoint</label>
              <input
                className="input"
                value={form.lms.importUrl}
                placeholder="https://…/api/courses/v1/import/ (leave blank to build the bundle only)"
                onChange={(e) => set("lms", { ...form.lms, importUrl: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">Import API token</label>
              <input
                className="input"
                type="password"
                value={form.lms.apiToken}
                placeholder="not set"
                onChange={(e) => set("lms", { ...form.lms, apiToken: e.target.value })}
              />
            </div>
            <div className="row">
              <button className="btn small" type="button" onClick={() => test("lms")} disabled={probing !== null}>
                {probing === "lms" ? "Testing…" : "Test LMS"}
              </button>
              {probe.lms && <span className={`chip ${probe.lms.ok ? "ok" : "bad"}`}>{probe.lms.detail}</span>}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Signara — signing</h2>
              <div className="card-sub">Document upload, signing request and signature.</div>
            </div>
            <span className={`chip ${form.configured.signara ? "ok" : "warn"}`}>
              {form.configured.signara ? "Key set" : "No key"}
            </span>
          </div>
          <div className="card-body stack">
            <div className="field">
              <label className="label">API base</label>
              <input
                className="input"
                value={form.signara.baseUrl}
                onChange={(e) => set("signara", { ...form.signara, baseUrl: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">API key (X-API-Key)</label>
              <input
                className="input"
                type="password"
                value={form.signara.apiKey}
                placeholder="not set"
                onChange={(e) => set("signara", { ...form.signara, apiKey: e.target.value })}
              />
              <span className="hint">Stored server-side in data/store.json; never sent to the browser.</span>
            </div>
            <div className="field">
              <label className="label">Default template</label>
              <input
                className="input"
                value={form.signara.defaultTemplate}
                onChange={(e) => set("signara", { ...form.signara, defaultTemplate: e.target.value })}
              />
            </div>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={form.signara.autoSign}
                onChange={(e) => set("signara", { ...form.signara, autoSign: e.target.checked })}
              />
              Sign automatically as the issuer (typed signature)
            </label>
            <div className="row">
              <button className="btn small" type="button" onClick={() => test("signara")} disabled={probing !== null}>
                {probing === "signara" ? "Testing…" : "Test Signara"}
              </button>
              {probe.signara && <span className={`chip ${probe.signara.ok ? "ok" : "bad"}`}>{probe.signara.detail}</span>}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Model gateway</h2>
              <div className="card-sub">OpenAI-compatible; OmniRoute in the AthenIQ stack.</div>
            </div>
            <span className={`chip ${form.configured.ai ? "ok" : "warn"}`}>
              {form.configured.ai ? "Key set" : "No key"}
            </span>
          </div>
          <div className="card-body stack">
            <div className="field">
              <label className="label">Base URL</label>
              <input
                className="input"
                value={form.ai.baseUrl}
                onChange={(e) => set("ai", { ...form.ai, baseUrl: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">API key</label>
              <input
                className="input"
                type="password"
                value={form.ai.apiKey}
                placeholder="not set"
                onChange={(e) => set("ai", { ...form.ai, apiKey: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">Model</label>
              <input
                className="input"
                value={form.ai.model}
                onChange={(e) => set("ai", { ...form.ai, model: e.target.value })}
              />
            </div>
            <div className="row">
              <button className="btn small" type="button" onClick={() => test("ai")} disabled={probing !== null}>
                {probing === "ai" ? "Testing…" : "Test gateway"}
              </button>
              {probe.ai && <span className={`chip ${probe.ai.ok ? "ok" : "bad"}`}>{probe.ai.detail}</span>}
            </div>
            <div className="banner">
              <div>
                Without a key the course studio uses the deterministic curriculum engine — the flow, validation and
                publishing are identical.
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Signatory & sites</h2>
              <div className="card-sub">Who signs, and the public surfaces this catalog feeds.</div>
            </div>
          </div>
          <div className="card-body stack">
            <div className="form-grid">
              <div className="field">
                <label className="label">Signatory name</label>
                <input
                  className="input"
                  value={form.signer.name}
                  onChange={(e) => set("signer", { ...form.signer, name: e.target.value })}
                />
              </div>
              <div className="field">
                <label className="label">Title</label>
                <input
                  className="input"
                  value={form.signer.title}
                  onChange={(e) => set("signer", { ...form.signer, title: e.target.value })}
                />
              </div>
              <div className="field span-2">
                <label className="label">Email</label>
                <input
                  className="input"
                  value={form.signer.email}
                  onChange={(e) => set("signer", { ...form.signer, email: e.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label className="label">Institute site</label>
              <input
                className="input"
                value={form.sites.instituteUrl}
                onChange={(e) => set("sites", { ...form.sites, instituteUrl: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">Courses site</label>
              <input
                className="input"
                value={form.sites.coursesUrl}
                onChange={(e) => set("sites", { ...form.sites, coursesUrl: e.target.value })}
              />
            </div>
            <div className="field">
              <label className="label">Workforce site</label>
              <input
                className="input"
                value={form.sites.workforceUrl}
                onChange={(e) => set("sites", { ...form.sites, workforceUrl: e.target.value })}
              />
            </div>
          </div>
        </div>
      </div>

      {message && (
        <div className={`banner ${message.tone === "ok" ? "ok" : "bad"}`}>
          <div>{message.text}</div>
        </div>
      )}

      <div className="row">
        <button className="btn primary" type="button" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save integrations"}
        </button>
        <span className="small muted">Secrets are written server-side only.</span>
      </div>
    </div>
  );
}
