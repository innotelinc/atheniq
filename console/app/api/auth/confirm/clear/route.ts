import { cookies } from "next/headers";
import { fail, ok } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { CONFIRM_COOKIE } from "@/lib/step-up";
import { logActivity, mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * Forget the remembered confirmation now instead of waiting for it to lapse.
 * Ending it early only makes the console ask again, so there is nothing extra to
 * authorize beyond being signed in; the act still goes on the trail, because it
 * shortens how long this browser can make access changes without a fresh code.
 */
export async function POST() {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in first.", 401);

  const jar = await cookies();
  const remembered = Boolean(jar.get(CONFIRM_COOKIE)?.value);
  jar.delete(CONFIRM_COOKIE);

  if (remembered) {
    await mutate((store) =>
      logActivity(store, "settings.updated", "Cleared the remembered confirmation", staff.id, {
        id: staff.id,
        name: staff.name,
        email: staff.email,
        role: staff.role,
      }),
    );
  }

  return ok({ cleared: remembered });
}
