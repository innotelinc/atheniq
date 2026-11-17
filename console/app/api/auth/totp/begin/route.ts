import { cookies } from "next/headers";
import { fail, ok } from "@/lib/api";
import { CHALLENGE_COOKIE, readLoginChallenge } from "@/lib/session";
import { getDb, mutate } from "@/lib/store";
import { generateTotpSecret, otpauthUri } from "@/lib/totp";

export const dynamic = "force-dynamic";

/**
 * Start enrollment: mint a secret for the account that passed the password step
 * and hand back its otpauth URI. The secret is stored but stays disabled until
 * a code from the authenticator confirms it, so a half-finished setup never
 * locks anyone out.
 */
export async function POST() {
  const jar = await cookies();
  const challenge = await readLoginChallenge(jar.get(CHALLENGE_COOKIE)?.value);
  if (!challenge) return fail("That sign-in attempt expired. Sign in again.", 401);

  const db = getDb();
  const staff = db.staff.find((member) => member.id === challenge.staffId && !member.disabled);
  if (!staff) return fail("That account cannot sign in.", 403);
  if (staff.totp?.enabled) return fail("Two-factor is already set up on this account.", 409);

  const secret = generateTotpSecret();
  await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id);
    if (record) record.totp = { secret, enabled: false, enrolledAt: null, recoveryCodes: [] };
  });

  return ok({
    secret,
    otpauthUri: otpauthUri(db.settings.brand.siteName, staff.email, secret),
    account: staff.email,
  });
}
