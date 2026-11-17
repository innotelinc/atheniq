import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";
import { sendPush } from "@/lib/mobile-push";
import type { ActorRef } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Issue a certificate the app queued when a learner finished a course.
 *
 * The console renders and submits to Signara; this marks the award issued so the
 * registrar can close the loop from a phone. A publisher cannot award — the same
 * rule the console enforces in its route handlers.
 */
export async function POST(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in with a staff account.", 401);
  if (identity.role !== "staff" || identity.staffRole !== "registrar") {
    return fail("Only a registrar can issue credentials.", 403);
  }

  const body = (await request.json().catch(() => null)) as { credentialId?: string } | null;
  const credentialId = text(body?.credentialId, 120);
  if (!credentialId) return fail("Choose a credential.");

  const db = getDb();
  const staff = db.staff.find((member) => member.id === identity.sub);
  if (!staff || staff.disabled) return fail("That staff account is no longer active.", 401);

  const credential = db.credentials.find((item) => item.id === credentialId);
  if (!credential) return fail("That credential does not exist.", 404);
  if (credential.status === "revoked") return fail("That credential was revoked.", 409);
  if (credential.status === "issued") return ok({ credentialId, status: "issued", alreadyIssued: true });

  const actor: ActorRef = { id: staff.id, name: staff.name, email: staff.email, role: staff.role };
  const result = await mutate((store) => {
    const row = store.credentials.find((item) => item.id === credentialId);
    if (!row) return null;
    const at = nowIso();
    row.status = "issued";
    row.issuedAt = at;
    row.updatedAt = at;
    row.timeline.push({ at, label: `Issued by ${actor.name} from the AthenIQ app` });
    logActivity(
      store,
      "credential.issued",
      `${actor.name} issued ${row.subjectLabel} for ${row.learner.name} from the app.`,
      row.id,
      actor,
    );
    return { credentialId: row.id, status: row.status, issuedAt: row.issuedAt, verifyId: row.verifyId };
  });

  if (!result) return fail("That credential disappeared.", 409);

  // Tell the learner their certificate is ready; a push failure never undoes the award.
  const learner = db.learners.find(
    (item) => item.email.toLowerCase() === credential.learner.email.toLowerCase(),
  );
  if (learner?.pushToken) {
    const push = await sendPush([
      {
        to: learner.pushToken,
        title: "Certificate issued",
        body: `${credential.subjectLabel} is now issued. Verification ${credential.verifyId}.`,
        data: { tab: "learning", verifyId: credential.verifyId },
      },
    ]);
    if (push.rejected.length) {
      await mutate((store) => {
        const row = store.learners.find((item) => item.id === learner.id);
        if (row) row.pushToken = null;
      });
    }
  }

  return ok(result);
}

export function OPTIONS() {
  return preflight();
}
