import { getDb } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { checkoutUrl, coursePriceCents, requiresPayment } from "@/lib/mobile-commerce";

export const dynamic = "force-dynamic";

/**
 * Where to send someone to pay.
 *
 * `url` is the school's hosted checkout (CHECKOUT_URL with the reference filled
 * in). When the school bills another way, `url` is null and the app shows the
 * reference plus a claim form instead of a dead button.
 */
export async function POST(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in to pay for a course.", 401);
  if (identity.role !== "learner") return fail("Staff accounts cannot buy courses.", 403);

  const body = (await request.json().catch(() => null)) as { courseId?: string } | null;
  const courseId = text(body?.courseId, 200);
  if (!courseId) return fail("Choose a course.");

  const db = getDb();
  const course = db.courses.find((item) => item.id === courseId || item.key === courseId);
  if (!course) return fail("That course does not exist.", 404);
  if (!requiresPayment(course)) return ok({ required: false });

  const enrollment = db.enrollments.find(
    (item) => item.learnerId === identity.sub && item.courseId === course.id,
  );
  const purchase = enrollment?.purchaseId
    ? db.purchases.find((item) => item.id === enrollment.purchaseId)
    : db.purchases.find(
        (item) => item.learnerId === identity.sub && item.courseId === course.id && item.status !== "declined",
      );
  if (!purchase) return fail("Enroll first, then pay.", 409);

  return ok({
    required: true,
    reference: purchase.reference,
    amountCents: purchase.amountCents || coursePriceCents(course),
    status: purchase.status,
    url: checkoutUrl(course, purchase.reference),
  });
}

export function OPTIONS() {
  return preflight();
}
