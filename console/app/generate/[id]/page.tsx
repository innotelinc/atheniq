import Link from "next/link";
import { notFound } from "next/navigation";
import { getDb } from "@/lib/store";
import { Crumbs, Topbar } from "@/components/ui";
import { Studio } from "@/components/Studio";

export const dynamic = "force-dynamic";

export default async function SessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const session = db.sessions.find((s) => s.id === id);
  if (!session) notFound();

  const course = session.courseId ? db.courses.find((c) => c.id === session.courseId) : null;

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Course studio", href: "/generate" }, { label: "Session" }]} />
        <div className="row">
          {course && (
            <Link className="btn small" href={`/courses/${course.id}`}>
              Open {course.code}
            </Link>
          )}
          <Link className="btn small ghost" href="/generate">
            New session
          </Link>
        </div>
      </Topbar>

      <div className="content">
        <Studio
          session={session}
          programs={db.programs.map((p) => ({ id: p.id, label: p.credential }))}
          tracks={db.tracks.map((t) => ({ id: t.id, label: t.title }))}
          terms={["2027_T1", "2026_T4", "2027_T2", "2027_T3"]}
          modelName={db.settings.ai.model}
        />
      </div>
    </>
  );
}
