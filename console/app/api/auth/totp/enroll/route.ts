import { fail, ok, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import { generateRecoveryCodes, generateTotpSecret, otpauthUri, verifyTotp } from "@/lib/totp";

export const dynamic = "force-dynamic";

/**
 * Enrolling an authenticator from a signed-in session.
 *
 * The login-time `/api/auth/totp/begin` route belongs to the password challenge
 * and only exists mid-sign-in, so an account that skipped enrolment could not
 * add a code afterwards. This is the same ceremony for someone already in:
 * POST without a code mints the secret, POST with a code enables it and returns
 * the recovery codes once.
 */
export async function POST(request: Request) {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in before enrolling an authenticator.", 401);
  if (staff.totp?.enabled) {
    return fail("An authenticator is already enrolled — a registrar can reset it.", 409);
  }

  const body = (await request.json().catch(() => null)) as { code?: string } | null;
  const code = str(body?.code).replace(/\s+/g, "");

  if (!code) {
    const secret = generateTotpSecret();
    await mutate((store) => {
      const record = store.staff.find((member) => member.id === staff.id);
      if (record) {
        record.totp = { secret, enabled: false, enrolledAt: null, recoveryCodes: [] };
      }
    });
    return ok({
      secret,
      otpauthUri: otpauthUri(getDb().settings.brand.siteName, staff.email, secret),
      account: staff.email,
    });
  }

  if (!staff.totp?.secret) return fail("Start the setup again.", 409);
  if (!verifyTotp(staff.totp.secret, code)) {
    return fail("That code is not right. Check the authenticator's clock and try the next one.", 400);
  }

  const generated = generateRecoveryCodes();
  await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id);
    if (!record) return;
    record.totp = {
      secret: staff.totp!.secret,
      enabled: true,
      enrolledAt: nowIso(),
      recoveryCodes: generated.hashes,
    };
    logActivity(store, "settings.updated", `Enabled two-factor for ${record.name}`, record.id);
  });

  return ok({ enabled: true, recoveryCodes: generated.plain });
}
