import Link from "next/link";
import { getDb } from "@/lib/store";
import { money } from "@/lib/format";
import { candidatesFor } from "@/lib/eligibility";
import { Badge, Card, PageHead, Progress, Stat, Topbar, Crumbs } from "@/components/ui";

export const dynamic = "force-dynamic";

export default function ProgramsPage() {
  const db = getDb();
  const totalCredits = db.programs.reduce((n, p) => n + p.totalCredits, 0);

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Degrees & programs" }]} />
        <Link className="btn small" href="/credentials">
          Conferral queue
        </Link>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="School"
          title="Degrees & programs"
          subtitle="The published plans behind atheniq.institute: semesters, credits, tuition and the credential each program confers."
        />

        <div className="stat-grid">
          <Stat label="Programs" value={db.programs.length} hint={`${db.programs.filter((p) => p.status === "active").length} active`} />
          <Stat label="Catalog credits" value={totalCredits} hint="Across all published plans" />
          <Stat label="Per credit" value={money(db.settings.tuitionPerCreditCents)} hint="One rate for every program" />
          <Stat
            label="Conferral candidates"
            value={db.programs.reduce((n, p) => n + candidatesFor(db, "degree", p.id).filter((c) => c.ready).length, 0)}
            hint="Learners with every credit"
          />
        </div>

        <div className="grid grid-3 mt">
          {db.programs.map((program) => {
            const candidates = candidatesFor(db, "degree", program.id);
            const ready = candidates.filter((c) => c.ready).length;
            const scheduled = program.semesters.reduce((n, s) => n + s.credits, 0);
            return (
              <Card
                key={program.id}
                title={program.credential}
                subtitle={`${program.name} · ${program.credentialType}`}
                action={<Badge status={program.status} />}
              >
                <div className="card-body stack-sm">
                  <p className="small muted">{program.summary}</p>
                  <div className="between small">
                    <span className="muted">Credits</span>
                    <span>{program.totalCredits}</span>
                  </div>
                  <div className="between small">
                    <span className="muted">Semesters</span>
                    <span>
                      {program.semesters.length} · {scheduled} credits scheduled
                    </span>
                  </div>
                  <div className="between small">
                    <span className="muted">Tuition</span>
                    <span>{money(program.totalCredits * program.tuitionPerCreditCents)}</span>
                  </div>
                  <div>
                    <div className="between small" style={{ marginBottom: 5 }}>
                      <span className="muted">Conferral readiness</span>
                      <span>
                        {ready} / {candidates.length}
                      </span>
                    </div>
                    <Progress value={candidates.length ? (ready / candidates.length) * 100 : 0} />
                  </div>
                </div>
                <div className="card-foot">
                  <div className="between">
                    <Link href={`/programs/${program.id}`} className="small">
                      Open plan →
                    </Link>
                    <Link href={`/credentials?program=${program.id}`} className="small">
                      Confer →
                    </Link>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>

        <Card title="Institution" className="mt">
          <div className="card-body grid grid-3">
            <div>
              <div className="label">Legal / published name</div>
              <div className="small">{db.settings.org}</div>
              <div className="tiny muted">A program of Innotel Labs</div>
            </div>
            <div>
              <div className="label">Fees</div>
              <div className="small">
                Application {money(db.settings.applicationFeeCents)} · Graduation {money(db.settings.graduationFeeCents)}
              </div>
              <div className="tiny muted">Waivers applied per cohort</div>
            </div>
            <div>
              <div className="label">Sites</div>
              <div className="small stack-sm">
                <a href={db.settings.sites.instituteUrl} target="_blank" rel="noreferrer">
                  {db.settings.sites.instituteUrl}
                </a>
                <a href={db.settings.sites.coursesUrl} target="_blank" rel="noreferrer">
                  {db.settings.sites.coursesUrl}
                </a>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
