import { getDb, mutate } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { bearerIdentity } from "@/lib/mobile-auth";

export const dynamic = "force-dynamic";

/** Keep the device's Expo push token on the learner, so an award can reach them. */
export async function POST(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in.", 401);
  if (identity.role !== "learner") return fail("Push notifications are for learner accounts.", 403);

  const body = (await request.json().catch(() => null)) as { token?: string } | null;
  const token = text(body?.token, 200);
  if (!token) return fail("No push token was sent.");

  const db = getDb();
  const learner = db.learners.find((item) => item.id === identity.sub);
  if (!learner) return fail("That learner account no longer exists.", 401);

  await mutate((store) => {
    const row = store.learners.find((item) => item.id === learner.id);
    if (row) row.pushToken = token;
  });

  return ok({ registered: true });
}

/** Forget the token — used when someone turns notifications off. */
export async function DELETE(request: Request) {
  const identity = bearerIdentity(request);
  if (!identity) return fail("Sign in.", 401);
  await mutate((store) => {
    const row = store.learners.find((item) => item.id === identity.sub);
    if (row) row.pushToken = null;
  });
  return ok({ registered: false });
}

export function OPTIONS() {
  return preflight();
}
