import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import { fail, ok, preflight } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { progressOf } from "@/lib/mobile-shape";
import { checkoutUrl, coursePriceCents, purchaseReference, requiresPayment } from "@/lib/mobile-commerce";
import type { Enrollment, Purchase } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Enroll in a published course.
 *
 * Free courses open immediately. A priced course or a plan-gated one does not:
 * the run is created `pending_payment` and lessons stay shut until a registrar
 * confirms the payment (or grants the place), because the app has no card
 * details and the console never had a processor.
 */
export async function POST(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in to enroll.", 401);
  if (identity.role !== "learner") return fail("Staff accounts cannot enroll as learners.", 403);

  const body = (await request.json().catch(() => null)) as { courseId?: string; courseKey?: string } | null;
  const wanted = (body?.courseId || body?.courseKey || "").trim();
  if (!wanted) return fail("Choose a course.");

  const db = getDb();
  const course = db.courses.find(
    (item) => item.status === "published" && (item.id === wanted || item.key === wanted),
  );
  if (!course) return fail("That course is not open for enrollment.", 404);
  const learner = db.learners.find((item) => item.id === identity.sub);
  if (!learner) return fail("That learner account no longer exists.", 401);

  const theCourse = course;
  const theLearner = learner;

  const result = await mutate((store) => {
    const existing = store.enrollments.find(
      (item) => item.learnerId === theLearner.id && item.courseId === theCourse.id,
    );
    if (existing) {
      const purchase = existing.purchaseId
        ? store.purchases.find((item) => item.id === existing.purchaseId) ?? null
        : null;
      return {
        enrollment: existing,
        progress: progressOf(theCourse, existing),
        alreadyEnrolled: true,
        purchase,
        checkout: purchase && purchase.status !== "confirmed"
          ? {
              reference: purchase.reference,
              amountCents: purchase.amountCents,
              url: checkoutUrl(theCourse, purchase.reference),
            }
          : null,
      };
    }

    if (requiresPayment(theCourse)) {
      const reference = purchaseReference(theCourse);
      const created: Enrollment = {
        id: newId("enr"),
        learnerId: theLearner.id,
        courseId: theCourse.id,
        courseKey: theCourse.key,
        enrolledAt: nowIso(),
        lastSeenAt: nowIso(),
        completedLessonIds: [],
        responses: {},
        completedAt: null,
        access: "pending_payment",
        purchaseId: null,
      };
      const purchase: Purchase = {
        id: newId("pur"),
        learnerId: theLearner.id,
        courseId: theCourse.id,
        courseKey: theCourse.key,
        amountCents: coursePriceCents(theCourse),
        reference,
        status: "pending",
        note: "",
        createdAt: nowIso(),
        decidedAt: null,
        decidedBy: null,
        granted: false,
      };
      created.purchaseId = purchase.id;
      store.purchases.push(purchase);
      store.enrollments.push(created);
      logActivity(
        store,
        "learner.enrolled",
        `${theLearner.name} started ${theCourse.code} — ${theCourse.title}; payment of ${purchase.amountCents ? `$${(purchase.amountCents / 100).toFixed(2)}` : "a plan"} is pending.`,
        theCourse.key,
      );
      return {
        enrollment: created,
        progress: progressOf(theCourse, created),
        alreadyEnrolled: false,
        purchase,
        checkout: {
          reference,
          amountCents: purchase.amountCents,
          url: checkoutUrl(theCourse, reference),
        },
      };
    }

    const open: Enrollment = {
      id: newId("enr"),
      learnerId: theLearner.id,
      courseId: theCourse.id,
      courseKey: theCourse.key,
      enrolledAt: nowIso(),
      lastSeenAt: nowIso(),
      completedLessonIds: [],
      responses: {},
      completedAt: null,
      access: "open",
      purchaseId: null,
    };
    store.enrollments.push(open);
    logActivity(
      store,
      "learner.enrolled",
      `${theLearner.name} enrolled in ${theCourse.code} — ${theCourse.title} from the app.`,
      theCourse.key,
    );
    return {
      enrollment: open,
      progress: progressOf(theCourse, open),
      alreadyEnrolled: false,
      purchase: null,
      checkout: null,
    };
  });

  return ok(result, result.alreadyEnrolled ? 200 : 201);
}

export function OPTIONS() {
  return preflight();
}
