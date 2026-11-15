import Link from "next/link";
import { notFound } from "next/navigation";
import { currentSessionId, currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { liveSessions } from "@/lib/login-sessions";
import { getDb } from "@/lib/store";
import { can, ROLE_LABELS } from "@/lib/staff-policy";
import { dateTime, shortDate, timeLeft } from "@/lib/format";
import { Card, Crumbs, Empty, PageHead, Stat, Topbar } from "@/components/ui";
import { StaffSessions } from "@/components/StaffSessions";
import { confirmationRemaining, recentlyConfirmed } from "@/lib/step-up";

export const dynamic = "force-dynamic";

const KIND_LABELS: Record<string, string> = {
  "course.published": "Published a course",
  "course.created": "Added a course",
  "course.updated": "Edited a course",
  "credential.issued": "Awarded a credential",
  "credential.signed": "Signed a credential",
  "credential.revoked": "Revoked a credential",
  "session.created": "Started a draft",
  "session.revised": "Revised a draft",
  "program.updated": "Changed a program",
  "settings.updated": "Changed settings",
};

export default async function StaffDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const member = db.staff.find((record) => record.id === id);
  if (!member) notFound();

  const me = await currentStaff();
  const allowed = !authEnabled() || can(me?.role, "staff");
  const confirmed = me ? await recentlyConfirmed(me.id) : false;
  const confirmationLeft = me ? await confirmationRemaining(me.id) : 0;
  const confirmationLabel =
    confirmationLeft > 0
      ? `${Math.floor(confirmationLeft / 60)}m ${String(confirmationLeft % 60).padStart(2, "0")}s`
      : "";

  if (!allowed) {
    return (
      <>
        <Topbar>
          <Crumbs items={[{ label: "Staff", href: "/staff" }, { label: member.name }]} />
        </Topbar>
        <div className="content">
          <Card title="Registrar only">
            <div className="card-body small muted">
              Account history is visible to registrars. Ask one if you need this exported.
            </div>
          </Card>
        </div>
      </>
    );
  }

  const actions = db.activity.filter((item) => item.actor?.id === member.id);
  const published = actions.filter((item) => item.kind === "course.published");
  const awards = actions.filter((item) => ["credential.issued", "credential.signed"].includes(item.kind));
  const revisions = actions.filter((item) => item.kind === "session.revised");

  const sessionId = await currentSessionId();
  const sessions = liveSessions(db)
    .filter((entry) => entry.staffId === member.id)
    .map((entry) => ({
      id: entry.id,
      source: entry.source,
      createdAt: dateTime(entry.createdAt),
      expiresAt: dateTime(entry.expiresAt),
      remaining: timeLeft(entry.expiresAt),
      newSource: Boolean(entry.newSource),
      current: entry.id === sessionId,
    }));

  const courseByKey = new Map(db.courses.map((course) => [course.key, course.id]));
  const credentialIds = new Set(db.credentials.map((credential) => credential.id));
  const hrefFor = (ref: string) => {
    if (courseByKey.has(ref)) return `/courses/${courseByKey.get(ref)}`;
    if (credentialIds.has(ref)) return `/credentials/${ref}`;
    return null;
  };

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Staff", href: "/staff" }, { label: member.name }]} />
        <div className="row">
          {confirmationLeft > 0 && (
            <span className="chip ok" title="Destructive actions will not ask for a code or passkey until this runs out.">
              {confirmationLabel} left on your confirmation
            </span>
          )}
          <span className={`chip ${member.role === "registrar" ? "ok" : "muted"}`}>{ROLE_LABELS[member.role]}</span>
          {member.disabled && <span className="chip bad">disabled</span>}
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Access & attribution"
          title={member.name}
          subtitle={`${member.title} · ${member.email} · added ${shortDate(member.createdAt)} · last sign-in ${
            member.lastLoginAt ? shortDate(member.lastLoginAt) : "never"
          }`}
        />

        <div className="stat-grid">
          <Stat label="Courses published" value={published.length} hint="Attributed to this account" />
          <Stat label="Credentials awarded" value={awards.length} hint="Staged or signed" />
          <Stat label="Drafts revised" value={revisions.length} hint="Studio instructions applied" />
          <Stat label="Recorded actions" value={actions.length} hint="Everything on the trail" />
        </div>

        <Card
          title="Live sessions"
          subtitle={`Sign-ins that can still reach the console for ${member.name}, with where each came from and how long it has left. Ending them takes effect at once; the next sign-in needs their second factor.`}
          className="mt"
        >
          <div className="card-body stack-sm">
            <StaffSessions
              staffId={member.id}
              name={member.name}
              entries={sessions}
              stepUp={Boolean(me?.totp?.enabled || (me?.passkeys?.length ?? 0) > 0)}
              confirmed={confirmed}
              passkeyCount={me?.passkeys?.length ?? 0}
              self={member.id === me?.id}
            />
          </div>
        </Card>

        <div className="mt">
          <Card
            title="Audit trail"
            subtitle="Newest first. The trail is written when the action happens, so it survives later edits."
            action={
              <div className="row">
                <a className="btn small ghost" href={`/api/audit/export?staffId=${member.id}`}>
                  Export CSV
                </a>
                <Link className="btn small ghost" href="/staff">
                  All staff
                </Link>
              </div>
            }
          >
            {actions.length === 0 ? (
              <Empty
                title="No recorded actions yet"
                body="This account has signed in but has not published, awarded or changed anything since the trail started recording names."
              />
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Detail</th>
                      <th>When</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {actions.map((item) => {
                      const href = hrefFor(item.ref);
                      return (
                        <tr key={item.id}>
                          <td className="small strong nowrap">{KIND_LABELS[item.kind] ?? item.kind}</td>
                          <td className="small">{item.message}</td>
                          <td className="small muted nowrap">{dateTime(item.at)}</td>
                          <td className="actions">
                            {href && (
                              <Link className="btn small ghost" href={href}>
                                Open
                              </Link>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
