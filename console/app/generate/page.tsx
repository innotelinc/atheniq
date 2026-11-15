import Link from "next/link";
import { getDb } from "@/lib/store";
import { daysAgo, humanStatus } from "@/lib/format";
import { Badge, Card, Empty, PageHead, Topbar, Crumbs } from "@/components/ui";
import { NewIdeaForm } from "@/components/NewIdeaForm";

export const dynamic = "force-dynamic";

export default function GeneratePage() {
  const db = getDb();
  const configured = Boolean(db.settings.ai.apiKey);

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Course studio" }]} />
        <span className={`chip ${configured ? "ok" : "warn"}`}>
          {configured ? `Model: ${db.settings.ai.model}` : "Rules engine"}
        </span>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Generative authoring"
          title="Course studio"
          subtitle="Start with the idea. The studio drafts outcomes, modules, lessons and assessment, and then you steer it — revision by revision — until the course is right."
        />

        <div className="split">
          <Card
            title="Start from an idea"
            subtitle="A sentence is enough. Be specific about the work the learner does."
            accent
          >
            <div className="card-body">
              <NewIdeaForm
                configured={configured}
                departments={[
                  "Applied AI",
                  "Business",
                  "Criminal Justice",
                  "Nursing",
                  "Data",
                  "Information Technology",
                  "Teaching & Learning",
                  "Health Administration",
                  "General Studies",
                ]}
                defaultTerm={db.settings.defaultTerm}
              />
            </div>
          </Card>

          <div className="stack">
            <Card title="How the loop works">
              <div className="card-body stack-sm small">
                <Step n="1" title="Describe the course">
                  One sentence. Who is it for, what should they be able to do, and what is the constraint?
                </Step>
                <Step n="2" title="Read the draft">
                  Outcomes, modules, lessons by type and length, and the assessment mix — all editable later.
                </Step>
                <Step n="3" title="Steer it">
                  “Make it more practical”, “add a compliance module”, “3 credits”, “for front-desk staff”,
                  “rigorous, with seminars”. Each instruction produces a new version.
                </Step>
                <Step n="4" title="Accept and publish">
                  Accepting puts it in the catalog with the next free course code. Leave “publish immediately”
                  ticked and it runs the publish checks and goes live in the same step.
                </Step>
              </div>
            </Card>

            <Card title="Recent sessions">
              {db.sessions.length === 0 ? (
                <Empty title="No sessions yet" body="Your first draft appears here once you start one." />
              ) : (
                <div className="table-wrap">
                  <table className="data">
                    <tbody>
                      {db.sessions.slice(0, 8).map((session) => (
                        <tr key={session.id}>
                          <td>
                            <Link href={`/generate/${session.id}`} className="strong">
                              {session.draft?.title ?? session.idea.slice(0, 50)}
                            </Link>
                            <div className="small muted">
                              {session.messages.length} messages · {session.versions.length} versions ·{" "}
                              {daysAgo(session.updatedAt)}
                            </div>
                          </td>
                          <td className="actions">
                            {session.courseId ? (
                              <Badge status="published" label="Accepted" />
                            ) : (
                              <span className="chip plain muted">{humanStatus(session.engine)}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}

function Step({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <div className="row" style={{ alignItems: "flex-start", gap: 10 }}>
      <span className="module-num">{n}</span>
      <div>
        <div className="strong">{title}</div>
        <div className="muted">{children}</div>
      </div>
    </div>
  );
}
