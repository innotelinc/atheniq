import Link from "next/link";
import { currentStaff } from "@/lib/current-staff";
import { authEnabled } from "@/lib/session";
import { getDb } from "@/lib/store";
import { can } from "@/lib/staff-policy";
import { dateTime } from "@/lib/format";
import { Card, Crumbs, PageHead, Topbar } from "@/components/ui";

export const dynamic = "force-dynamic";

export const metadata = { title: "News — AthenIQ registrar" };

/**
 * What the institute says to its students, and to whom.
 *
 * A notice is either school-wide or addressed to one program; the portal filters
 * on the same value, so a cohort never sees another cohort's dates.
 */
export default async function NewsPage({
  searchParams,
}: {
  searchParams: Promise<{ note?: string }>;
}) {
  const { note } = await searchParams;

  const db = getDb();
  const me = await currentStaff();
  const allowed = !authEnabled() || can(me?.role, "award");
  const programs = db.programs;

  const posts = [...(db.news ?? [])].sort(
    (a, b) => Number(b.pinned) - Number(a.pinned) || b.publishedAt.localeCompare(a.publishedAt),
  );

  const audienceLabel = (audience: string) =>
    audience === "all"
      ? "Everyone"
      : programs.find((program) => program.id === audience)?.name ?? "a retired cohort";

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "News" }]} />
        <div className="row">
          <span className="chip muted">{posts.length} notice(s)</span>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Student portals"
          title="News"
          subtitle="Notices appear at the top of every matching student's portal. Pinned notices stay there."
        />

        {note ? (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="card-body">
              <span className="chip ok">{note}</span>
            </div>
          </div>
        ) : null}

        <div className="split mt">
          <Card title="Published notices" subtitle="Newest first; pinned notices stay at the top of the portal.">
            <div className="table-wrap">
              {posts.length === 0 ? (
                <div className="card-body">
                  <span className="small muted">Nothing published yet.</span>
                </div>
              ) : (
                <table className="data">
                  <thead>
                    <tr>
                      <th>Notice</th>
                      <th>Audience</th>
                      <th>Published</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {posts.map((post) => (
                      <tr key={post.id}>
                        <td>
                          <div className="small strong">
                            {post.pinned ? "★ " : ""}
                            {post.title}
                          </div>
                          <div className="tiny muted">
                            {post.body.length > 140 ? `${post.body.slice(0, 140)}…` : post.body}
                          </div>
                        </td>
                        <td className="small">{audienceLabel(post.audience)}</td>
                        <td className="small muted nowrap">
                          {dateTime(post.publishedAt)}
                          <div className="tiny muted">{post.author}</div>
                        </td>
                        <td>
                          <form action="/api/news" method="post">
                            <input type="hidden" name="action" value="delete" />
                            <input type="hidden" name="id" value={post.id} />
                            <button className="btn small ghost" type="submit">
                              Withdraw
                            </button>
                          </form>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>

          <Card title="Publish a notice" subtitle="Registrar only.">
            <div className="card-body stack-sm">
              {!allowed ? (
                <span className="small muted">
                  Your account can publish courses but not notices.{" "}
                  <Link className="small" href="/">
                    Back to the dashboard
                  </Link>
                  .
                </span>
              ) : (
                <form action="/api/news" method="post" className="stack-sm">
                  <input type="hidden" name="action" value="create" />
                  <label className="label" htmlFor="title">
                    Title
                  </label>
                  <input
                    className="input"
                    id="title"
                    name="title"
                    maxLength={140}
                    placeholder="Spring term registration opens Monday"
                    required
                  />
                  <label className="label" htmlFor="body">
                    Notice
                  </label>
                  <textarea
                    className="input"
                    id="body"
                    name="body"
                    rows={6}
                    maxLength={4000}
                    placeholder="What changed, what to do, and by when."
                    required
                  />
                  <label className="label" htmlFor="audience">
                    Audience
                  </label>
                  <select className="input" id="audience" name="audience" defaultValue="all">
                    <option value="all">Everyone</option>
                    {programs.map((program) => (
                      <option key={program.id} value={program.id}>
                        {program.name}
                      </option>
                    ))}
                  </select>
                  <label className="row" style={{ gap: 8, alignItems: "center" }}>
                    <input type="checkbox" name="pinned" />
                    <span className="small">Pin to the top of the portal</span>
                  </label>
                  <button className="btn small" type="submit">
                    Publish
                  </button>
                </form>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
