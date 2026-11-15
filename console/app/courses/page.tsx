import Link from "next/link";
import { getDb } from "@/lib/store";
import { money, humanStatus, shortDate } from "@/lib/format";
import { Badge, Card, Empty, PageHead, Topbar, Crumbs } from "@/components/ui";
import type { Course } from "@/lib/types";

export const dynamic = "force-dynamic";

const STATUSES: Course["status"][] = ["published", "in_review", "draft", "archived"];

export default async function CoursesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; status?: string; program?: string; track?: string; page?: string }>;
}) {
  const params = await searchParams;
  const db = getDb();
  const q = (params.q ?? "").trim().toLowerCase();
  const status = params.status ?? "";
  const programId = params.program ?? "";
  const trackId = params.track ?? "";

  const courses = db.courses
    .filter((course) => {
      if (status && course.status !== status) return false;
      if (programId && !course.programIds.includes(programId)) return false;
      if (trackId && !course.trackIds.includes(trackId)) return false;
      if (q) {
        const haystack = `${course.code} ${course.title} ${course.department} ${course.summary}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    })
    .sort((a, b) => {
      const order = { in_review: 0, draft: 1, published: 2, archived: 3 } as Record<string, number>;
      const diff = (order[a.status] ?? 9) - (order[b.status] ?? 9);
      return diff !== 0 ? diff : a.code.localeCompare(b.code);
    });

  const PAGE_SIZE = 30;
  const pageCount = Math.max(1, Math.ceil(courses.length / PAGE_SIZE));
  const page = Math.min(pageCount, Math.max(1, Number(params.page) || 1));
  const start = (page - 1) * PAGE_SIZE;
  const visible = courses.slice(start, start + PAGE_SIZE);
  const pageHref = (target: number) => {
    const query = new URLSearchParams();
    if (params.q) query.set("q", params.q);
    if (status) query.set("status", status);
    if (programId) query.set("program", programId);
    if (trackId) query.set("track", trackId);
    if (target > 1) query.set("page", String(target));
    const suffix = query.toString();
    return suffix ? `/courses?${suffix}` : "/courses";
  };

  const programName = (id: string) => db.programs.find((p) => p.id === id)?.credential ?? id;
  const trackName = (id: string) => db.tracks.find((t) => t.id === id)?.title ?? id;

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Registrar console" }, { label: "Courses" }]} />
        <div className="row">
          <Link className="btn small" href="/generate">
            Course studio
          </Link>
          <Link className="btn primary small" href="/courses/new">
            New course
          </Link>
        </div>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Catalog"
          title="Courses"
          subtitle={`${db.courses.filter((c) => c.status === "published").length} published of ${db.courses.length}. Every row is a runtime course key at atheniq.courses.`}
        />

        <Card>
          <form method="get" className="card-body tight">
            <div className="row" style={{ gap: 10 }}>
              <input
                className="input"
                style={{ maxWidth: 300 }}
                type="search"
                name="q"
                defaultValue={params.q ?? ""}
                placeholder="Search code, title, department…"
                aria-label="Search courses"
              />
              <select className="select" style={{ maxWidth: 170 }} name="status" defaultValue={status} aria-label="Status">
                <option value="">All statuses</option>
                {STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {humanStatus(value)}
                  </option>
                ))}
              </select>
              <select className="select" style={{ maxWidth: 240 }} name="program" defaultValue={programId} aria-label="Program">
                <option value="">All programs</option>
                {db.programs.map((program) => (
                  <option key={program.id} value={program.id}>
                    {program.credential}
                  </option>
                ))}
              </select>
              <select className="select" style={{ maxWidth: 220 }} name="track" defaultValue={trackId} aria-label="Track">
                <option value="">All tracks</option>
                {db.tracks.map((track) => (
                  <option key={track.id} value={track.id}>
                    {track.title}
                  </option>
                ))}
              </select>
              <button className="btn" type="submit">
                Filter
              </button>
              {(q || status || programId || trackId) && (
                <Link className="btn ghost small" href="/courses">
                  Clear
                </Link>
              )}
              <span className="right small muted">
                {courses.length === 0
                  ? "no matches"
                  : `${start + 1}–${Math.min(start + PAGE_SIZE, courses.length)} of ${courses.length}`}
              </span>
            </div>
          </form>
        </Card>

        <Card className="mt">
          {courses.length === 0 ? (
            <Empty
              title="No courses match"
              body="Clear the filters, or create the course you are looking for."
              action={
                <Link className="btn primary" href="/courses/new">
                  New course
                </Link>
              }
            />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Course</th>
                    <th>Status</th>
                    <th>Placement</th>
                    <th className="num">Credits</th>
                    <th>Access</th>
                    <th>Updated</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((course) => (
                    <tr key={course.id}>
                      <td>
                        <Link href={`/courses/${course.id}`} className="strong">
                          {course.code} — {course.title.replace(`${course.code} — `, "")}
                        </Link>
                        <div className="small muted">
                          {course.department} · {course.modules.length} modules
                        </div>
                        <div className="tiny mono muted">{course.key}</div>
                      </td>
                      <td>
                        <Badge status={course.status} />
                      </td>
                      <td>
                        <div className="stack-sm" style={{ gap: 2 }}>
                          {course.programIds.map((id) => (
                            <span key={id} className="chip plain muted">
                              {programName(id)}
                            </span>
                          ))}
                          {course.trackIds.map((id) => (
                            <span key={id} className="chip plain muted">
                              {trackName(id)}
                            </span>
                          ))}
                          {!course.programIds.length && !course.trackIds.length && (
                            <span className="tiny muted">Unplaced</span>
                          )}
                        </div>
                      </td>
                      <td className="num">{course.credits}</td>
                      <td>
                        <span className="small">
                          {course.price.amountCents
                            ? money(course.price.amountCents)
                            : course.price.plan
                              ? course.price.plan
                              : "Free"}
                        </span>
                      </td>
                      <td className="small muted nowrap">{shortDate(course.updatedAt)}</td>
                      <td className="actions">
                        <Link className="btn small" href={`/courses/${course.id}`}>
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

        {pageCount > 1 && (
          <div className="row mt" style={{ gap: 6 }}>
            <Link className="btn small" href={pageHref(page - 1)} aria-disabled={page === 1}>
              ← Previous
            </Link>
            <span className="small muted" style={{ padding: "0 8px" }}>
              Page {page} of {pageCount}
            </span>
            <Link className="btn small" href={pageHref(page + 1)} aria-disabled={page === pageCount}>
              Next →
            </Link>
          </div>
        )}
      </div>
    </>
  );
}
