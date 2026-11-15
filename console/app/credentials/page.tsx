import Link from "next/link";
import { getDb } from "@/lib/store";
import { shortDate } from "@/lib/format";
import { Badge, Card, Empty, PageHead, Stat, Topbar, Crumbs } from "@/components/ui";
import { IssueCredentialForm } from "@/components/IssueCredentialForm";

export const dynamic = "force-dynamic";

export default async function CredentialsPage({
  searchParams,
}: {
  searchParams: Promise<{ learner?: string; program?: string; course?: string; status?: string }>;
}) {
  const params = await searchParams;
  const db = getDb();
  const status = params.status ?? "";

  const credentials = db.credentials
    .filter((credential) => (status ? credential.status === status : true))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const issued = db.credentials.filter((c) => ["issued", "signed"].includes(c.status)).length;
  const pending = db.credentials.filter((c) => ["queued_local", "partial", "failed", "draft"].includes(c.status)).length;

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Credentials" }]} />
        <div className="row">
          <Link className="btn small ghost" href="/verify">
            Verify a credential
          </Link>
          <span className={`chip ${db.settings.signara.apiKey ? "ok" : "warn"}`}>
            {db.settings.signara.apiKey ? "Signara connected" : "Signara not configured"}
          </span>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Award & conferral"
          title="Credential center"
          subtitle="Course certificates, workforce track credentials and degree conferrals — rendered, submitted to Signara for signing, and issued to the learner record."
        />

        <div className="stat-grid">
          <Stat label="Issued" value={issued} hint="Signed and on the learner record" />
          <Stat label="Awaiting Signara" value={pending} hint="Held locally or partially submitted" />
          <Stat label="Revoked" value={db.credentials.filter((c) => c.status === "revoked").length} hint="Verification shows the revocation" />
          <Stat label="Learners" value={db.learners.length} hint={`${db.completions.filter((c) => c.status === "pass").length} passing completions`} />
        </div>

        <div className="split mt">
          <Card
            title="Awards"
            subtitle="Newest first. Every award carries its evidence hash and Signara identifiers."
            action={
              <form method="get" className="row" style={{ gap: 6 }}>
                <select className="select" name="status" defaultValue={status} aria-label="Filter status">
                  <option value="">All</option>
                  {["issued", "partial", "queued_local", "failed", "revoked"].map((value) => (
                    <option key={value} value={value}>
                      {value.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
                <button className="btn small" type="submit">
                  Filter
                </button>
              </form>
            }
          >
            {credentials.length === 0 ? (
              <Empty
                title="No awards yet"
                body="Issue the first one on the right — pick the course, track or degree, then the learner."
              />
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Credential</th>
                      <th>Learner</th>
                      <th>Status</th>
                      <th>Signara</th>
                      <th>Date</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {credentials.map((credential) => (
                      <tr key={credential.id}>
                        <td>
                          <Link href={`/credentials/${credential.id}`} className="strong">
                            {credential.subjectLabel}
                          </Link>
                          <div className="tiny muted">{credential.type.replace(/_/g, " ")}</div>
                        </td>
                        <td>
                          <div className="small">{credential.learner.name}</div>
                          <div className="tiny muted">{credential.learner.email}</div>
                        </td>
                        <td>
                          <Badge status={credential.status} />
                        </td>
                        <td className="small mono muted">
                          {credential.signara.requestId
                            ? credential.signara.requestId.slice(0, 12)
                            : credential.signara.lastError
                              ? "error"
                              : "—"}
                        </td>
                        <td className="small muted nowrap">{shortDate(credential.createdAt)}</td>
                        <td className="actions">
                          <Link className="btn small" href={`/credentials/${credential.id}`}>
                            Open
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <IssueCredentialForm
            learners={db.learners.map((learner) => ({
              id: learner.id,
              name: learner.name,
              email: learner.email,
            }))}
            courses={db.courses
              .filter((course) => course.status === "published")
              .map((course) => ({
                key: course.key,
                label: `${course.code} — ${course.title.replace(`${course.code} — `, "")}`,
              }))}
            tracks={db.tracks.map((track) => ({ id: track.id, label: track.title }))}
            programs={db.programs.map((program) => ({ id: program.id, label: program.credential }))}
            defaults={{
              learner: params.learner ?? "",
              program: params.program ?? "",
              course: params.course ?? "",
            }}
            autoSign={db.settings.signara.autoSign}
          />
        </div>
      </div>
    </>
  );
}
