import { getDb } from "@/lib/store";
import { brandOf, publicSiteOrigin } from "@/lib/branding";
import { ADMISSIONS_EMAIL } from "@/lib/legal";
import { Card, Crumbs, PageHead, Topbar } from "@/components/ui";
import { WebsiteForm } from "@/components/WebsiteForm";

export const dynamic = "force-dynamic";

/**
 * The institute's website is atheniq.institute — `web/landing/` in this
 * repository, served from a git checkout behind the edge's NPM proxy host 206.
 * The console does not publish a second copy of it and has no storefront of its
 * own: this page is where the school's name, domain and admissions address are
 * set, and where the one website is described. Students never come through the
 * console — their accounts are created at atheniq.courses/register.
 */
export default async function WebsitePage() {
  const db = getDb();
  const brand = brandOf(db.settings);
  const site = publicSiteOrigin();
  const registerUrl = `${db.settings.lms.baseUrl.replace(/\/+$/, "")}/register`;
  const loginUrl = `${db.settings.lms.baseUrl.replace(/\/+$/, "")}/login`;

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Website" }]} />
        <div className="row">
          <a className="btn small ghost" href={`${site}/`} target="_blank" rel="noreferrer">
            Open {brand.domain}
          </a>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Public website"
          title={brand.domain}
          subtitle="One website, served from this repository: web/landing behind the edge, published by a git checkout rather than by this console. Set what the school is called, the domain it answers on and where admissions is written — there is no second site to keep in step, and no student route through the registrar."
        />

        <WebsiteForm settings={db.settings} />

        <div className="split mt">
          <Card title="Where it is served" subtitle="One site, one copy, one update command.">
            <div className="card-body stack-sm small">
              <Row label="Origin" value="the landing service, from a git checkout" />
              <Row label="Published by" value="deploy/update-landing.sh" />
              <Row label="Edge" value="NPM proxy host 206" />
              <Row label="Domain" value={brand.domain} />
              <span className="tiny muted">
                A change to the site is a commit and that one command — the files on the host are the files a
                visitor gets. Settings saved here change the school's name, address and domain everywhere this
                console points, not the page copy.
              </span>
            </div>
          </Card>

          <Card title="Students and applicants" subtitle="They never come through the registrar console.">
            <div className="card-body stack-sm small">
              <Row label="Create an account" value={registerUrl} />
              <Row label="Sign in" value={loginUrl} />
              <Row label="Admissions" value={ADMISSIONS_EMAIL} />
              <Row label="Check a credential" value="the public /verify page" />
              <span className="tiny muted">
                A learner's account, enrolment and classroom live in the course engine. The console is staff-only:
                sign-in here is for registrars and publishers, and every page behind it needs that session.
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
      <span className="mono tiny">{value}</span>
    </div>
  );
}
