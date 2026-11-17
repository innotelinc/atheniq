import { getDb } from "@/lib/store";
import { fail, ok, preflight } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { courseDetail } from "@/lib/mobile-shape";
import type { Enrollment } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const db = getDb();
  const course = db.courses.find(
    (item) => item.status === "published" && (item.id === id || item.key === decodeURIComponent(id)),
  );
  if (!course) return fail("That course is not published.", 404);

  const identity = bearerIdentity(request);
  let enrollment: Enrollment | null = null;
  if (identity?.role === "learner") {
    enrollment =
      db.enrollments.find(
        (item) => item.learnerId === identity.sub && item.courseId === course.id,
      ) ?? null;
  }

  const programNames = new Map(db.programs.map((program) => [program.id, program.name]));
  return ok(courseDetail(course, enrollment, programNames));
}

export function OPTIONS() {
  return preflight();
}
