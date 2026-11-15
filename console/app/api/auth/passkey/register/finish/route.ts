import { cookies } from "next/headers";
import { fail, ok, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import { PASSKEY_COOKIE, readChallengeCookie, relyingParty, verifyRegistration } from "@/lib/webauthn";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in before adding a passkey.", 401);

  const body = (await request.json().catch(() => null)) as
    | { response?: { clientDataJSON?: string; attestationObject?: string; transports?: string[] }; label?: string }
    | null;
  const response = body?.response;
  if (!response?.clientDataJSON || !response.attestationObject) {
    return fail("The browser did not return a passkey.");
  }

  const jar = await cookies();
  const challenge = readChallengeCookie(jar.get(PASSKEY_COOKIE)?.value);
  if (!challenge) return fail("That passkey setup expired. Start again.", 401);

  const db = getDb();
  const rp = relyingParty(request, db.settings.brand.siteName);

  let verified;
  try {
    verified = verifyRegistration(
      {
        clientDataJSON: response.clientDataJSON,
        attestationObject: response.attestationObject,
        transports: Array.isArray(response.transports) ? response.transports : [],
      },
      challenge,
      rp,
    );
  } catch (error) {
    return fail(error instanceof Error ? error.message : "That passkey could not be verified.", 400);
  }

  const label = str(body?.label).slice(0, 60) || "Passkey";
  await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id);
    if (!record) return;
    if (!Array.isArray(record.passkeys)) record.passkeys = [];
    if (record.passkeys.some((passkey) => passkey.credentialId === verified.credentialId)) return;
    record.passkeys.push({
      id: newId("pkey"),
      credentialId: verified.credentialId,
      publicKey: verified.publicKey,
      algorithm: verified.algorithm,
      signCount: verified.signCount,
      label,
      transports: verified.transports,
      createdAt: nowIso(),
      lastUsedAt: null,
    });
    logActivity(store, "settings.updated", `Added a passkey for ${record.name}`, record.id);
  });

  jar.delete(PASSKEY_COOKIE);
  return ok({ credentialId: verified.credentialId, label });
}
