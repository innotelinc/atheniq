import { fail, ok, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { can } from "@/lib/staff-policy";
import { getDb, logActivity, mutate } from "@/lib/store";
import { LOCK_WINDOW_MS } from "@/lib/throttle";

export const dynamic = "force-dynamic";

/**
 * Lift a pause after a registrar has looked at it. The refusals behind the lock
 * are removed (they are what the throttle counts), so the address or source can
 * try again immediately; the activity trail records that someone unlocked it.
 */
export async function POST(request: Request) {
  const me = await currentStaff();
  if (process.env.AUTH_PASSWORD && !can(me?.role, "staff")) {
    return fail("Only a registrar can unlock a sign-in.", 403);
  }

  const body = (await request.json().catch(() => null)) as { kind?: string; value?: string } | null;
  const kind = str(body?.kind);
  const value = str(body?.value).toLowerCase();
  if ((kind !== "email" && kind !== "source") || !value) {
    return fail("Name the address or source to unlock.");
  }

  const removed = await mutate((store) => {
    const cutoff = Date.now() - LOCK_WINDOW_MS;
    const before = store.authLog.length;
    store.authLog = store.authLog.filter((event) => {
      if (event.outcome === "success") return true;
      if (new Date(event.at).getTime() < cutoff) return true;
      const matches = kind === "email" ? event.email.toLowerCase() === value : (event.source ?? "").toLowerCase() === value;
      return !matches;
    });
    const count = before - store.authLog.length;
    logActivity(
      store,
      "settings.updated",
      `Unlocked ${kind === "email" ? "address" : "source"} ${value}`,
      "",
      me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null,
    );
    return count;
  });

  return ok({ unlocked: value, removed, remaining: getDb().authLog.length });
}
