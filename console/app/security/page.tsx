import Link from "next/link";
import { redirect } from "next/navigation";
import { currentSessionId, currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { getDb } from "@/lib/store";
import { can, ROLE_LABELS } from "@/lib/staff-policy";
import { dateTime, humanStatus, shortDate, timeLeft } from "@/lib/format";
import { Card, Crumbs, PageHead, Stat, Topbar } from "@/components/ui";
import { PasskeyManager } from "@/components/PasskeyManager";
import { PasswordForm } from "@/components/PasswordForm";
import { TotpEnroller } from "@/components/TotpEnroller";
import { ClearAuthLog } from "@/components/ClearAuthLog";
import { MailTestButton } from "@/components/MailTestButton";
import { LockoutList } from "@/components/LockoutList";
import { SessionList } from "@/components/SessionList";
import { pausedSignIns } from "@/lib/throttle";
import { liveSessions, SESSIONS_PER_SOURCE } from "@/lib/login-sessions";
import { alertsConfigured, alertRecipients } from "@/lib/alerts";
import { confirmationRemaining, recentlyConfirmed } from "@/lib/step-up";
import { ClearConfirmation } from "@/components/ClearConfirmation";

export const dynamic = "force-dynamic";

const OUTCOME_LABELS: Record<string, string> = {
  success: "Signed in",
  invalid_password: "Wrong password",
  unknown_account: "No such account",
  blocked_domain: "Blocked domain",
  totp_failed: "Wrong two-factor code",
  recovery_used: "Recovery code used",
  passkey_failed: "Passkey rejected",
};

const END_REASON_LABELS: Record<string, string> = {
  signed_out: "Signed out",
  ended_by_registrar: "Ended by a registrar",
  signed_out_everywhere: "Signed out everywhere",
  access_change: "Access change",
  evicted: "Evicted by the session cap",
};

export default async function SecurityPage() {
  const me = await currentStaff();
  if (authEnabled() && !me) redirect("/login?next=%2Fsecurity");

  const db = getDb();
  const registrar = !authEnabled() || can(me?.role, "staff");
  const weekAgo = Date.now() - 7 * 86_400_000;
  const events = db.authLog ?? [];
  const mailReady = alertsConfigured();
  const failures = events.filter((event) => event.outcome !== "success");
  const recentFailures = failures.filter((event) => new Date(event.at).getTime() >= weekAgo);
  const unenrolled = db.staff.filter((member) => !member.totp?.enabled && !member.disabled);
  const pending = (db.accessRequests ?? []).filter((entry) => entry.status === "pending");
  const paused = pausedSignIns();
  const sessionId = await currentSessionId();
  const confirmed = me ? await recentlyConfirmed(me.id) : false;
  const confirmationLeft = me ? await confirmationRemaining(me.id) : 0;
  const confirmationLabel =
    confirmationLeft > 0
      ? `${Math.floor(confirmationLeft / 60)}m ${String(confirmationLeft % 60).padStart(2, "0")}s`
      : "";
  const sessions = liveSessions(db).map((entry) => {
    const member = db.staff.find((person) => person.id === entry.staffId);
    return {
      id: entry.id,
      name: member?.name ?? "Removed account",
      email: member?.email ?? "no longer on staff",
      source: entry.source,
      createdAt: dateTime(entry.createdAt),
      expiresAt: dateTime(entry.expiresAt),
      remaining: timeLeft(entry.expiresAt),
      newSource: Boolean(entry.newSource),
      current: entry.id === sessionId,
    };
  });

  const endedSessions = (db.sessionEnds ?? []).slice(0, 8).map((entry) => {
    const member = db.staff.find((person) => person.id === entry.staffId);
    return {
      id: entry.id,
      name: member?.name ?? "Removed account",
      email: member?.email ?? "no longer on staff",
      source: entry.source,
      startedAt: dateTime(entry.startedAt),
      endedAt: dateTime(entry.endedAt),
      reason: END_REASON_LABELS[entry.reason] ?? humanStatus(entry.reason),
      by: entry.endedBy?.name ?? null,
    };
  });

  const myPasskeys = (me?.passkeys ?? []).map((passkey) => ({
    id: passkey.id,
    label: passkey.label,
    createdAt: passkey.createdAt,
    lastUsedAt: passkey.lastUsedAt,
    algorithm: passkey.algorithm,
  }));

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Security" }]} />
        <span className={`chip ${recentFailures.length ? "warn" : "ok"}`}>
          {recentFailures.length ? `${recentFailures.length} failed sign-in(s) this week` : "No failed sign-ins this week"}
        </span>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Access & attribution"
          title="Sign-in security"
          subtitle="Who can get in, what they need to prove it, and every attempt that was refused."
        />

        <div className="split">
          <Card title="Your sign-in" subtitle={me ? `${me.email} · ${ROLE_LABELS[me.role]}` : "Console access"}>
            <div className="card-body stack-sm">
              <div className="between">
                <span className="small muted">Two-factor</span>
                <span className={`chip ${me?.totp?.enabled ? "ok" : "warn"}`}>
                  {me?.totp?.enabled ? "Authenticator enrolled" : "Not enrolled"}
                </span>
              </div>
              <div className="between">
                <span className="small muted">Passkeys</span>
                <span className="small">{myPasskeys.length}</span>
              </div>
              <div className="between">
                <span className="small muted">Confirmation memory</span>
                {confirmationLeft > 0 ? (
                  <span className="row" style={{ gap: 8 }}>
                    <span className="small">{confirmationLabel} left</span>
                    <ClearConfirmation />
                  </span>
                ) : (
                  <span className="chip muted">Asks each time</span>
                )}
              </div>
                            <span className="tiny muted">
                One code or passkey covers destructive actions for five minutes. Forget ends that early.
              </span>
              {me && <PasswordForm />}
              {me && !me.totp?.enabled && <TotpEnroller />}
              {me ? (
                <PasskeyManager passkeys={myPasskeys} />
              ) : (
                <span className="small muted">
                  Sign-in is switched off on this host (no AUTH_PASSWORD), so there is no personal factor to manage.
                </span>
              )}
            </div>
          </Card>

          <Card title="How access is decided" subtitle="The policy the console enforces on every attempt.">
            <div className="card-body stack-sm small">
              <div className="between">
                <span className="muted">Registered domains</span>
                <span className="mono tiny">{db.settings.auth.allowedDomains.map((d) => `@${d}`).join(" ")}</span>
              </div>
              <div className="between">
                <span className="muted">Two-factor required</span>
                <span>{db.settings.auth.require2fa ? "Yes, every sign-in" : "Optional"}</span>
              </div>
              <div className="between">
                <span className="muted">Passkeys</span>
                <span>Count as a complete sign-in</span>
              </div>
              {registrar && (
                <Link className="btn small ghost" href="/staff">
                  Change the policy
                </Link>
              )}
              <span className="tiny muted">
                A password alone never opens a session while two-factor is required. Failed attempts are recorded below
                without the password.
              </span>
            </div>
          </Card>
        </div>

        {registrar && (
          <>
            <div className="stat-grid mt">
              <Stat label="Accounts" value={db.staff.length} hint={`${unenrolled.length} without two-factor`} />
              <Stat label="Passkeys" value={db.staff.reduce((sum, member) => sum + (member.passkeys?.length ?? 0), 0)} />
              <Stat label="Failed sign-ins" value={recentFailures.length} hint="Last 7 days" />
              <Stat
                label="Pending requests"
                value={pending.length}
                hint={pending.length ? "Waiting for a registrar" : "Queue empty"}
              />
            </div>

            {unenrolled.length > 0 && (
              <div className="banner warn mt">
                <div>
                  <div className="banner-title">Accounts without a second factor</div>
                  {unenrolled.map((member) => `${member.name} (${member.email})`).join(", ")} — they enrol at their
                  next sign-in; nobody can skip it while two-factor is required.
                </div>
              </div>
            )}

            <div className="split mt">
              <Card title="Accounts" subtitle="Second factors and last sign-in per person.">
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Person</th>
                        <th>Two-factor</th>
                        <th>Passkeys</th>
                        <th>Last sign-in</th>
                      </tr>
                    </thead>
                    <tbody>
                      {db.staff.map((member) => (
                        <tr key={member.id}>
                          <td>
                            <Link className="strong small" href={`/staff/${member.id}`}>
                              {member.name}
                            </Link>
                            <div className="tiny muted">{member.email}</div>
                          </td>
                          <td>
                            <span className={`chip ${member.totp?.enabled ? "ok" : "warn"}`}>
                              {member.totp?.enabled ? "enrolled" : "pending"}
                            </span>
                          </td>
                          <td className="small">{member.passkeys?.length ?? 0}</td>
                          <td className="small muted nowrap">
                            {member.lastLoginAt ? shortDate(member.lastLoginAt) : "never"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              <Card
                title="Failed sign-ins"
                subtitle="Newest first, with where the attempt came from. Addresses are recorded, passwords never are."
                action={failures.length > 0 ? <ClearAuthLog count={failures.length} /> : undefined}
              >
                <div className="card-body stack-sm">
                  {failures.length === 0 ? (
                    <span className="small muted">Nothing has been refused yet.</span>
                  ) : (
                    failures.slice(0, 10).map((event) => (
                      <div key={event.id} className="between" style={{ alignItems: "flex-start" }}>
                        <div>
                          <div className="small strong">{OUTCOME_LABELS[event.outcome] ?? humanStatus(event.outcome)}</div>
                          <div className="tiny muted">
                            {event.email} · from {event.source || "before sources were recorded"}
                          </div>
                          {event.detail && <div className="tiny muted">{event.detail}</div>}
                        </div>
                        <span className="tiny muted nowrap">{dateTime(event.at)}</span>
                      </div>
                    ))
                  )}
                  <span className="tiny muted">
                    <strong>this computer</strong> means the attempt came from the machine running the console — your
                    own browser or an automated check. An IP address means it arrived over the network. Test accounts you
                    create look exactly like a stranger&apos;s attempt, so clear the log once you have read it. Five
                    refusals for one address in fifteen minutes pause its password and code sign-in until the oldest
                    falls out of the window; passkeys are never paused.
                  </span>
                  <Link className="btn small ghost" href="/staff">
                    Review staff {pending.length ? `· ${pending.length} pending request(s)` : ""}
                  </Link>
                </div>
              </Card>
            </div>

            <Card
              title="Paused sign-ins"
              subtitle="Addresses and sources currently throttled after repeated refusals. Unlocking removes the refusals behind the pause."
              className="mt"
            >
              <div className="card-body stack-sm">
                <LockoutList entries={paused} />
              </div>
            </Card>

            <Card
              title="Live sessions"
              subtitle={`Every sign-in that can still reach the console, newest first, with where it came from. A source holds at most ${SESSIONS_PER_SOURCE}; a fourth sign-in ends its oldest.`}
              className="mt"
            >
              <div className="card-body stack-sm">
                <SessionList
                  entries={sessions}
                  stepUp={Boolean(me?.totp?.enabled || (me?.passkeys?.length ?? 0) > 0)}
                  confirmed={confirmed}
                  passkeyCount={me?.passkeys?.length ?? 0}
                />
              </div>
            </Card>

            <Card
              title="Recently ended"
              subtitle="The last eight sessions that stopped working, with who ended them and why."
              className="mt"
            >
              <div className="card-body stack-sm">
                {endedSessions.length === 0 ? (
                  <span className="small muted">No session has been ended yet.</span>
                ) : (
                  endedSessions.map((entry) => (
                    <div key={entry.id} className="between" style={{ alignItems: "flex-start" }}>
                      <div>
                        <div className="small strong">{entry.name}</div>
                        <div className="tiny muted">
                          {entry.email} · from {entry.source}
                        </div>
                        <div className="tiny muted">
                          started {entry.startedAt} · ended {entry.endedAt}
                          {entry.by ? ` · by ${entry.by}` : ""}
                        </div>
                      </div>
                      <span className="chip muted nowrap">{entry.reason}</span>
                    </div>
                  ))
                )}
                <span className="tiny muted">
                  Sign-ins that simply expire are dropped without an entry. Everything else — a registrar ending a
                  session, an access change, the per-source cap, or the person signing out — is kept here, newest
                  first, and survives the live-session registry being pruned.
                </span>
              </div>
            </Card>

            <Card
              title="Registrar alerts"
              subtitle="New access requests and repeated failed sign-ins, emailed to every registrar."
              className="mt"
            >
              <div className="card-body stack-sm">
                <div className="between">
                  <span className="small muted">Mail relay</span>
                  <span className={`chip ${mailReady ? "ok" : "warn"}`}>
                    {mailReady ? "Configured" : "Not configured"}
                  </span>
                </div>
                <span className="tiny muted">
                  Alerts use the same relay as the operations digest: set <span className="mono">MAIL_API_KEY</span>{" "}
                  and <span className="mono">MAIL_FROM</span> in <span className="mono">.env</span>, then restart.{" "}
                  <span className="mono">MAIL_API_URL</span> points at another relay; it defaults to Resend. The sender
                  domain must be verified by whichever relay you use. Until a key is set, alerts are skipped silently
                  and sign-in never waits on them.
                </span>
                <MailTestButton />
                <span className="tiny muted">
                  Alerts currently go to {alertRecipients().join(", ") || "no one — add a registrar or a security address"}
                  . Set a dedicated address under Health → Operations digest; it overrides the registrar list.
                </span>
              </div>
            </Card>
          </>
        )}

        {!registrar && (
          <Card title="Registrar view" className="mt">
            <div className="card-body small muted">
              Account-wide security (failed sign-ins, who has enrolled) is visible to registrars.
            </div>
          </Card>
        )}
      </div>
    </>
  );
}
