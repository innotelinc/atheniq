import { NextResponse, type NextRequest } from "next/server";
import { getDb } from "@/lib/store";
import { brandOf } from "@/lib/branding";
import { integrationHealth } from "@/lib/health";
import { Card, Crumbs, PageHead, Topbar } from "@/components/ui";
import { WebsiteForm } from "@/components/WebsiteForm";

export const dynamic = "force-dynamic";

/**
 * The public website atheniq.institute serves is generated from this console:
 * published courses, active programs and the signed credential register. This
 * page owns the brand the site wears (white-label) and whether it is live.
 */
export default async function WebsitePage() {
  const db = getDb();
  const brand = brandOf(db.settings);
  const health = await integrationHealth(db.settings);
  const published = db.courses.filter((course) => course.status === "published");

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Website" }]} />
        <div className="row">
          <span className={`chip ${db.settings.site.published ? "ok" : "warn"}`}>
            {db.settings.site.published ? "Public site live" : "Public site offline"}
          </span>
          <a className="btn small ghost" href={`https://${brand.domain}/`} target="_blank" rel="noreferrer">
            {brand.domain}
          </a>
          <a className="btn small ghost" href="/site" target="_blank" rel="noreferrer">
            Preview as edited
          </a>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Front-facing website"
          title="atheniq.institute"
          subtitle={`Derived from the platform, not maintained twice: ${published.length} published courses, ${
            db.programs.filter((program) => program.status === "active").length
          } active programs and every signed credential appear automatically. Brand it once here, then re-skin it per client — the same console becomes their school. Staff only: the site itself is public, and admissions and student accounts are handled there, not in this console.`}
        />

        <WebsiteForm settings={db.settings} />

        <div className="split mt">
          <Card title="How the domain is served" subtitle={`${brand.domain} is answered by this same app.`}>
            <div className="card-body stack-sm small">
              <p className="muted" style={{ margin: 0 }}>
                Point the domain at this host, then the console rewrites the public paths for that host and serves
                them without a staff session. The console itself stays on its own hostname.
              </p>
              <div className="between">
                <span className="muted">A record</span>
                <span className="mono tiny">{brand.domain} → the console host</span>
              </div>
              <div className="between">
                <span className="muted">CNAME</span>
                <span className="mono tiny">www.{brand.domain} → {brand.domain}</span>
              </div>
              <div className="between">
                <span className="muted">Hosts it answers</span>
                <span className="mono tiny">PUBLIC_SITE_HOSTS</span>
              </div>
              <span className="tiny muted">
                Add the domain to PUBLIC_SITE_HOSTS in .env and restart. Until DNS resolves, the site is served at
                /site on the console host — that is the preview button above.
              </span>
            </div>
          </Card>

          <Card title="What goes live" subtitle="The site is a projection of the catalog.">
            <div className="card-body stack-sm small">
              <Row label="Published courses" value={`${published.length} listed`} />
              <Row label="Active programs" value={`${db.programs.filter((p) => p.status === "active").length} listed`} />
              <Row
                label="Credential register"
                value={`${db.credentials.filter((c) => ["issued", "signed"].includes(c.status)).length} verifiable`}
              />
              <Row label="Course engine" value={health.checks.find((c) => c.id === "lms")?.ok ? "answering" : "not answering"} />
              <Row label="Prices" value="USD, from each course and program" />
              <span className="tiny muted">
                Archiving a course removes it from the site on the next request. Nothing is copied, so a price
                change here is the price a visitor sees.
              </span>
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="between">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}
