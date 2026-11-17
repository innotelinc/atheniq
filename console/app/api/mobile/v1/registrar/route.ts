import { getDb } from "@/lib/store";
import { fail, ok, preflight } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";

export const dynamic = "force-dynamic";

/** The registrar's phone view of the school: what needs a decision, and what moved. */
export async function GET(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in with a staff account.", 401);
  if (identity.role !== "staff") return fail("That account is a learner account.", 403);

  const db = getDb();
  const now = Date.now();
  const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString();

  const active = db.enrollments.filter((enrollment) => !enrollment.completedAt);
  const queue = db.credentials
    .filter((credential) => credential.status === "queued_local" || credential.status === "submitted" || credential.status === "partial" || credential.status === "signed")
    .slice()
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .slice(0, 25)
    .map((credential) => ({
      id: credential.id,
      title: credential.subjectLabel || credential.title,
      learner: credential.learner.name,
      email: credential.learner.email,
      type: credential.type,
      status: credential.status,
      verifyId: credential.verifyId,
      createdAt: credential.createdAt,
      detail: credential.timeline[credential.timeline.length - 1]?.label ?? "",
    }));

  return ok({
    staff: { id: identity.sub, name: identity.name, email: identity.email, role: identity.staffRole ?? "publisher" },
    counts: {
      learners: db.learners.length,
      newLearners: db.learners.filter((learner) => learner.enrolledAt >= weekAgo).length,
      enrollments: db.enrollments.length,
      active: active.length,
      completions: db.completions.length,
      certificatesQueued: queue.filter((item) => item.status === "queued_local").length,
      certificatesIssued: db.credentials.filter((credential) => credential.status === "issued").length,
      publishedCourses: db.courses.filter((course) => course.status === "published").length,
      paymentsWaiting: db.purchases.filter(
        (purchase) => purchase.status === "pending" || purchase.status === "claimed",
      ).length,
    },
    queue,
    purchases: db.purchases
      .filter((purchase) => purchase.status === "pending" || purchase.status === "claimed")
      .slice()
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, 25)
      .map((purchase) => {
        const learner = db.learners.find((item) => item.id === purchase.learnerId);
        const course = db.courses.find((item) => item.id === purchase.courseId);
        return {
          id: purchase.id,
          reference: purchase.reference,
          learner: learner?.name ?? "Learner",
          email: learner?.email ?? "",
          course: course ? `${course.code} — ${course.title}` : purchase.courseKey,
          amountCents: purchase.amountCents,
          status: purchase.status,
          note: purchase.note,
          createdAt: purchase.createdAt,
        };
      }),
    activity: db.activity.slice(0, 12).map((entry) => ({
      id: entry.id,
      at: entry.at,
      kind: entry.kind,
      message: entry.message,
    })),
    recentLearners: db.learners
      .slice()
      .sort((a, b) => b.enrolledAt.localeCompare(a.enrolledAt))
      .slice(0, 8)
      .map((learner) => ({
        id: learner.id,
        name: learner.name,
        email: learner.email,
        enrolledAt: learner.enrolledAt,
        courses: db.enrollments.filter((enrollment) => enrollment.learnerId === learner.id).length,
      })),
  });
}

export function OPTIONS() {
  return preflight();
}
