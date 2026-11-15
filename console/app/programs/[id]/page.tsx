import Link from "next/link";
import { notFound } from "next/navigation";
import { getDb } from "@/lib/store";
import { money } from "@/lib/format";
import { candidatesFor } from "@/lib/eligibility";
import { Badge, Card, Crumbs, Progress, Topbar } from "@/components/ui";
import { ProgramEditor } from "@/components/ProgramEditor";

export const dynamic = "force-dynamic";

export default async function ProgramPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const program = db.programs.find((p) => p.id === id);
  if (!program) notFound();

  const candidates = candidatesFor(db, "degree", program.id);

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Degrees & programs", href: "/programs" }, { label: program.name }]} />
        <div className="row">
          <Link className="btn small" href={`/credentials?program=${program.id}`}>
            Confer degrees
          </Link>
          <Link className="btn small ghost" href="/programs">
            All programs
          </Link>
        </div>
      </Topbar>

      <div className="content">
        <div className="hero">
          <div className="between" style={{ alignItems: "flex-start" }}>
            <div>
              <div className="eyebrow">{program.department}</div>
              <h1 className="page-title" style={{ fontSize: 26 }}>{program.credential}</h1>
              <p className="page-sub">{program.summary}</p>
            </div>
            <Badge status={program.status} />
          </div>
          <div className="hero-meta">
            <span className="chip plain">{program.totalCredits} credits</span>
            <span className="chip plain">{program.semesters.length} semesters</span>
            <span className="chip plain">{money(program.totalCredits * program.tuitionPerCreditCents)} tuition</span>
            <span className="chip plain">{money(program.tuitionPerCreditCents)} / credit</span>
            <span className="chip plain">Signara: {program.signaraTemplate}</span>
          </div>
        </div>

        <div className="split mt">
          <ProgramEditor program={program} programsUrl="/programs" />
          <div className="stack">
            <Card title="Conferral queue" subtitle="Learners on this plan and their earned credit.">
              <div className="card-body stack-sm">
                {candidates.length === 0 && <p className="small muted">No learners are enrolled on this program yet.</p>}
                {candidates.map((candidate) => (
                  <div key={candidate.learner.id}>
                    <div className="between">
                      <div>
                        <div className="strong small">{candidate.learner.name}</div>
                        <div className="tiny muted">
                          {"creditsEarned" in candidate.eligibility
                            ? `${candidate.eligibility.creditsEarned} / ${candidate.eligibility.creditsRequired} credits · GPA ${candidate.eligibility.gpa}`
                            : ""}
                        </div>
                      </div>
                      {candidate.ready ? (
                        <Link className="btn small primary" href={`/credentials?program=${program.id}`}>
                          Confer
                        </Link>
                      ) : (
                        <span className="chip warn">In progress</span>
                      )}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <Progress
                        value={
                          "creditsEarned" in candidate.eligibility
                            ? Math.min(100, (candidate.eligibility.creditsEarned / program.totalCredits) * 100)
                            : 0
                        }
                      />
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Conferral requirements">
              <div className="card-body stack-sm small">
                <p className="muted">
                  A degree is conferred when every credit on the plan is earned and the record is clear. The
                  console then renders the conferral certificate, submits it to Signara, and issues the signed
                  document to the learner record.
                </p>
                <div className="between">
                  <span className="muted">Credential template</span>
                  <span className="mono">{program.signaraTemplate}</span>
                </div>
                <div className="between">
                  <span className="muted">Fees</span>
                  <span>{money(db.settings.graduationFeeCents)} graduation</span>
                </div>
                <div className="between">
                  <span className="muted">Accreditation</span>
                  <span>{program.accreditation}</span>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
