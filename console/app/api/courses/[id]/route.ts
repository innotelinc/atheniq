import { getDb, logActivity, mutate } from "@/lib/store";
import { coerceGrading, coerceLevel, coerceModules, titleFor } from "@/lib/courses";
import { fail, num, ok, str, strArray } from "@/lib/api";
import { currentActor } from "@/lib/current-staff";
import type { Course } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const course = db.courses.find((c) => c.id === id);
  if (!course) return fail("Course not found.", 404);
  return ok(course);
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) return fail("Invalid body.");

  const actor = await currentActor();
  const outcome = await mutate((db) => {
    const course = db.courses.find((c) => c.id === id);
    if (!course) return { error: "Course not found." as string, status: 404 as const };

    if (body.title !== undefined) {
      const title = str(body.title);
      if (!title) return { error: "The title cannot be empty." as string, status: 400 as const };
      course.title = title.startsWith(`${course.code} —`) ? title : `${course.code} — ${titleFor({ ...course, title } as Course)}`;
    }
    if (body.summary !== undefined) course.summary = str(body.summary);
    if (body.description !== undefined) course.description = str(body.description);
    if (body.audience !== undefined) course.audience = str(body.audience);
    if (body.outcomes !== undefined) course.outcomes = strArray(body.outcomes);
    if (body.prerequisites !== undefined) course.prerequisites = strArray(body.prerequisites);
    if (body.credits !== undefined) course.credits = Math.min(6, Math.max(1, num(body.credits, course.credits)));
    if (body.level !== undefined) course.level = coerceLevel(body.level, course.level);
    if (body.department !== undefined) course.department = str(body.department) || course.department;
    if (body.term !== undefined) {
      const term = str(body.term);
      if (term && term !== course.term) {
        if (db.courses.some((c) => c.code === course.code && c.term === term)) {
          return { error: `${course.code} already exists in ${term}.` as string, status: 400 as const };
        }
        course.term = term;
        course.key = `course-v1:${course.org}+${course.code}+${term}`;
      }
    }
    if (body.modules !== undefined) {
      const modules = coerceModules(body.modules);
      if (!modules.length) return { error: "A course needs at least one module." as string, status: 400 as const };
      course.modules = modules;
    }
    if (body.grading !== undefined) course.grading = coerceGrading(body.grading, course.grading);
    if (body.programIds !== undefined) course.programIds = strArray(body.programIds);
    if (body.trackIds !== undefined) course.trackIds = strArray(body.trackIds);
    if (body.plan !== undefined || body.amountCents !== undefined) {
      course.price = {
        plan: body.plan === undefined ? course.price.plan : (str(body.plan) || null),
        amountCents:
          body.amountCents === undefined || body.amountCents === null || body.amountCents === ""
            ? course.price.amountCents
            : num(body.amountCents, course.price.amountCents ?? 0),
      };
    }
    if (body.status !== undefined) {
      const status = str(body.status);
      if (["draft", "in_review", "published", "archived"].includes(status)) {
        course.status = status as Course["status"];
        if (status === "published" && !course.publishedAt) course.publishedAt = new Date().toISOString();
      }
    }

    course.updatedAt = new Date().toISOString();
    logActivity(db, "course.updated", `Updated ${course.code}`, course.key, actor);
    return { course };
  });

  if ("error" in outcome && outcome.error) return fail(outcome.error, outcome.status ?? 400);
  return ok((outcome as { course: Course }).course);
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const actor = await currentActor();
  const removed = await mutate((db) => {
    const index = db.courses.findIndex((c) => c.id === id);
    if (index < 0) return null;
    const [course] = db.courses.splice(index, 1);
    db.tracks.forEach((track) => {
      track.courses = track.courses.filter((key) => key !== course.key);
    });
    db.programs.forEach((program) => {
      program.semesters.forEach((semester) => {
        semester.courses = semester.courses.filter((c) => c.code !== course.code);
      });
    });
    logActivity(db, "course.updated", `Removed ${course.code} from the catalog`, course.key, actor);
    return course;
  });
  if (!removed) return fail("Course not found.", 404);
  return ok({ deleted: id });
}
