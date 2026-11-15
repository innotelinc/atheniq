import Link from "next/link";
import { currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { getDb } from "@/lib/store";
import { can } from "@/lib/staff-policy";
import { integrationHealth } from "@/lib/health";
import { Card, Crumbs, PageHead, Stat, Topbar } from "@/components/ui";
import { ExpiryForm } from "@/components/ExpiryForm";
import { DigestPanel } from "@/components/DigestPanel";
import { RotateKeyButton } from "@/components/RotateKeyButton";

export const dynamic = "force-dynamic";

export default async function HealthPage() {
  const db = getDb();
  const me = await currentStaff();
  const allowed = !authEnabled() || can(me?.role, "settings");

  if (!allowed) {
    return (
      <>
        <Topbar>
          <Crumbs items={[{ label: "Registrar console" }, { label: "Health" }]} />
        </Topbar>
        <div className="content">
          <Card title="Registrar only">
            <div className="card-body stack-sm">
              <p className="small muted" style={{ margin: 0 }}>
                Integration health is visible to registrars. Ask one if you suspect a pipeline is down.
              </p>
              <Link className="btn small" href="/">
                Back to the dashboard
              </Link>
            </div>
          </Card>
        </div>
      </>
    );
  }

  const health = await integrationHealth(db.settings);
  const tone = health.window.level === "bad" ? "bad" : health.window.level === "warn" ? "warn" : "ok";

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Health" }]} />
        <span className={`chip ${health.healthy ? "ok" : tone === "bad" ? "bad" : "warn"}`}>
          {health.healthy ? "All pipelines answering" : "Needs attention"}
        </span>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Platform"
          title="Integration health"
          subtitle="Live probes of the three systems the console writes to, plus the Signara key's expiry countdown — so a key never lapses in the middle of an award."
        />

        <div className="stat-grid">
          {health.checks.map((check) => (
            <Stat
              key={check.id}
              label={check.label}
              value={check.ok ? "Up" : check.configured ? "Down" : "Not set"}
              hint={check.detail}
            />
          ))}
          <Stat label="Signara key" value={health.window.label} hint={health.window.detail} />
        </div>

        <div className="split mt">
          <Card
            title="Checks run now"
            subtitle="These probes hit the real endpoints every time this page loads."
            action={
              <Link className="btn small ghost" href="/health">
                Re-run
              </Link>
            }
          >
            <div className="card-body stack-sm">
              {health.checks.map((check) => (
                <div className="between" key={check.id} style={{ alignItems: "flex-start" }}>
                  <div>
                    <div className="strong small">{check.label}</div>
                    <div className="tiny muted">{check.detail}</div>
                  </div>
                  <span className={`chip ${check.ok ? "ok" : check.configured ? "bad" : "muted"}`}>
                    {check.ok ? "OK" : check.configured ? "Failing" : "No key"}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <div className="stack">
            <Card title="Signara key" subtitle="When the current key stops working.">
              <div className="card-body stack-sm">
                <div className="between">
                  <span className="small muted">Status</span>
                  <span className={`chip ${tone === "bad" ? "bad" : tone === "warn" ? "warn" : "ok"}`}>
                    {health.window.label}
                  </span>
                </div>
                <div className="between">
                  <span className="small muted">Prefix</span>
                  <span className="small mono">{db.settings.signara.keyPrefix || "—"}</span>
                </div>
                <div className="between">
                  <span className="small muted">Expires</span>
                  <span className="small mono">{db.settings.signara.keyExpiresAt ? db.settings.signara.keyExpiresAt.slice(0, 10) : "—"}</span>
                </div>
                <ExpiryForm value={db.settings.signara.keyExpiresAt ? db.settings.signara.keyExpiresAt.slice(0, 10) : ""} />
                <span className="tiny muted">
                  Signara only shows the key once, at creation. When you paste a new one in Integrations, record its expiry here.
                </span>
              </div>
            </Card>

            <Card title="Rotate the key" subtitle="Mint a replacement and swap it in — verified before it counts.">
              <div className="card-body stack-sm">
                <RotateKeyButton
                  ready={Boolean(process.env.SIGNARA_ADMIN_SECRET)}
                  prefix={db.settings.signara.keyPrefix}
                />
              </div>
            </Card>

            <Card title="What a failing key does">
              <div className="card-body stack-sm small muted">
                <p style={{ margin: 0 }}>
                  Awards still render and are held as <strong>Held locally</strong>; nothing is lost. Set a working key and
                  open the award to retry the signature.
                </p>
                <p style={{ margin: 0 }}>
                  Publishing does not depend on Signara — courses keep going out while signing is repaired.
                </p>
              </div>
            </Card>
          </div>
        </div>

        <div className="mt">
          <Card
            title="Operations digest"
            subtitle="Health, catalog and credential counts by email — and readable here whether or not a relay is set."
          >
            <div className="card-body stack-sm">
              <DigestPanel
                recipients={db.settings.mail.digestTo}
                alertsTo={db.settings.mail.alertsTo ?? ""}
                cadenceDays={db.settings.mail.cadenceDays}
                lastDigestAt={db.settings.mail.lastDigestAt}
                mailConfigured={Boolean(process.env.MAIL_API_KEY && process.env.MAIL_FROM)}
              />
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
