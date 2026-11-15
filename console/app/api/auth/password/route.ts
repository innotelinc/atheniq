import { fail, ok, str } from "@/lib/api";
import { currentSessionId, currentStaff } from "@/lib/current-staff";
import { liveSessions, revokeSessions } from "@/lib/login-sessions";
import { actorRef, hashPassword, verifyPassword } from "@/lib/staff";
import { getDb, logActivity, mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * Change your own console password.
 *
 * The signed-in person proves the old password first, so a borrowed session
 * cannot lock them out of their own account. Every other session they hold is
 * ended — a password change is how you evict a device you no longer trust — but
 * the one making the change stays signed in.
 */
export async function POST(request: Request) {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in before changing your password.", 401);

  const body = (await request.json().catch(() => null)) as { current?: string; next?: string } | null;
  const current = str(body?.current);
  const next = str(body?.next);

  if (!current) return fail("Enter your current password.");
  if (!verifyPassword(current, staff.passwordHash)) {
    return fail("That is not your current password.", 400);
  }
  if (next.length < 10) return fail("Use a password of at least 10 characters.", 400);
  if (next === current) return fail("That is the password you already have.", 400);

  const sid = await currentSessionId();
  const ended = await mutate((db) => {
    const record = db.staff.find((member) => member.id === staff.id);
    if (!record) return 0;
    record.passwordHash = hashPassword(next);
    logActivity(db, "settings.updated", `${record.name} changed their own password`, record.id, actorRef(record));

    let count = 0;
    for (const entry of liveSessions(db)) {
      if (entry.staffId === staff.id && entry.id !== sid) {
        count += revokeSessions(db, entry.id, { reason: "access_change", actor: actorRef(record) });
      }
    }
    return count;
  });

  if (getDb().staff.every((member) => member.id !== staff.id)) {
    return fail("That account no longer exists.", 404);
  }

  return ok({ changed: true, sessionsEnded: ended });
}
