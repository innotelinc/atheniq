import { createHash } from "node:crypto";
import { getDb, logActivity, mutate, newId, nowIso, verifyId } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { findLesson, needsResponse } from "@/lib/lesson-content";
import { accessOpen } from "@/lib/mobile-commerce";
import { progressOf } from "@/lib/mobile-shape";
import type { Completion, Credential, Enrollment, Learner } from "@/lib/types";

export const dynamic = "force-dynamic";

interface Body {
  courseId?: string;
  lessonId?: string;
  done?: boolean;
  /** Written answer for quiz, exam, project and discussion lessons. */
  response?: string;
}

/**
 * Mark a lesson read, or save the written answer that completes it.
 *
 * When the last lesson is done the course is recorded as a passing completion
 * and a certificate is queued for the registrar — the same ledger the console
 * awards from, so the app is not a separate island of progress.
 */
export async function POST(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in to track your progress.", 401);
  if (identity.role !== "learner") return fail("Staff accounts do not carry learner progress.", 403);

  const body = (await request.json().catch(() => null)) as Body | null;
  const courseId = text(body?.courseId, 200);
  const lessonId = text(body?.lessonId, 120);
  const done = body?.done !== false;
  const answer = text(body?.response, 4000);
  if (!courseId || !lessonId) return fail("Choose a lesson.");

  const db = getDb();
  const course = db.courses.find((item) => item.id === courseId || item.key === courseId);
  if (!course) return fail("That course is not in the catalog.", 404);
  const found = findLesson(course, lessonId);
  if (!found) return fail("That lesson is not part of this course.", 404);

  const learner = db.learners.find((item) => item.id === identity.sub);
  if (!learner) return fail("That learner account no longer exists.", 401);
  const enrollment = db.enrollments.find(
    (item) => item.learnerId === learner.id && item.courseId === course.id,
  );
  if (!enrollment) return fail("Enroll in this course first.", 409);
  if (!accessOpen(enrollment.access)) {
    return fail("This course opens once the registrar confirms your payment.", 402);
  }

  const existingAnswer = enrollment.responses[lessonId] ?? "";
  if (done && needsResponse(found.lesson.type) && !(answer || existingAnswer).trim()) {
    return fail("Write your answer before marking this lesson complete.", 422, { needsResponse: true });
  }

  const result = await mutate((store) => {
    const row = store.enrollments.find((item) => item.id === enrollment.id) as Enrollment | undefined;
    if (!row) return null;

    if (answer) row.responses[lessonId] = answer;
    const has = row.completedLessonIds.includes(lessonId);
    if (done && !has) row.completedLessonIds.push(lessonId);
    if (!done && has) row.completedLessonIds = row.completedLessonIds.filter((id) => id !== lessonId);
    row.lastSeenAt = nowIso();

    const total = course.modules.reduce((sum, module) => sum + module.lessons.length, 0);
    const finished = total > 0 && row.completedLessonIds.length >= total;
    let credential: Credential | null = null;

    if (finished && !row.completedAt) {
      row.completedAt = nowIso();
      const completedOn = row.completedAt.slice(0, 10);

      const completion: Completion = {
        id: newId("cmp"),
        learnerId: row.learnerId,
        courseKey: course.key,
        grade: "Pass",
        completedOn,
        status: "pass",
      };
      if (!store.completions.some((item) => item.learnerId === row.learnerId && item.courseKey === course.key)) {
        store.completions.push(completion);
      }

      const owner = store.learners.find((item) => item.id === row.learnerId) as Learner;
      const already = store.credentials.find(
        (item) =>
          item.type === "course_certificate" &&
          item.subjectRef === course.key &&
          item.learner.username === owner.username,
      );
      if (!already) {
        const at = nowIso();
        const evidence = { grade: "Pass", completedOn, courses: [course.key] };
        credential = {
          id: newId("crd"),
          verifyId: verifyId(),
          type: "course_certificate",
          title: `${course.title} — Certificate of Completion (${owner.name})`,
          subjectRef: course.key,
          subjectLabel: course.title,
          learner: { username: owner.username, name: owner.name, email: owner.email },
          evidence,
          status: "queued_local",
          signara: {
            documentId: null,
            requestId: null,
            signerToken: null,
            apiBase: null,
            lastHttp: null,
            lastError: null,
          },
          template: store.settings.signara.defaultTemplate,
          signer: { ...store.settings.signer },
          hash: createHash("sha256")
            .update(JSON.stringify({ courseKey: course.key, learner: owner.username, evidence }))
            .digest("hex"),
          previewPath: null,
          createdAt: at,
          updatedAt: at,
          signedAt: null,
          issuedAt: null,
          revokedAt: null,
          revokeReason: null,
          timeline: [
            {
              at,
              label: "Course completed in the AthenIQ app",
              detail: `${total} lessons, ${course.code}`,
            },
            { at, label: "Certificate queued for the registrar" },
          ],
        };
        store.credentials.push(credential);
      }

      logActivity(
        store,
        "learner.completed",
        `${owner.name} completed ${course.code} — ${course.title} in the app.`,
        course.key,
      );
    }

    return { progress: progressOf(course, row), completedAt: row.completedAt, credential };
  });

  if (!result) return fail("That enrollment no longer exists. Enroll again.", 409);
  return ok(result);
}

export function OPTIONS() {
  return preflight();
}
