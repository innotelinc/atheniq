import Link from "next/link";
import { getDb } from "@/lib/store";
import { money, shortDate, humanStatus, daysAgo } from "@/lib/format";
import { candidatesFor } from "@/lib/eligibility";
import { expiryWindow } from "@/lib/health";
import { Badge, Banner, Card, Empty, PageHead, Progress, Stat, Topbar, Crumbs } from "@/components/ui";

export const dynamic = "force-dynamic";

export default function DashboardPage() {
  const db = getDb();
  const settings = db.settings;

  const published = db.courses.filter((c) => c.status === "published");
  const inFlight = db.courses.filter((c) => c.status === "draft" || c.status === "in_review");
  const issued = db.credentials.filter((c) => c.status === "issued" || c.status === "signed");
  const needsSigning = db.credentials.filter((c) =>
    ["queued_local", "partial", "failed", "draft"].includes(c.status),
  );

  const configured = {
    signara: Boolean(settings.signara.apiKey),
    ai: Boolean(settings.ai.apiKey),
    lmsImport: Boolean(settings.lms.importUrl),
  };
  const readyCount = [configured.signara, configured.ai, configured.lmsImport].filter(Boolean).length;
  const keyWindow = expiryWindow(settings.signara.keyExpiresAt);

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Dashboard" }]} />
        <div className="row">
          <Link className="btn small ghost" href="/website">
            Website
          </Link>
          <Link className="btn small" href="/generate">
            Generate a course
          </Link>
          <Link className="btn primary small" href="/courses/new">
            New course
          </Link>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow={`${settings.org} · ${settings.defaultTerm}`}
          title="School at a glance"
          subtitle="Every course in the catalog, every program plan, and every credential signed through Signara — in one place."
        />

        {(keyWindow.level === "warn" || keyWindow.level === "bad") && (
          <Banner tone={keyWindow.level === "bad" ? "bad" : "warn"} title={`Signara key — ${keyWindow.label}`}>
            {keyWindow.detail} <Link href="/health">Open health</Link>
          </Banner>
        )}

        <div className="stat-grid">
          <Stat
            label="Catalog"
            value={published.length}
            unit="courses"
            hint={`${db.courses.length} total · ${inFlight.length} not yet live`}
          />
          <Stat
            label="Degree programs"
            value={db.programs.filter((p) => p.status === "active").length}
            unit="active"
            hint={`${db.programs.reduce((n, p) => n + p.semesters.length, 0)} published semesters`}
          />
          <Stat
            label="Workforce tracks"
            value={db.tracks.filter((t) => t.status === "active").length}
            unit="ladders"
            hint={`${db.tracks.reduce((n, t) => n + t.courses.length, 0)} course links`}
          />
          <Stat
            label="Credentials"
            value={issued.length}
            unit="issued"
            hint={needsSigning.length ? `${needsSigning.length} awaiting Signara` : "All awards signed"}
          />
        </div>

        <div className="split mt">
          <div className="stack">
            <Card
              title="Publishing pipeline"
              subtitle="What the console can do with what is configured right now."
              action={
                <Link className="btn small ghost" href="/integrations">
                  Configure
                </Link>
              }
            >
              <div className="card-body stack">
                <PipelineRow
                  label="Course engine (atheniq.courses)"
                  detail={settings.lms.baseUrl}
                  ok={Boolean(settings.lms.baseUrl)}
                  note={
                    configured.lmsImport
                      ? "Import endpoint configured — publishing pushes the OLX archive."
                      : "No import endpoint: publishing builds the OLX archive and catalog patches for the repo pipeline."
                  }
                />
                <PipelineRow
                  label="Signara signing"
                  detail={settings.signara.baseUrl}
                  ok={configured.signara}
                  note={
                    configured.signara
                      ? `Awards are uploaded, requested and signed as ${settings.signer.name}.`
                      : "No API key: awards are staged locally and stay queued until a key is set."
                  }
                />
                <PipelineRow
                  label="Model gateway"
                  detail={`${settings.ai.baseUrl} · ${settings.ai.model}`}
                  ok={configured.ai}
                  note={
                    configured.ai
                      ? "Course studio generates with the gateway, falling back to the rules engine on error."
                      : "No key: the studio uses the deterministic curriculum engine."
                  }
                />
                <div className="between small muted">
                  <span>
                    {readyCount} of 3 integrations configured · tuition {money(settings.tuitionPerCreditCents)} per credit
                  </span>
                  <Link href="/integrations">Open integration settings →</Link>
                </div>
              </div>
            </Card>

            <Card
              title="Needs a decision"
              subtitle="Drafts finished but not published, and awards waiting on signing."
              action={
                <Link className="btn small ghost" href="/courses?status=in_review">
                  View all
                </Link>
              }
            >
              {inFlight.length === 0 && needsSigning.length === 0 ? (
                <Empty
                  title="Nothing is waiting"
                  body="Every course is published and every award is signed. Start a new course from an idea in the course studio."
                  action={
                    <Link className="btn" href="/generate">
                      Open course studio
                    </Link>
                  }
                />
              ) : (
                <div className="card-body stack-sm">
                  {inFlight.slice(0, 4).map((course) => (
                    <div className="between" key={course.id}>
                      <div>
                        <Link href={`/courses/${course.id}`} className="strong">
                          {course.code} — {course.title.replace(`${course.code} — `, "")}
                        </Link>
                        <div className="small muted">
                          {course.credits} credits · {course.modules.length} modules · updated {daysAgo(course.updatedAt)}
                        </div>
                      </div>
                      <div className="row">
                        <Badge status={course.status} />
                        <Link className="btn small" href={`/courses/${course.id}`}>
                          Finish
                        </Link>
                      </div>
                    </div>
                  ))}
                  {needsSigning.slice(0, 3).map((credential) => (
                    <div className="between" key={credential.id}>
                      <div>
                        <Link href={`/credentials/${credential.id}`} className="strong">
                          {credential.subjectLabel}
                        </Link>
                        <div className="small muted">
                          {credential.learner.name} · {humanStatus(credential.status)}
                          {credential.signara.lastError ? ` · ${credential.signara.lastError.slice(0, 60)}` : ""}
                        </div>
                      </div>
                      <Badge status={credential.status} />
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card
              title="Programs"
              subtitle="Published plans, credits and the tuition each one bills."
              action={
                <Link className="btn small ghost" href="/programs">
                  Manage
                </Link>
              }
            >
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Program</th>
                      <th className="num">Credits</th>
                      <th className="num">Tuition</th>
                      <th>Conferral candidates</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {db.programs.map((program) => {
                      const candidates = candidatesFor(db, "degree", program.id);
                      const ready = candidates.filter((c) => c.ready).length;
                      return (
                        <tr key={program.id}>
                          <td>
                            <Link href={`/programs/${program.id}`} className="strong">
                              {program.credential}
                            </Link>
                            <div className="small muted">{program.name} · {program.semesters.length} semesters</div>
                          </td>
                          <td className="num">{program.totalCredits}</td>
                          <td className="num">{money(program.totalCredits * program.tuitionPerCreditCents)}</td>
                          <td>
                            <span className="small">
                              {ready} of {candidates.length} ready
                            </span>
                            <div style={{ marginTop: 6 }}>
                              <Progress value={candidates.length ? (ready / candidates.length) * 100 : 0} />
                            </div>
                          </td>
                          <td className="actions">
                            <Badge status={program.status} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <div className="stack">
            <Card title="Recent activity">
              <div className="card-body stack-sm">
                {db.activity.slice(0, 8).map((item) => (
                  <div key={item.id} className="between" style={{ alignItems: "flex-start" }}>
                    <div>
                      <div className="small">{item.message}</div>
                      {item.actor && (
                        <div className="tiny muted">
                          by {item.actor.name} · {item.actor.role}
                        </div>
                      )}
                    </div>
                    <span className="tiny muted nowrap">{shortDate(item.at)}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Award from a completion" subtitle="Learners whose evidence is already in the LMS.">
              <div className="card-body stack-sm">
                {db.learners.slice(0, 4).map((learner) => {
                  const completions = db.completions.filter((c) => c.learnerId === learner.id && c.status === "pass");
                  return (
                    <div key={learner.id} className="between">
                      <div>
                        <div className="strong">{learner.name}</div>
                        <div className="small muted">{completions.length} completions</div>
                      </div>
                      <Link className="btn small ghost" href={`/credentials?learner=${learner.id}`}>
                        Award
                      </Link>
                    </div>
                  );
                })}
                <Link className="btn small block" href="/credentials">
                  Open credential center
                </Link>
              </div>
            </Card>

            <Card title="Course studio" accent>
              <div className="card-body stack-sm">
                <p className="small muted">
                  Describe a course you want to exist. The studio drafts the outcomes, modules, lessons and
                  assessment mix — then you refine it by instruction until it is right, and accept it into the
                  catalog.
                </p>
                <Link className="btn primary block" href="/generate">
                  Generate from an idea
                </Link>
                <span className="tiny muted">Signed-in staff only · every revision is versioned</span>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}

function PipelineRow({
  label,
  detail,
  ok,
  note,
}: {
  label: string;
  detail: string;
  ok: boolean;
  note: string;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10, alignItems: "start" }}>
      <div>
        <div className="strong small">{label}</div>
        <div className="tiny mono muted">{detail}</div>
        <div className="tiny muted" style={{ marginTop: 3 }}>{note}</div>
      </div>
      <span className={`chip ${ok ? "ok" : "warn"}`}>{ok ? "Configured" : "Not configured"}</span>
    </div>
  );
}
