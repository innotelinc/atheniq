import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";

export const dynamic = "force-dynamic";

/**
 * "I have paid" — the learner quotes the reference from their payment.
 *
 * Nothing unlocks here. The registrar sees the claim beside the reference and
 * confirms it, which is the only thing that opens the course.
 */
export async function POST(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in.", 401);
  if (identity.role !== "learner") return fail("Only a learner can claim a payment.", 403);

  const body = (await request.json().catch(() => null)) as {
    courseId?: string;
    reference?: string;
    note?: string;
  } | null;
  const courseId = text(body?.courseId, 200);
  const reference = text(body?.reference, 60).toUpperCase();
  const note = text(body?.note, 300);
  if (!courseId) return fail("Choose a course.");
  if (!reference) return fail("Quote the payment reference.");

  const db = getDb();
  const enrollment = db.enrollments.find(
    (item) =>
      item.learnerId === identity.sub &&
      (item.courseId === courseId || item.courseKey === courseId),
  );
  if (!enrollment) return fail("Enroll in the course first.", 409);
  const purchase = enrollment.purchaseId
    ? db.purchases.find((item) => item.id === enrollment.purchaseId)
    : undefined;
  if (!purchase) return fail("This course has no payment to claim.", 409);
  if (purchase.status === "confirmed") return ok({ claimed: false, status: "confirmed" });
  if (purchase.reference.toUpperCase() !== reference) {
    return fail("That reference does not match this enrollment.", 422);
  }

  await mutate((store) => {
    const row = store.purchases.find((item) => item.id === purchase.id);
    if (!row) return;
    row.status = "claimed";
    row.note = note;
    const learner = store.learners.find((item) => item.id === identity.sub);
    logActivity(
      store,
      "course.purchased",
      `${learner?.name ?? "A learner"} says they paid for ${enrollment.courseKey} (${row.reference}); waiting on the registrar.`,
      enrollment.courseKey,
    );
  });

  return ok({ claimed: true, status: "claimed", reference: purchase.reference });
}

export function OPTIONS() {
  return preflight();
}
