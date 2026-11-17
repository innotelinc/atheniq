import type { Course } from "./types";

/**
 * What a course costs, and how the app hands the learner to a checkout.
 *
 * The console has never taken card details itself: a course either sits behind
 * a Magnate plan or carries a one-off price, and the school bills through
 * whatever hosted checkout it already uses. The app keeps that boundary — it
 * gates lessons on a recorded entitlement and sends the learner to
 * `CHECKOUT_URL` (with {reference}, {amount}, {course} filled in) when one is
 * configured. Without it, the learner can still claim a payment made another
 * way and the registrar confirms it.
 */
export function coursePriceCents(course: Course): number {
  return course.price.amountCents && course.price.amountCents > 0 ? course.price.amountCents : 0;
}

export function requiresPayment(course: Course): boolean {
  // Only a one-off price is something the app can settle. A plan-gated course
  // (price.plan set, no amount) belongs to a subscription the school sells
  // elsewhere and cannot be verified from a phone, so it stays open — gating it
  // would lock the whole catalog behind a manual confirmation.
  return coursePriceCents(course) > 0;
}

export function checkoutUrl(course: Course, reference: string): string | null {
  const template = (process.env.CHECKOUT_URL || "").trim();
  if (!template) return null;
  const amount = coursePriceCents(course);
  const filled = template
    .replaceAll("{reference}", encodeURIComponent(reference))
    .replaceAll("{amount}", String(amount))
    .replaceAll("{course}", encodeURIComponent(course.key))
    .replaceAll("{title}", encodeURIComponent(course.title));
  try {
    const url = new URL(filled);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

/** Quoted to the learner and used to match a payment to an enrollment. */
export function purchaseReference(course: Course): string {
  const random = Math.random().toString(36).slice(2, 7).toUpperCase();
  return `ATH-${course.code.replace(/[^A-Z0-9]/gi, "").toUpperCase().slice(0, 8)}-${random}`;
}

export function money(cents: number): string {
  return `$${(cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function accessOpen(access: string | undefined): boolean {
  return access === "open" || access === "paid" || access === "granted";
}
