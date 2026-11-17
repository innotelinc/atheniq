import { getDb } from "@/lib/store";
import { fail, ok, preflight } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { catalogCard, progressOf } from "@/lib/mobile-shape";

export const dynamic = "force-dynamic";

/** The learner's own page: enrollments with progress, and their certificates. */
export async function GET(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in.", 401);
  if (identity.role !== "learner") return fail("This page belongs to learner accounts.", 403);

  const db = getDb();
  const learner = db.learners.find((item) => item.id === identity.sub);
  if (!learner) return fail("That learner account no longer exists.", 401);

  const programNames = new Map(db.programs.map((program) => [program.id, program.name]));
  const enrollments = db.enrollments
    .filter((item) => item.learnerId === learner.id)
    .map((enrollment) => {
      const course = db.courses.find((item) => item.id === enrollment.courseId);
      if (!course) return null;
      return {
        id: enrollment.id,
        enrolledAt: enrollment.enrolledAt,
        completedAt: enrollment.completedAt,
        lastSeenAt: enrollment.lastSeenAt,
        course: catalogCard(course, programNames),
        progress: progressOf(course, enrollment),
        access: enrollment.access ?? "open",
      };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
    .sort((a, b) => (b.lastSeenAt || "").localeCompare(a.lastSeenAt || ""));

  const credentials = db.credentials
    .filter((credential) => credential.learner.username === learner.username)
    .map((credential) => ({
      id: credential.id,
      verifyId: credential.verifyId,
      title: credential.title,
      type: credential.type,
      status: credential.status,
      issuedAt: credential.issuedAt,
      createdAt: credential.createdAt,
      subjectLabel: credential.subjectLabel,
    }))
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  const completed = enrollments.filter((item) => item.completedAt).length;
  const credits = enrollments
    .filter((item) => item.completedAt)
    .reduce((sum, item) => sum + item.course.credits, 0);

  return ok({
    learner: {
      id: learner.id,
      name: learner.name,
      email: learner.email,
      programId: learner.programId,
      programName: learner.programId ? programNames.get(learner.programId) ?? null : null,
      enrolledAt: learner.enrolledAt,
    },
    stats: {
      enrolled: enrollments.length,
      completed,
      inProgress: enrollments.length - completed,
      credits,
      certificates: credentials.filter((item) => item.status === "issued").length,
    },
    enrollments,
    credentials,
  });
}

export function OPTIONS() {
  return preflight();
}
