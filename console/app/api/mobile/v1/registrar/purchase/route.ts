import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { sendPush } from "@/lib/mobile-push";
import type { ActorRef } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Confirm a payment, grant a place, or decline the claim.
 *
 * Confirming opens the course the learner already started; granting does the
 * same for a plan-gated course with no card payment at all. Both leave the
 * decision on the activity trail with who made it.
 */
export async function POST(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in with a staff account.", 401);
  if (identity.role !== "staff" || identity.staffRole !== "registrar") {
    return fail("Only a registrar can confirm payments.", 403);
  }

  const body = (await request.json().catch(() => null)) as {
    purchaseId?: string;
    action?: string;
  } | null;
  const purchaseId = text(body?.purchaseId, 120);
  const action = text(body?.action, 20) || "confirm";
  if (!purchaseId) return fail("Choose a purchase.");
  if (!["confirm", "grant", "decline"].includes(action)) return fail("That action is not one of confirm, grant or decline.");

  const db = getDb();
  const staff = db.staff.find((member) => member.id === identity.sub);
  if (!staff || staff.disabled) return fail("That staff account is no longer active.", 401);
  const purchase = db.purchases.find((item) => item.id === purchaseId);
  if (!purchase) return fail("That purchase does not exist.", 404);

  const actor: ActorRef = { id: staff.id, name: staff.name, email: staff.email, role: staff.role };

  const result = await mutate((store) => {
    const row = store.purchases.find((item) => item.id === purchaseId);
    if (!row) return null;
    const enrollment = store.enrollments.find((item) => item.purchaseId === row.id);
    const learner = store.learners.find((item) => item.id === row.learnerId);
    const at = nowIso();

    if (action === "decline") {
      row.status = "declined";
      row.decidedAt = at;
      row.decidedBy = actor.email;
      if (enrollment) enrollment.access = "pending_payment";
      logActivity(
        store,
        "course.purchased",
        `${actor.name} declined the payment claim ${row.reference} for ${learner?.name ?? "a learner"}.`,
        row.courseKey,
        actor,
      );
      return {
        status: row.status,
        reference: row.reference,
        courseKey: row.courseKey,
        learnerId: row.learnerId,
        learnerName: learner?.name ?? "",
      };
    }

    row.status = "confirmed";
    row.decidedAt = at;
    row.decidedBy = actor.email;
    row.granted = action === "grant";
    if (enrollment) enrollment.access = row.granted ? "granted" : "paid";
    logActivity(
      store,
      "course.purchased",
      row.granted
        ? `${actor.name} granted ${learner?.name ?? "a learner"} access to ${row.courseKey} from the app.`
        : `${actor.name} confirmed payment ${row.reference} for ${row.courseKey} from the app.`,
      row.courseKey,
      actor,
    );
    return {
      status: row.status,
      reference: row.reference,
      learnerId: row.learnerId,
      learnerName: learner?.name ?? "",
      courseKey: row.courseKey,
    };
  });

  if (!result) return fail("That purchase disappeared.", 409);

  if (action !== "decline" && "learnerId" in result) {
    const learner = getDb().learners.find((item) => item.id === result.learnerId);
    if (learner?.pushToken) {
      const push = await sendPush([
        {
          to: learner.pushToken,
          title: "You are enrolled",
          body: `${result.courseKey.split("+")[1] ?? "Your course"} is open. Pick up where you left off.`,
          data: { tab: "learning" },
        },
      ]);
      if (push.rejected.length) {
        await mutate((store) => {
          const row = store.learners.find((item) => item.id === learner.id);
          if (row) row.pushToken = null;
        });
      }
    }
  }

  return ok(result);
}

export function OPTIONS() {
  return preflight();
}
