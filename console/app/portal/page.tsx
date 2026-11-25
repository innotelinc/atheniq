import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getDb } from "@/lib/store";
import { PORTAL_COOKIE, portalView, readPortalSession } from "@/lib/portal";
import { money } from "@/lib/format";
import { paymentsEnabled } from "@/lib/stripe";

export const dynamic = "force-dynamic";

export const metadata = { title: "Student portal — AthenIQ Institute" };

function date(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? "—"
    : parsed.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

const ACCESS_LABEL: Record<string, string> = {
  open: "Open",
  paid: "Paid",
  granted: "Granted",
  pending_payment: "Awaiting payment",
};

export default async function PortalPage() {
  const learnerId = readPortalSession((await cookies()).get(PORTAL_COOKIE)?.value);
  if (!learnerId) redirect("/portal/login");

  const db = getDb();
  const learner = db.learners.find((item) => item.id === learnerId);
  if (!learner) redirect("/portal/login");

  const view = await portalView(db, learner);
  const cardPay = paymentsEnabled();

  return (
    <div className="portal">
      <header className="portal-head">
        <div>
          <h1 className="portal-title">{view.learner.name}</h1>
          <p className="portal-lede">
            {view.learner.programName ? `${view.learner.programName} · ` : ""}
            Admitted {date(view.learner.enrolledAt)} · {view.learner.email}
          </p>
          {view.learner.mailbox ? (
            <p className="portal-aside" style={{ margin: "4px 0 0" }}>
              Institute address: <strong>{view.learner.mailbox.address}</strong>
              {view.learner.mailbox.status === "active" ? "" : " (being set up)"}
            </p>
          ) : null}
        </div>
        <form action="/api/portal/logout" method="post">
          <button className="btn small" type="submit">
            Sign out
          </button>
        </form>
      </header>

      <section className="portal-stats" aria-label="Progress summary">
        <div className="portal-stat">
          <span className="portal-stat-value">{view.stats.enrolled}</span>
          <span className="portal-stat-label">Courses</span>
        </div>
        <div className="portal-stat">
          <span className="portal-stat-value">{view.stats.completed}</span>
          <span className="portal-stat-label">Completed</span>
        </div>
        <div className="portal-stat">
          <span className="portal-stat-value">{view.stats.credits}</span>
          <span className="portal-stat-label">Credits earned</span>
        </div>
        <div className="portal-stat">
          <span className="portal-stat-value">{view.stats.certificates}</span>
          <span className="portal-stat-label">Credentials</span>
        </div>
        <div className="portal-stat">
          <span className="portal-stat-value">{money(view.stats.outstandingCents)}</span>
          <span className="portal-stat-label">Outstanding</span>
        </div>
      </section>

      {view.news.length > 0 ? (
        <section className="portal-section" aria-label="News">
          <h2 className="portal-h2">News</h2>
          <ul className="portal-certs">
            {view.news.map((post) => (
              <li key={post.id}>
                <span className="strong">{post.title}</span>
                <span className="portal-aside">
                  {" "}
                  · {date(post.publishedAt)}
                  {post.pinned ? " · pinned" : ""}
                </span>
                <p className="portal-aside" style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>
                  {post.body}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="portal-section" aria-label="Your courses">
        <h2 className="portal-h2">Your courses</h2>
        {view.courses.length === 0 ? (
          <p className="portal-aside">
            No courses yet. Browse the catalog at{" "}
            <a href={db.settings.lms.catalogUrl}>{db.settings.lms.catalogUrl}</a>.
          </p>
        ) : (
          <ul className="portal-courses">
            {view.courses.map((course) => (
              <li className="portal-course" key={course.id}>
                <div className="portal-course-head">
                  <span className="portal-code">{course.code}</span>
                  <span className="portal-course-title">{course.title}</span>
                  <span className={`portal-badge ${course.completedAt ? "is-done" : ""}`}>
                    {course.completedAt ? "Completed" : ACCESS_LABEL[course.access] ?? course.access}
                  </span>
                </div>
                <div className="portal-bar" role="img" aria-label={`${course.progress.percent}% complete`}>
                  <span style={{ width: `${course.progress.percent}%` }} />
                </div>
                <p className="portal-aside">
                  {course.progress.done} of {course.progress.total} lessons ·{" "}
                  {course.progress.percent}% · {course.credits} credits
                  {course.liveInLms ? "" : " · not yet available in the courseware"}
                </p>
                {course.access === "pending_payment" && cardPay ? (
                  <form action="/api/portal/pay" method="post">
                    <input type="hidden" name="enrollmentId" value={course.id} />
                    <button className="btn small" type="submit">
                      Pay by card
                    </button>
                  </form>
                ) : null}
                {course.coursewareUrl && course.access !== "pending_payment" ? (
                  <a className="btn small" href={course.coursewareUrl}>
                    Open course
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {view.billing.length > 0 ? (
        <section className="portal-section" aria-label="Billing">
          <h2 className="portal-h2">Billing</h2>
          <table className="portal-table">
            <thead>
              <tr>
                <th scope="col">Reference</th>
                <th scope="col">Course</th>
                <th scope="col">Amount</th>
                <th scope="col">Status</th>
                <th scope="col">Date</th>
              </tr>
            </thead>
            <tbody>
              {view.billing.map((entry) => (
                <tr key={entry.reference}>
                  <td>{entry.reference}</td>
                  <td>{entry.courseKey}</td>
                  <td>{money(entry.amountCents)}</td>
                  <td>{entry.status}</td>
                  <td>{date(entry.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {view.certificates.length > 0 ? (
        <section className="portal-section" aria-label="Credentials">
          <h2 className="portal-h2">Credentials</h2>
          <ul className="portal-certs">
            {view.certificates.map((certificate) => (
              <li key={certificate.id}>
                <Link href={`/verify/${certificate.verifyId}`}>{certificate.title}</Link>
                <span className="portal-aside">
                  {" "}
                  · {certificate.type} · {certificate.status} · {date(certificate.issuedAt)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
