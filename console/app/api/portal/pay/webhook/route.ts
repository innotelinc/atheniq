import { NextResponse } from "next/server";
import { logActivity, mutate, nowIso } from "@/lib/store";
import { verifyStripeSignature } from "@/lib/stripe";

export const dynamic = "force-dynamic";

/**
 * Stripe telling us a card payment settled.
 *
 * This is the only place a card payment opens a course, and it is reachable
 * without a learner session — so the signature check is the authentication.
 * Nothing is read from the event body before it verifies.
 */
export async function POST(request: Request) {
  const raw = await request.text();
  if (!verifyStripeSignature(raw, request.headers.get("stripe-signature"))) {
    return NextResponse.json({ error: "Bad signature." }, { status: 400 });
  }

  let event: {
    type?: string;
    data?: {
      object?: {
        id?: string;
        client_reference_id?: string | null;
        payment_status?: string | null;
        metadata?: Record<string, string> | null;
      };
    };
  };
  try {
    event = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "Unreadable event." }, { status: 400 });
  }

  const type = event.type ?? "";
  if (type !== "checkout.session.completed" && type !== "checkout.session.async_payment_succeeded") {
    return NextResponse.json({ received: true, ignored: type });
  }

  const session = event.data?.object;
  // Bank debits and similar settle later; the checkout completing is not the
  // payment completing, so wait for the async event in that case.
  if (session?.payment_status && session.payment_status !== "paid") {
    return NextResponse.json({ received: true, awaiting: session.payment_status });
  }

  const purchaseId = (session?.metadata?.purchaseId ?? "").trim();
  const reference = (session?.client_reference_id ?? "").trim();

  const outcome = await mutate((store) => {
    const row = store.purchases.find(
      (item) =>
        (purchaseId && item.id === purchaseId) || (reference && item.reference === reference),
    );
    if (!row) return null;
    if (row.status === "confirmed") return { reference: row.reference, alreadyConfirmed: true };

    row.status = "confirmed";
    row.decidedAt = nowIso();
    row.decidedBy = "stripe";
    row.granted = false;

    // The enrollment may predate the purchase row, so match on both.
    const enrollment =
      store.enrollments.find((item) => item.purchaseId === row.id) ??
      store.enrollments.find(
        (item) => item.learnerId === row.learnerId && item.courseId === row.courseId,
      );
    if (enrollment) {
      enrollment.access = "paid";
      enrollment.purchaseId = row.id;
    }

    const learner = store.learners.find((item) => item.id === row.learnerId);
    logActivity(
      store,
      "course.purchased",
      `Stripe confirmed payment ${row.reference} for ${learner?.name ?? "a learner"} in ${row.courseKey}.`,
      row.courseKey,
      null,
    );
    return { reference: row.reference, alreadyConfirmed: false };
  });

  // 200 either way: a 4xx makes Stripe retry an event we have already handled.
  return NextResponse.json({ received: true, matched: Boolean(outcome), ...(outcome ?? {}) });
}
