import Link from "next/link";
import { notFound } from "next/navigation";
import { currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { getDb } from "@/lib/store";
import { can } from "@/lib/staff-policy";
import { dateTime, money, shortDate } from "@/lib/format";
import { progressOf } from "@/lib/mobile-shape";
import { Card, Crumbs, PageHead, Topbar } from "@/components/ui";

export const dynamic = "force-dynamic";

const ACCESS_LABEL: Record<string, string> = {
  open: "Open",
  paid: "Paid",
  granted: "Granted",
  pending_payment: "Awaiting payment",
};

const PURCHASE_TONE: Record<string, string> = {
  pending: "muted",
  claimed: "warn",
  confirmed: "ok",
  declined: "bad",
};

export default async function StudentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ note?: string }>;
}) {
  const { id } = await params;
  const { note } = await searchParams;

  const db = getDb();
  const learner = db.learners.find((item) => item.id === id);
  if (!learner) notFound();

  const me = await currentStaff();
  const allowed = !authEnabled() || can(me?.role, "award");
  const back = `/students/${learner.id}`;

  const program = learner.programId
    ? db.programs.find((item) => item.id === learner.programId)
    : undefined;

  const enrollments = db.enrollments
    .filter((item) => item.learnerId === learner.id)
    .map((enrollment) => {
      const course = db.courses.find((item) => item.id === enrollment.courseId);
      return {
        enrollment,
        course,
        progress: course ? progressOf(course, enrollment) : null,
        access: enrollment.access ?? "open",
      };
    })
    .sort((a, b) => (a.course?.code ?? "").localeCompare(b.course?.code ?? ""));

  const purchases = db.purchases
    .filter((item) => item.learnerId === learner.id)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const completions = db.completions
    .filter((item) => item.learnerId === learner.id)
    .sort((a, b) => b.completedOn.localeCompare(a.completedOn));

  const credentials = db.credentials.filter(
    (item) => item.learner.username === learner.username,
  );

  const credits = completions
    .filter((item) => item.status === "pass")
    .reduce((sum, item) => {
      const course = db.courses.find((entry) => entry.key === item.courseKey);
      return sum + (course?.credits ?? 0);
    }, 0);

  const outstanding = purchases
    .filter((item) => item.status === "pending" || item.status === "claimed")
    .reduce((sum, item) => sum + item.amountCents, 0);

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Students", href: "/students" }, { label: learner.name }]} />
        <div className="row">
          <Link className="btn small ghost" href="/students">
            All students
          </Link>
          <span className="chip muted">{learner.username}</span>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow={program?.name ?? "Not in a program yet"}
          title={learner.name}
          subtitle={`${learner.email} · admitted ${shortDate(learner.enrolledAt)} · ${enrollments.length} course(s), ${credits} credit(s), ${money(outstanding)} outstanding`}
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
                Your account can publish courses but cannot decide payments or record grades.
              </p>
              <Link className="btn small" href="/">
                Back to the dashboard
              </Link>
            </div>
          </Card>
        ) : null}

        <div className="stack mt">
          <Card
            title="Courses"
            subtitle="Access, progress and the courseware link the student sees in their portal."
          >
            <div className="table-wrap">
              {enrollments.length === 0 ? (
                <div className="card-body">
                  <span className="small muted">No courses yet.</span>
                </div>
              ) : (
                <table className="data">
                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Access</th>
                      <th>Progress</th>
                      <th>Enrolled</th>
                      <th>Finished</th>
                    </tr>
                  </thead>
                  <tbody>
                    {enrollments.map(({ enrollment, course, progress, access }) => (
                      <tr key={enrollment.id}>
                        <td>
                          <div className="small strong">{course?.code ?? enrollment.courseKey}</div>
                          <div className="tiny muted">{course?.title ?? "course no longer in the catalogue"}</div>
                        </td>
                        <td className="small">
                          <span className={`chip ${access === "open" || access === "paid" || access === "granted" ? "ok" : "warn"}`}>
                            {ACCESS_LABEL[access] ?? access}
                          </span>
                        </td>
                        <td className="small">
                          {progress ? `${progress.done}/${progress.total} · ${progress.percent}%` : "—"}
                        </td>
                        <td className="small muted nowrap">{shortDate(enrollment.enrolledAt)}</td>
                        <td className="small muted nowrap">
                          {enrollment.completedAt ? shortDate(enrollment.completedAt) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>

          <Card
            title="Billing"
            subtitle="Confirming opens the course; granting does the same without a payment. A card payment confirms itself."
          >
            <div className="table-wrap">
              {purchases.length === 0 ? (
                <div className="card-body">
                  <span className="small muted">Nothing billed to this student.</span>
                </div>
              ) : (
                <table className="data">
                  <thead>
                    <tr>
                      <th>Reference</th>
                      <th>Course</th>
                      <th>Amount</th>
                      <th>Status</th>
                      <th>Decided</th>
                      <th>Decision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {purchases.map((purchase) => (
                      <tr key={purchase.id}>
                        <td className="small nowrap">{purchase.reference}</td>
                        <td className="small">{purchase.courseKey.split("+")[1] ?? purchase.courseKey}</td>
                        <td className="small">{money(purchase.amountCents)}</td>
                        <td className="small">
                          <span className={`chip ${PURCHASE_TONE[purchase.status] ?? "muted"}`}>
                            {purchase.status === "confirmed" && purchase.granted ? "granted" : purchase.status}
                          </span>
                        </td>
                        <td className="small muted nowrap">
                          {purchase.decidedAt ? dateTime(purchase.decidedAt) : "—"}
                          {purchase.decidedBy ? <div className="tiny muted">{purchase.decidedBy}</div> : null}
                        </td>
                        <td>
                          {purchase.status === "confirmed" || purchase.status === "declined" ? (
                            <span className="tiny muted">settled</span>
                          ) : (
                            <div className="row">
                              <form action="/api/students/purchase" method="post">
                                <input type="hidden" name="purchaseId" value={purchase.id} />
                                <input type="hidden" name="back" value={back} />
                                <input type="hidden" name="action" value="confirm" />
                                <button className="btn small" type="submit">
                                  Confirm
                                </button>
                              </form>
                              <form action="/api/students/purchase" method="post">
                                <input type="hidden" name="purchaseId" value={purchase.id} />
                                <input type="hidden" name="back" value={back} />
                                <input type="hidden" name="action" value="grant" />
                                <button className="btn small ghost" type="submit">
                                  Grant
                                </button>
                              </form>
                              <form action="/api/students/purchase" method="post">
                                <input type="hidden" name="purchaseId" value={purchase.id} />
                                <input type="hidden" name="back" value={back} />
                                <input type="hidden" name="action" value="decline" />
                                <button className="btn small ghost" type="submit">
                                  Decline
                                </button>
                              </form>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>

          <Card
            title="Institute address"
            subtitle="Reserved once from the name they enrolled under; a graduate keeps it."
          >
            <div className="card-body stack-sm">
              {learner.mailbox ? (
                <div className="between">
                  <div>
                    <div className="small strong">{learner.mailbox.address}</div>
                    <div className="tiny muted">
                      {learner.mailbox.status} · reserved {shortDate(learner.mailbox.createdAt)}
                    </div>
                  </div>
                  <span className={`chip ${learner.mailbox.status === "active" ? "ok" : "warn"}`}>
                    {learner.mailbox.status}
                  </span>
                </div>
              ) : (
                <>
                  <span className="small muted">
                    No institute address yet. Reserving the name is immediate; mail is delivered
                    once the mailbox exists on the institute mail server.
                  </span>
                  {allowed ? (
                    <form action="/api/students/mailbox" method="post">
                      <input type="hidden" name="learnerId" value={learner.id} />
                      <input type="hidden" name="back" value={back} />
                      <button className="btn small" type="submit">
                        Reserve address
                      </button>
                    </form>
                  ) : null}
                </>
              )}
            </div>
          </Card>

          <div className="split">
            <Card
              title="Record a grade"
              subtitle="A pass finishes the course on this student's portal; a fail leaves it open to try again."
            >
              <div className="card-body stack-sm">
                {enrollments.length === 0 ? (
                  <span className="small muted">Enrol the student in a course first.</span>
                ) : (
                  <form action="/api/students/completion" method="post" className="stack-sm">
                    <input type="hidden" name="learnerId" value={learner.id} />
                    <label className="label" htmlFor="courseKey">
                      Course
                    </label>
                    <select className="input" id="courseKey" name="courseKey" defaultValue="">
                      <option value="" disabled>
                        Choose a course
                      </option>
                      {enrollments.map(({ course, enrollment }) => (
                        <option key={enrollment.id} value={enrollment.courseKey}>
                          {course?.code ?? enrollment.courseKey} — {course?.title ?? ""}
                        </option>
                      ))}
                    </select>
                    <label className="label" htmlFor="grade">
                      Grade
                    </label>
                    <input className="input" id="grade" name="grade" placeholder="A, 92, Pass" maxLength={20} />
                    <label className="label" htmlFor="status">
                      Outcome
                    </label>
                    <select className="input" id="status" name="status" defaultValue="pass">
                      <option value="pass">Pass</option>
                      <option value="fail">Fail</option>
                    </select>
                    <button className="btn small" type="submit">
                      Record grade
                    </button>
                  </form>
                )}
              </div>
            </Card>

            <Card title="Grades on record" subtitle="What a credential can be issued against.">
              <div className="card-body stack-sm">
                {completions.length === 0 ? (
                  <span className="small muted">No grades recorded yet.</span>
                ) : (
                  completions.map((completion) => (
                    <div key={completion.id} className="between">
                      <div>
                        <div className="small">
                          {completion.courseKey.split("+")[1] ?? completion.courseKey} · {completion.grade}
                        </div>
                        <div className="tiny muted">{shortDate(completion.completedOn)}</div>
                      </div>
                      <span className={`chip ${completion.status === "pass" ? "ok" : "bad"}`}>
                        {completion.status}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>

          <Card title="Credentials" subtitle="Issued through the signing ledger; each one has a public verification page.">
            <div className="card-body stack-sm">
              {credentials.length === 0 ? (
                <span className="small muted">
                  Nothing issued yet.{" "}
                  <Link className="small" href="/credentials">
                    Issue one from Credentials
                  </Link>
                  .
                </span>
              ) : (
                credentials.map((credential) => (
                  <div key={credential.id} className="between">
                    <div>
                      <Link className="small" href={`/credentials/${credential.id}`}>
                        {credential.title}
                      </Link>
                      <div className="tiny muted">
                        {credential.type} · {credential.issuedAt ? shortDate(credential.issuedAt) : "not issued"}
                      </div>
                    </div>
                    <div className="row">
                      <span className={`chip ${credential.status === "issued" ? "ok" : "muted"}`}>
                        {credential.status}
                      </span>
                      <a className="btn small ghost" href={`/verify/${credential.verifyId}`}>
                        Verify
                      </a>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
