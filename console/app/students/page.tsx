import Link from "next/link";
import { currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { getDb } from "@/lib/store";
import { can } from "@/lib/staff-policy";
import { money, shortDate } from "@/lib/format";
import { Card, Crumbs, PageHead, Stat, Topbar } from "@/components/ui";

export const dynamic = "force-dynamic";

export const metadata = { title: "Students — AthenIQ console" };

/**
 * The registrar's view of the student body: who is admitted, what they are
 * taking, what they owe and what they have earned. Everything here is the same
 * record the student portal renders, which is the point — a change made here is
 * what the student sees, rather than a second copy of the truth.
 */
export default async function StudentsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; note?: string }>;
}) {
  const params = await searchParams;
  const query = (params.q ?? "").trim().toLowerCase();
  const note = (params.note ?? "").trim();

  const db = getDb();
  const me = await currentStaff();
  const allowed = !authEnabled() || can(me?.role, "award");

  const programNames = new Map(db.programs.map((program) => [program.id, program.name]));

  const rows = db.learners
    .map((learner) => {
      const enrollments = db.enrollments.filter((item) => item.learnerId === learner.id);
      const completed = enrollments.filter((item) => item.completedAt);
      const credits = completed.reduce((sum, enrollment) => {
        const course = db.courses.find((item) => item.id === enrollment.courseId);
        return sum + (course?.credits ?? 0);
      }, 0);
      const outstanding = db.purchases
        .filter(
          (item) =>
            item.learnerId === learner.id &&
            (item.status === "pending" || item.status === "claimed"),
        )
        .reduce((sum, item) => sum + item.amountCents, 0);
      const awaiting = db.purchases.filter(
        (item) => item.learnerId === learner.id && item.status === "claimed",
      ).length;
      const credentials = db.credentials.filter(
        (item) => item.learner.username === learner.username && item.status === "issued",
      ).length;

      return {
        id: learner.id,
        name: learner.name,
        email: learner.email,
        username: learner.username,
        programName: learner.programId ? programNames.get(learner.programId) ?? null : null,
        enrolledAt: learner.enrolledAt,
        lastSeenAt: learner.lastSeenAt ?? null,
        courses: enrollments.length,
        completed: completed.length,
        credits,
        outstanding,
        awaiting,
        credentials,
        hasPassword: Boolean(learner.passwordHash),
      };
    })
    .filter((row) =>
      query
        ? row.name.toLowerCase().includes(query) ||
          row.email.toLowerCase().includes(query) ||
          row.username.toLowerCase().includes(query)
        : true,
    )
    .sort((a, b) => a.name.localeCompare(b.name));

  const totals = rows.reduce(
    (acc, row) => ({
      courses: acc.courses + row.courses,
      credits: acc.credits + row.credits,
      outstanding: acc.outstanding + row.outstanding,
      awaiting: acc.awaiting + row.awaiting,
    }),
    { courses: 0, credits: 0, outstanding: 0, awaiting: 0 },
  );

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Students" }]} />
        <div className="row">
          <span className="chip muted">{rows.length} students</span>
          {totals.awaiting > 0 ? (
            <span className="chip warn">{totals.awaiting} payment claim(s) to decide</span>
          ) : null}
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Student administration"
          title="Students"
          subtitle="Admissions, enrolments, billing and grades in one place. This is the record the student portal shows, so what you change here is what the student sees."
        />

        {note ? (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="card-body">
              <span className="chip ok">{note}</span>
            </div>
          </div>
        ) : null}

        {!allowed ? (
          <Card title="Registrar only">
            <div className="card-body stack-sm">
              <p className="small muted" style={{ margin: 0 }}>
                Your account can publish courses but cannot administer students.
              </p>
              <Link className="btn small" href="/">
                Back to the dashboard
              </Link>
            </div>
          </Card>
        ) : (
          <div className="stack mt">
            <div className="stats">
              <Stat label="Students" value={db.learners.length} />
              <Stat label="Enrolments" value={totals.courses} />
              <Stat label="Credits earned" value={totals.credits} />
              <Stat label="Outstanding" value={money(totals.outstanding)} hint="Claimed or pending" />
            </div>

            <Card
              title="Everyone enrolled"
              subtitle="Open a student to settle a payment, record a grade or check their progress."
              action={
                <form action="/students" method="get" className="row">
                  <input
                    className="input"
                    type="search"
                    name="q"
                    placeholder="Name, email or username"
                    defaultValue={params.q ?? ""}
                    style={{ minWidth: 220 }}
                  />
                  <button className="btn small" type="submit">
                    Search
                  </button>
                </form>
              }
            >
              <div className="table-wrap">
                {rows.length === 0 ? (
                  <div className="card-body">
                    <span className="small muted">
                      {query ? "No student matches that search." : "No students yet."}
                    </span>
                  </div>
                ) : (
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Student</th>
                        <th>Program</th>
                        <th>Courses</th>
                        <th>Credits</th>
                        <th>Outstanding</th>
                        <th>Credentials</th>
                        <th>Last seen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <Link className="strong small" href={`/students/${row.id}`}>
                              {row.name}
                            </Link>
                            <div className="tiny muted">{row.email}</div>
                            {!row.hasPassword ? (
                              <span className="tiny muted">no portal password set</span>
                            ) : null}
                          </td>
                          <td className="small muted">{row.programName ?? "—"}</td>
                          <td className="small">
                            {row.completed}/{row.courses}
                          </td>
                          <td className="small">{row.credits}</td>
                          <td className="small">
                            {row.outstanding > 0 ? money(row.outstanding) : "—"}
                            {row.awaiting > 0 ? (
                              <div className="tiny muted">{row.awaiting} to decide</div>
                            ) : null}
                          </td>
                          <td className="small">{row.credentials || "—"}</td>
                          <td className="small muted nowrap">
                            {row.lastSeenAt ? shortDate(row.lastSeenAt) : "never"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </Card>

            <Card title="Admitted but not enrolled" subtitle="A student with no course on their record yet.">
              <div className="card-body stack-sm">
                {rows.filter((row) => row.courses === 0).length === 0 ? (
                  <span className="small muted">Everyone admitted has at least one course.</span>
                ) : (
                  rows
                    .filter((row) => row.courses === 0)
                    .map((row) => (
                      <div key={row.id} className="between">
                        <Link className="small" href={`/students/${row.id}`}>
                          {row.name}
                        </Link>
                        <span className="tiny muted">admitted {shortDate(row.enrolledAt)}</span>
                      </div>
                    ))
                )}
              </div>
            </Card>
          </div>
        )}
      </div>
    </>
  );
}
