import { cookies } from "next/headers";
import { fail, ok } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { getDb } from "@/lib/store";
import {
  COOKIE_TTL_SECONDS,
  STEP_UP_COOKIE,
  challengeCookie,
  newChallenge,
  relyingParty,
} from "@/lib/webauthn";

export const dynamic = "force-dynamic";

/**
 * Start a passkey confirmation for a destructive action. Only passkeys already
 * registered to the signed-in account are offered, and the challenge is bound
 * to this browser by a short-lived signed cookie.
 */
export async function POST(request: Request) {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in again before confirming with a passkey.", 401);

  const passkeys = staff.passkeys ?? [];
  if (passkeys.length === 0) {
    return fail("This account has no passkey — use an authenticator code instead.", 400);
  }

  const db = getDb();
  const rp = relyingParty(request, db.settings.brand.siteName);
  const challenge = newChallenge();

  const jar = await cookies();
  jar.set(STEP_UP_COOKIE, challengeCookie(challenge), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: COOKIE_TTL_SECONDS,
  });

  return ok({
    challenge,
    rpId: rp.rpId,
    timeout: 120_000,
    userVerification: "preferred",
    allowCredentials: passkeys.slice(0, 20).map((passkey) => ({
      id: passkey.credentialId,
      transports: passkey.transports ?? [],
    })),
  });
}
