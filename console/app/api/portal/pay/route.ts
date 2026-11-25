import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { getDb } from "@/lib/store";
import { PORTAL_COOKIE, readPortalSession } from "@/lib/portal";
import { coursePriceCents } from "@/lib/mobile-commerce";
import { createCheckoutSession, paymentsEnabled } from "@/lib/stripe";

export const dynamic = "force-dynamic";

/**
 * Send a student to pay an invoice they already have.
 *
 * Deliberately not an "enroll and pay" endpoint: the enrollment and its
 * reference exist first, exactly as the app's claim flow expects, so a card
 * payment and a bank transfer end up in the same place — a confirmed purchase
 * against that reference.
 */
export async function POST(request: Request) {
  const origin = new URL(request.url).origin;
  const back = (query: string) => NextResponse.redirect(new URL(`/portal?${query}`, origin), 303);

  const learnerId = readPortalSession((await cookies()).get(PORTAL_COOKIE)?.value);
  if (!learnerId) return NextResponse.redirect(new URL("/portal/login", origin), 303);

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return back("error=That+payment+request+could+not+be+read.");
  }
  const enrollmentId = String(form.get("enrollmentId") ?? "").trim();

  const db = getDb();
  const learner = db.learners.find((item) => item.id === learnerId);
  if (!learner) return NextResponse.redirect(new URL("/portal/login", origin), 303);

  const enrollment = db.enrollments.find(
    (item) => item.id === enrollmentId && item.learnerId === learnerId,
  );
  if (!enrollment) return back("error=That+course+is+not+on+your+record.");

  const course = db.courses.find((item) => item.id === enrollment.courseId);
  if (!course) return back("error=That+course+no+longer+exists.");

  const purchase = enrollment.purchaseId
    ? db.purchases.find((item) => item.id === enrollment.purchaseId)
    : db.purchases.find(
        (item) =>
          item.learnerId === learnerId && item.courseId === course.id && item.status !== "declined",
      );
  if (!purchase) return back("error=That+course+has+no+invoice+to+pay.");

  // Paid twice is worse than a stale link: never open a second session.
  if (purchase.status === "confirmed") return NextResponse.redirect(new URL("/portal", origin), 303);
  if (!paymentsEnabled()) return back("error=Card+payment+is+not+set+up+yet.");

  const session = await createCheckoutSession({
    reference: purchase.reference,
    purchaseId: purchase.id,
    courseKey: purchase.courseKey,
    title: course.title,
    amountCents: purchase.amountCents || coursePriceCents(course),
    email: learner.email,
    successUrl: `${origin}/portal?paid=${encodeURIComponent(purchase.reference)}`,
    cancelUrl: `${origin}/portal?cancelled=1`,
  });

  if ("error" in session) {
    return back(`error=${encodeURIComponent(session.error)}`);
  }
  return NextResponse.redirect(session.url, 303);
}
