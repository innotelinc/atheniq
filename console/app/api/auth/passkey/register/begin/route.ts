import { cookies } from "next/headers";
import { fail, ok } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { getDb } from "@/lib/store";
import { COOKIE_TTL_SECONDS, PASSKEY_COOKIE, challengeCookie, newChallenge, relyingParty } from "@/lib/webauthn";

export const dynamic = "force-dynamic";

/** Registration options for the signed-in staff member's own assistant. */
export async function POST(request: Request) {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in before adding a passkey.", 401);

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
    rp: { id: rp.rpId, name: rp.name },
    user: {
      id: Buffer.from(staff.id).toString("base64url"),
      name: staff.email,
      displayName: staff.name,
    },
    pubKeyCredParams: [
      { type: "public-key", alg: -7 },
      { type: "public-key", alg: -257 },
    ],
    timeout: 120_000,
    attestation: "none",
    authenticatorSelection: {
      residentKey: "preferred",
      userVerification: "preferred",
    },
    excludeCredentials: (staff.passkeys ?? []).map((passkey) => ({
      type: "public-key",
      id: passkey.credentialId,
      transports: passkey.transports,
    })),
  });
}
