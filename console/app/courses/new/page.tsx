import Link from "next/link";
import { getDb } from "@/lib/store";
import { nextCourseCode } from "@/lib/courses";
import { PageHead, Topbar, Crumbs } from "@/components/ui";
import { CourseNewForm } from "@/components/CourseNewForm";

export const dynamic = "force-dynamic";

export default function NewCoursePage() {
  const db = getDb();
  const departments = Array.from(
    new Set([
      ...db.courses.map((course) => course.department),
      "Business",
      "Criminal Justice",
      "Nursing",
      "Applied AI",
      "Data",
      "Information Technology",
      "Teaching & Learning",
      "Health Administration",
      "General Studies",
    ]),
  ).sort();

  const suggested = nextCourseCode(db, "General Studies");

  return (
    <>
      <Topbar>
        <Crumbs items={[{ label: "Courses", href: "/courses" }, { label: "New course" }]} />
        <Link className="btn small ghost" href="/generate">
          Generate instead
        </Link>
      </Topbar>

      <div className="content">
        <PageHead
          eyebrow="Catalog authoring"
          title="New course"
          subtitle="Create the record first; the curriculum editor opens as soon as the course exists. Courses start as drafts and only appear on the sites once you publish."
        />
        <CourseNewForm
          departments={departments}
          programs={db.programs.map((p) => ({ id: p.id, label: p.credential }))}
          tracks={db.tracks.map((t) => ({ id: t.id, label: t.title }))}
          terms={["2027_T1", "2026_T4", "2027_T2", "2027_T3"]}
          defaultTerm={db.settings.defaultTerm}
          suggestedCode={suggested}
          creditsPerCourse={db.settings.creditsPerCourse}
        />
      </div>
    </>
  );
}
