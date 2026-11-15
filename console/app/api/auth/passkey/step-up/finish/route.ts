import { cookies } from "next/headers";
import { fail, ok } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { getDb, mutate, nowIso } from "@/lib/store";
import {
  STEP_UP_COOKIE,
  issueStepUpTicket,
  readChallengeCookie,
  relyingParty,
  verifyAssertion,
  type AssertionResponse,
} from "@/lib/webauthn";

export const dynamic = "force-dynamic";

/**
 * Verify a passkey assertion for a destructive action and hand back a
 * two-minute ticket the action can present instead of an authenticator code.
 * The credential must belong to the signed-in account — there is no fallback,
 * because this ceremony is not a sign-in.
 */
export async function POST(request: Request) {
  const staff = await currentStaff();
  if (!staff) return fail("Sign in again before confirming with a passkey.", 401);

  const body = (await request.json().catch(() => null)) as
    | {
        response?: {
          id?: string;
          clientDataJSON?: string;
          authenticatorData?: string;
          signature?: string;
          userHandle?: string | null;
        };
      }
    | null;
  const response = body?.response;
  if (!response?.id || !response.clientDataJSON || !response.authenticatorData || !response.signature) {
    return fail("The browser did not return a passkey assertion.");
  }

  const jar = await cookies();
  const challenge = readChallengeCookie(jar.get(STEP_UP_COOKIE)?.value);
  if (!challenge) return fail("That passkey confirmation expired. Start again.", 401);
  // The challenge is spent either way: a retry has to begin a new ceremony.
  jar.delete(STEP_UP_COOKIE);

  const db = getDb();
  const rp = relyingParty(request, db.settings.brand.siteName);
  const passkey = (staff.passkeys ?? []).find((entry) => entry.credentialId === response.id);
  if (!passkey) return fail("That passkey is not registered to this account.", 401);

  let signCount: number;
  try {
    ({ signCount } = verifyAssertion(response as AssertionResponse, challenge, rp, passkey));
  } catch (error) {
    return fail(error instanceof Error ? error.message : "That passkey could not be verified.", 401);
  }

  await mutate((store) => {
    const record = store.staff.find((member) => member.id === staff.id);
    const stored = record?.passkeys?.find((entry) => entry.credentialId === passkey.credentialId);
    if (stored) {
      stored.signCount = Math.max(stored.signCount, signCount);
      stored.lastUsedAt = nowIso();
    }
  });

  return ok({ ticket: issueStepUpTicket(staff.id), expiresIn: 120 });
}
