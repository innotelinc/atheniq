import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * Card capture, without a Stripe SDK.
 *
 * The console had no card processing at all: a learner claims a payment and a
 * registrar confirms it. This adds the one thing that was missing — a way for
 * the learner to actually pay — and leaves the confirmation path intact: a
 * settled card payment arrives as a webhook and takes the same decision a
 * registrar would have taken.
 *
 * The SDK is one form POST and one HMAC, so it is not worth a dependency; a
 * price rise in `stripe` should not be able to break the school's billing.
 */

const API = "https://api.stripe.com/v1";

export function paymentsEnabled(): boolean {
  return Boolean((process.env.STRIPE_SECRET_KEY || "").trim());
}

export type CheckoutResult = { url: string } | { error: string };

export async function createCheckoutSession(input: {
  reference: string;
  purchaseId: string;
  courseKey: string;
  title: string;
  amountCents: number;
  email: string;
  successUrl: string;
  cancelUrl: string;
}): Promise<CheckoutResult> {
  const key = (process.env.STRIPE_SECRET_KEY || "").trim();
  if (!key) return { error: "Card payment is not set up yet." };
  if (input.amountCents <= 0) return { error: "That course has no price to charge." };

  const body = new URLSearchParams({
    mode: "payment",
    "line_items[0][quantity]": "1",
    "line_items[0][price_data][currency]": "usd",
    "line_items[0][price_data][unit_amount]": String(Math.round(input.amountCents)),
    "line_items[0][price_data][product_data][name]": input.title,
    client_reference_id: input.reference,
    "metadata[purchaseId]": input.purchaseId,
    "metadata[courseKey]": input.courseKey,
    customer_email: input.email,
    success_url: input.successUrl,
    cancel_url: input.cancelUrl,
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12_000);
  try {
    const response = await fetch(`${API}/checkout/sessions`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${key}`,
        "content-type": "application/x-www-form-urlencoded",
      },
      body,
      signal: controller.signal,
      cache: "no-store",
    });
    const payload = (await response.json().catch(() => null)) as
      | { url?: string; error?: { message?: string } }
      | null;
    if (!response.ok) {
      // The message is Stripe's own wording for a key or price problem; it
      // never contains the key itself.
      return { error: payload?.error?.message || `Stripe answered ${response.status}.` };
    }
    if (!payload?.url) return { error: "Stripe did not return a checkout link." };
    return { url: payload.url };
  } catch {
    return { error: "Stripe could not be reached." };
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Stripe signs `t.body` with the endpoint secret. Anything without a matching
 * v1 signature inside the tolerance window is refused, so a replayed or forged
 * event cannot open a course.
 */
export function verifyStripeSignature(
  payload: string,
  header: string | null,
  toleranceSeconds = 300,
): boolean {
  const secret = (process.env.STRIPE_WEBHOOK_SECRET || "").trim();
  if (!secret || !header) return false;

  const parts = header.split(",").map((part) => part.trim());
  const timestamp = parts.find((part) => part.startsWith("t="))?.slice(2);
  const signatures = parts.filter((part) => part.startsWith("v1=")).map((part) => part.slice(3));
  if (!timestamp || signatures.length === 0) return false;

  const age = Math.abs(Date.now() / 1000 - Number(timestamp));
  if (!Number.isFinite(age) || age > toleranceSeconds) return false;

  const expected = Buffer.from(
    createHmac("sha256", secret).update(`${timestamp}.${payload}`).digest("hex"),
    "utf8",
  );
  return signatures.some((signature) => {
    const given = Buffer.from(signature, "utf8");
    return given.length === expected.length && timingSafeEqual(given, expected);
  });
}
