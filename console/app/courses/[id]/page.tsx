import Link from "next/link";
import { notFound } from "next/navigation";
import { getDb } from "@/lib/store";
import { money, shortDate, termLabelOf } from "@/lib/format-ext";
import { Badge, Card, Crumbs, PageHead, Topbar } from "@/components/ui";
import { CourseEditor } from "@/components/CourseEditor";
import { PublishPanel } from "@/components/PublishPanel";

export const dynamic = "force-dynamic";

export default async function CoursePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const course = db.courses.find((c) => c.id === id);
  if (!course) notFound();

  const access = course.price.amountCents
    ? `${money(course.price.amountCents)} one-off`
    : course.price.plan
      ? `Magnate plan “${course.price.plan}”`
      : "Free";

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Courses", href: "/courses" }, { label: course.code }]} />
        <div className="row">
          <Link className="btn small ghost" href={`/credentials?course=${encodeURIComponent(course.key)}`}>
            Award certificate
          </Link>
          <Link className="btn small" href="/courses">
            All courses
          </Link>
        </div>
      </Topbar>

      <div className="content">
        <div className="hero">
          <div className="between" style={{ alignItems: "flex-start" }}>
            <div>
              <div className="eyebrow">{course.department}</div>
              <h1 className="page-title" style={{ fontSize: 26 }}>
                {course.code} — {course.title.replace(`${course.code} — `, "")}
              </h1>
              <p className="page-sub">{course.summary}</p>
            </div>
            <div className="row">
              <Badge status={course.status} />
            </div>
          </div>
          <div className="hero-meta">
            <span className="chip plain">{course.credits} credits</span>
            <span className="chip plain">Level {course.level}</span>
            <span className="chip plain">{termLabelOf(course.term)}</span>
            <span className="chip plain">{access}</span>
            <span className="chip plain mono">{course.key}</span>
          </div>
        </div>

        <div className="split mt">
          <CourseEditor
            course={course}
            programs={db.programs.map((p) => ({ id: p.id, label: p.credential }))}
            tracks={db.tracks.map((t) => ({ id: t.id, label: t.title }))}
            terms={["2027_T1", "2026_T4", "2027_T2", "2027_T3"]}
          />
          <div className="stack">
            <PublishPanel course={course} />
            <Card title="Record">
              <div className="card-body stack-sm small">
                <Row label="Runtime key" value={<span className="mono">{course.key}</span>} />
                <Row label="Created" value={shortDate(course.createdAt)} />
                <Row label="Last updated" value={shortDate(course.updatedAt)} />
                <Row label="Published" value={course.publishedAt ? shortDate(course.publishedAt) : "Not yet"} />
                <Row
                  label="Modules"
                  value={`${course.modules.length} · ${course.modules.reduce((n, m) => n + m.lessons.length, 0)} lessons`}
                />
                <Row
                  label="Source"
                  value={course.generationId ? "Course studio" : "Manual authoring"}
                />
              </div>
              <div className="card-foot">
                <div className="stack-sm">
                  <a href={`${db.settings.sites.coursesUrl}/catalog/`} target="_blank" rel="noreferrer">
                    Open the course catalog →
                  </a>
                  <a href={`${db.settings.sites.instituteUrl}/catalog/`} target="_blank" rel="noreferrer">
                    Open the institute catalog →
                  </a>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="between">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}
