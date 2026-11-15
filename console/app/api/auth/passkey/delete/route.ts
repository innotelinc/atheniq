import { fail, ok, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { logActivity, mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

/** Remove one of your own passkeys; someone else's needs a registrar. */
export async function POST(request: Request) {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in first.", 401);
  const body = (await request.json().catch(() => null)) as { id?: string } | null;
  const id = str(body?.id);
  if (!id) return fail("Which passkey?");

  const removed = await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id);
    if (!record) return false;
    const before = record.passkeys?.length ?? 0;
    record.passkeys = (record.passkeys ?? []).filter((passkey) => passkey.id !== id);
    const changed = (record.passkeys?.length ?? 0) < before;
    if (changed) logActivity(store, "settings.updated", `Removed a passkey for ${record.name}`, record.id);
    return changed;
  });

  return removed ? ok({ removed: id }) : fail("That passkey is not on your account.", 404);
}
