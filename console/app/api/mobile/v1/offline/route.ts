import { getDb } from "@/lib/store";
import { fail, ok, preflight } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { accessOpen } from "@/lib/mobile-commerce";
import { buildLesson, courseLessonCount, findLesson } from "@/lib/lesson-content";
import { courseDetail } from "@/lib/mobile-shape";

export const dynamic = "force-dynamic";

/**
 * A whole course in one response, for reading without a network.
 *
 * The app stores it on the device and falls back to it when a lesson fetch
 * fails. Answers are not downloaded with it — progress still needs the server,
 * so nothing can be marked complete off the record.
 */
export async function GET(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in to download a course.", 401);
  if (identity.role !== "learner") return fail("Downloads belong to learner accounts.", 403);

  const url = new URL(request.url);
  const courseId = url.searchParams.get("courseId") || "";
  if (!courseId) return fail("Choose a course.");

  const db = getDb();
  const course = db.courses.find((item) => item.id === courseId || item.key === courseId);
  if (!course) return fail("That course is not in the catalog.", 404);

  const enrollment = db.enrollments.find(
    (item) => item.learnerId === identity.sub && item.courseId === course.id,
  );
  if (!enrollment) return fail("Enroll in this course to download it.", 409);
  if (!accessOpen(enrollment.access)) {
    return fail("This course opens once the registrar confirms your payment.", 402);
  }

  const programNames = new Map(db.programs.map((program) => [program.id, program.name]));
  const flat = course.modules.flatMap((module) =>
    module.lessons.map((lesson) => ({ module, lesson })),
  );
  const total = courseLessonCount(course);

  return ok({
    downloadedAt: new Date().toISOString(),
    course: courseDetail(course, enrollment, programNames),
    lessons: flat.map(({ module, lesson }, index) => ({
      ...buildLesson(course, module, lesson, { index, total }),
      position: { index, total },
      done: enrollment.completedLessonIds.includes(lesson.id),
    })),
    curriculum: course.modules.map((module) => ({
      id: module.id,
      title: module.title,
      lessons: module.lessons.map((lesson) => {
        const found = findLesson(course, lesson.id);
        return { id: lesson.id, title: lesson.title, type: lesson.type, minutes: lesson.minutes, module: found?.module.title ?? module.title };
      }),
    })),
  });
}

export function OPTIONS() {
  return preflight();
}
