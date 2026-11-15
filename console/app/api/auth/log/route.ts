import { currentStaff } from "@/lib/current-staff";
import { can } from "@/lib/staff-policy";
import { fail, ok } from "@/lib/api";
import { getDb, logActivity, mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * Clear the sign-in log once a registrar has read it. The entries are capped and
 * rot on their own; this exists for the case where someone wants a clean slate
 * after investigating, and it records *that* clearing in the activity trail so
 * the act itself is not invisible.
 */
export async function DELETE() {
  const me = await currentStaff();
  if (process.env.AUTH_PASSWORD && !can(me?.role, "staff")) {
    return fail("Only a registrar can clear the sign-in log.", 403);
  }

  const cleared = await mutate((store) => {
    const count = store.authLog.length;
    store.authLog = [];
    logActivity(
      store,
      "settings.updated",
      `Cleared ${count} sign-in log ${count === 1 ? "entry" : "entries"}`,
      "",
      me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null,
    );
    return count;
  });

  return ok({ cleared, remaining: getDb().authLog.length });
}
