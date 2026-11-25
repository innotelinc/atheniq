import { NextResponse } from "next/server";
import { allowed, currentActor } from "@/lib/current-staff";
import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import type { ActorRef } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * The same three decisions the app's registrar route makes — confirm, grant,
 * decline — from the console, so a registrar working at a desk is not second
 * class to one holding a phone. Card payments arrive through the Stripe webhook
 * instead; both paths end at the same purchase row and the same access change.
 */
export async function POST(request: Request) {
  const origin = new URL(request.url).origin;
  const toList = (note: string) =>
    NextResponse.redirect(new URL(`/students?note=${encodeURIComponent(note)}`, origin), 303);

  if (!(await allowed("award"))) return toList("Only a registrar can decide a payment.");

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return toList("That decision could not be read.");
  }
  const purchaseId = String(form.get("purchaseId") ?? "").trim();
  const action = String(form.get("action") ?? "confirm").trim();
  const back = String(form.get("back") ?? "").trim();

  if (!purchaseId) return toList("That request did not name a purchase.");
  if (!["confirm", "grant", "decline"].includes(action)) {
    return toList("That action is not one of confirm, grant or decline.");
  }

  const db = getDb();
  const existing = db.purchases.find((item) => item.id === purchaseId);
  if (!existing) return toList("That purchase no longer exists.");
  // Where to land after the decision: the learner's page when it came from one.
  const destination = back.startsWith("/students/") ? back : "/students";
  const respond = (note: string) =>
    NextResponse.redirect(new URL(`${destination}?note=${encodeURIComponent(note)}`, origin), 303);

  const actor = (await currentActor()) as ActorRef | null;
  const decidedBy = actor?.email ?? "console";
  const name = actor?.name ?? "The console";

  const result = await mutate((store) => {
    const row = store.purchases.find((item) => item.id === purchaseId);
    if (!row) return null;
    const enrollment =
      store.enrollments.find((item) => item.purchaseId === row.id) ??
      store.enrollments.find(
        (item) => item.learnerId === row.learnerId && item.courseId === row.courseId,
      );
    const learner = store.learners.find((item) => item.id === row.learnerId);
    const at = nowIso();

    if (action === "decline") {
      row.status = "declined";
      row.decidedAt = at;
      row.decidedBy = decidedBy;
      if (enrollment) enrollment.access = "pending_payment";
      logActivity(
        store,
        "course.purchased",
        `${name} declined the payment claim ${row.reference} for ${learner?.name ?? "a learner"}.`,
        row.courseKey,
        actor,
      );
      return { reference: row.reference, learnerName: learner?.name ?? "the learner" };
    }

    row.status = "confirmed";
    row.decidedAt = at;
    row.decidedBy = decidedBy;
    row.granted = action === "grant";
    if (enrollment) {
      enrollment.access = row.granted ? "granted" : "paid";
      enrollment.purchaseId = row.id;
    }
    logActivity(
      store,
      "course.purchased",
      row.granted
        ? `${name} granted ${learner?.name ?? "a learner"} access to ${row.courseKey}.`
        : `${name} confirmed payment ${row.reference} for ${learner?.name ?? "a learner"} in ${row.courseKey}.`,
      row.courseKey,
      actor,
    );
    return { reference: row.reference, learnerName: learner?.name ?? "the learner" };
  });

  if (!result) return respond("That purchase disappeared while you were deciding.");
  const verb = action === "decline" ? "Declined" : action === "grant" ? "Granted access for" : "Confirmed";
  return respond(`${verb} ${result.reference} — ${result.learnerName}.`);
}
