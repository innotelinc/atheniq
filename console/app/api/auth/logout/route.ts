import { cookies } from "next/headers";
import { ok } from "@/lib/api";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { revokeSession } from "@/lib/login-sessions";
import { mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function POST() {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  const session = await readSession(token);
  // Clearing the cookie is not enough: free the address's slot as well.
  if (session) await mutate((store) => revokeSession(store, session.sid, { reason: "signed_out" }));
  jar.delete(SESSION_COOKIE);
  return ok({ signedOut: true });
}
