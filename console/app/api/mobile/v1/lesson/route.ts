import { getDb, mutate, nowIso } from "@/lib/store";
import { fail, ok, preflight } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { buildLesson, courseLessonCount, findLesson } from "@/lib/lesson-content";
import { accessOpen } from "@/lib/mobile-commerce";

export const dynamic = "force-dynamic";

/** One lesson: the text to read, the task, and any answer already saved. */
export async function GET(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in to open a lesson.", 401);

  const url = new URL(request.url);
  const courseId = url.searchParams.get("courseId") || "";
  const lessonId = url.searchParams.get("lessonId") || "";
  if (!courseId || !lessonId) return fail("Choose a lesson.");

  const db = getDb();
  const course = db.courses.find((item) => item.id === courseId || item.key === courseId);
  if (!course) return fail("That course is not in the catalog.", 404);
  const found = findLesson(course, lessonId);
  if (!found) return fail("That lesson is not part of this course.", 404);

  const enrollment = db.enrollments.find(
    (item) => item.learnerId === identity.sub && item.courseId === course.id,
  );
  if (!enrollment) return fail("Enroll in this course to read its lessons.", 409);
  if (!accessOpen(enrollment.access)) {
    return fail("This course opens once the registrar confirms your payment.", 402);
  }

  const flat = course.modules.flatMap((module) =>
    module.lessons.map((lesson) => ({ module, lesson })),
  );
  const index = flat.findIndex(({ lesson }) => lesson.id === lessonId);
  const content = buildLesson(course, found.module, found.lesson, {
    index,
    total: courseLessonCount(course),
  });

  await mutate((store) => {
    const row = store.enrollments.find((item) => item.id === enrollment.id);
    if (row) row.lastSeenAt = nowIso();
  });

  return ok({
    course: { id: course.id, code: course.code, title: course.title },
    ...content,
    done: enrollment.completedLessonIds.includes(lessonId),
    response: enrollment.responses[lessonId] ?? "",
    position: { index, total: flat.length },
    nextLessonId: flat[index + 1]?.lesson.id ?? null,
  });
}

export function OPTIONS() {
  return preflight();
}
