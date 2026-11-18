import Link from "next/link";
import { ApplicationsQueue, type ApplicationRow } from "@/components/ApplicationsQueue";
import { Card, Crumbs, PageHead, Topbar } from "@/components/ui";
import { OPEN_STATUSES } from "@/lib/applications";
import { currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { can } from "@/lib/staff-policy";
import { getDb } from "@/lib/store";
import { termLabel } from "@/lib/term";

export const dynamic = "force-dynamic";

/**
 * Admissions, out of the inbox.
 *
 * Every application the public form writes is here with the program, the term,
 * the goals statement and a link to the transcript. A registrar sets a status and
 * a note, and the record keeps who decided and when.
 */
export default async function AdmissionsPage() {
  const db = getDb();
  const me = await currentStaff();
  const allowed = !authEnabled() || can(me?.role, "staff");

  const applications = db.applications ?? [];
  const open = applications.filter((entry) => OPEN_STATUSES.includes(entry.status));

  const rows: ApplicationRow[] = applications.map((entry) => ({
    id: entry.id,
    name: entry.name,
    email: entry.email,
    phone: entry.phone,
    programName: entry.programName,
    termLabel: termLabel(entry.term),
    goals: entry.goals,
    status: entry.status,
    statusLabel:
      entry.status === "received"
        ? "Received"
        : entry.status === "reviewing"
          ? "Under review"
          : entry.status === "accepted"
            ? "Accepted"
            : entry.status === "waitlisted"
              ? "Waitlisted"
              : "Declined",
    note: entry.note,
    createdAt: entry.createdAt,
    transcript: entry.transcript ? { fileName: entry.transcript.fileName, bytes: entry.transcript.bytes } : null,
  }));

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Admissions" }]} />
        <div className="row">
          <a className="btn small ghost" href="/apply" target="_blank" rel="noreferrer">
            Open the public form
          </a>
          <span className="chip muted">{open.length} to answer</span>
          <span className="chip muted">{applications.length} total</span>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Admissions"
          title="Applications"
          subtitle="Every application submitted through the public form: the program and term the applicant chose, their goals statement, and the transcript they uploaded. Accept, waitlist or decline, and say why — the record keeps who decided and when."
        />

        {!allowed ? (
          <Card title="Registrar only">
            <div className="card-body stack-sm">
              <p className="small muted" style={{ margin: 0 }}>
                Your account can publish courses but cannot decide admissions. Ask a registrar if you need
                access changed.
              </p>
              <Link className="btn small" href="/">
                Back to the dashboard
              </Link>
            </div>
          </Card>
        ) : (
          <Card
            title="Application records"
            subtitle="Newest first. A decision is saved on the record, not sent to the applicant — email them from admissions."
          >
            <div className="card-body">
              <ApplicationsQueue applications={rows} />
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
