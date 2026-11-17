import { getDb, logAuthEvent, mutate, nowIso } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { issueToken } from "@/lib/mobile-auth";
import { verifyPassword } from "@/lib/staff";
import { consumeRecoveryCode, verifyTotp } from "@/lib/totp";
import type { Staff } from "@/lib/types";

export const dynamic = "force-dynamic";

interface Body {
  email?: string;
  password?: string;
  /** Authenticator code, or one of the eight recovery codes. */
  code?: string;
}

/**
 * Staff sign-in from the app.
 *
 * The console's browser session cannot be carried by a phone, so a registrar or
 * publisher signs in here and gets a 12-hour bearer token. The same two gates
 * apply: the account must be active, and an enrolled authenticator must produce
 * a code (or a recovery code) before the token is issued.
 */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Body | null;
  const email = text(body?.email, 200).toLowerCase();
  const password = typeof body?.password === "string" ? body.password : "";
  const code = text(body?.code, 20).replace(/\s/g, "");
  if (!email || !password) return fail("Enter your staff email and password.");

  const db = getDb();
  const staff = db.staff.find(
    (member) => !member.disabled && member.email.toLowerCase() === email,
  );
  if (!staff || !verifyPassword(password, staff.passwordHash)) {
    await mutate((store) => {
      logAuthEvent(
        store,
        email,
        staff ? "invalid_password" : "unknown_account",
        staff ? "Password did not match the staff account." : "No active staff account uses that address.",
        "the app",
      );
    });
    return fail("That email and password do not match a staff account.", 401);
  }

  let usedRecovery = false;
  let remainingRecovery: string[] | null = null;
  if (staff.totp.enabled) {
    if (!code) {
      return fail("Enter the code from your authenticator app.", 401, { needsCode: true });
    }
    const totpOk = staff.totp.secret ? verifyTotp(staff.totp.secret, code) : false;
    if (!totpOk) {
      const recovery = consumeRecoveryCode(staff.totp.recoveryCodes, code);
      if (!recovery.ok) {
        await mutate((store) => {
          logAuthEvent(store, email, "totp_failed", "Rejected authenticator code from the app.", "the app");
        });
        return fail("That code is not valid. Check the app, or use a recovery code.", 401, {
          needsCode: true,
        });
      }
      usedRecovery = true;
      // A recovery code is single-use, so the record keeps the reduced set.
      remainingRecovery = recovery.remaining;
    }
  }

  const identity = await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id) as Staff | undefined;
    if (record) {
      record.lastLoginAt = nowIso();
      if (remainingRecovery) record.totp.recoveryCodes = remainingRecovery;
    }
    logAuthEvent(
      store,
      email,
      usedRecovery ? "recovery_used" : "success",
      usedRecovery ? "Signed in to the app with a recovery code." : "Signed in to the app.",
      "the app",
    );
    return {
      token: issueToken({
        sub: staff.id,
        role: "staff",
        name: staff.name,
        email: staff.email,
        staffRole: staff.role,
      }),
      staff: { id: staff.id, name: staff.name, email: staff.email, role: staff.role, title: staff.title },
    };
  });

  return ok(identity);
}

export function OPTIONS() {
  return preflight();
}
