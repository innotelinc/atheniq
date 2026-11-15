import { fail, ok, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { actorRef, verifyPassword } from "@/lib/staff";
import { can } from "@/lib/staff-policy";
import { getDb, logActivity, mutate } from "@/lib/store";
import { linkExistingVault, publicVault } from "@/lib/vaultwarden";
import type { Staff } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Repair a vault link.
 *
 * A link made before the console kept an API key cannot be checked, and an
 * account someone registered on the vault themselves was never linked. The
 * registrar enters that person's vault password here; it is used once to open
 * the account and mint a key, then dropped.
 */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const me = await currentStaff();
  if (process.env.AUTH_PASSWORD && !can(me?.role, "staff")) {
    return fail("Only a registrar can link a vault account.", 403);
  }

  const { id } = await params;
  const target = getDb().staff.find((member) => member.id === id);
  if (!target) return fail("That account does not exist.", 404);

  const body = (await request.json().catch(() => null)) as { password?: string } | null;
  const password = str(body?.password);
  if (password.length < 10) return fail("Enter the password for that vault account.");

  const result = await linkExistingVault(target.email, password);
  if (!result.ok || !result.vault) {
    return fail(result.error ?? "That vault account could not be linked.", 400);
  }

  // The registrar typed the vault password, so it can be compared with the
  // console login's hash instead of being assumed either way.
  const link = { ...result.vault, sharedPassword: verifyPassword(password, target.passwordHash) };
  const saved = await mutate((db) => {
    const record = db.staff.find((member) => member.id === id) as Staff;
    record.vault = link;
    logActivity(
      db,
      "settings.updated",
      `Re-linked the Vaultwarden account for ${record.name}`,
      record.id,
      me ? actorRef(me) : null,
    );
    return publicVault(link);
  });

  return ok({ vault: saved });
}
