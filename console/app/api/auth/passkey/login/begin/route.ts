import { cookies } from "next/headers";
import { ok } from "@/lib/api";
import { getDb } from "@/lib/store";
import { COOKIE_TTL_SECONDS, PASSKEY_COOKIE, challengeCookie, newChallenge, relyingParty } from "@/lib/webauthn";

export const dynamic = "force-dynamic";

/**
 * Discoverable-credential sign-in: no email needed, the authenticator picks the
 * account and returns its user handle, which the finish step resolves.
 */
export async function POST(request: Request) {
  const db = getDb();
  const rp = relyingParty(request, db.settings.brand.siteName);
  const challenge = newChallenge();

  const jar = await cookies();
  jar.set(PASSKEY_COOKIE, challengeCookie(challenge), {
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
  });
}
