import { getDb, logAuthEvent, mutate, nowIso } from "@/lib/store";
import { fail, ok, preflight, text } from "@/lib/mobile-api";
import { issueToken } from "@/lib/mobile-auth";
import { verifyPassword } from "@/lib/staff";

export const dynamic = "force-dynamic";

interface Body {
  email?: string;
  password?: string;
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Body | null;
  const email = text(body?.email, 200).toLowerCase();
  const password = typeof body?.password === "string" ? body.password : "";
  if (!email || !password) return fail("Enter your email and password.");

  const db = getDb();
  const learner = db.learners.find(
    (record) => record.email.toLowerCase() === email && Boolean(record.passwordHash),
  );
  if (!learner || !learner.passwordHash || !verifyPassword(password, learner.passwordHash)) {
    await mutate((store) => {
      logAuthEvent(
        store,
        email,
        learner ? "invalid_password" : "unknown_account",
        learner ? "Password did not match the learner account." : "No learner account uses that address.",
        "the app",
      );
    });
    return fail("That email and password do not match an account.", 401);
  }

  await mutate((store) => {
    const record = store.learners.find((item) => item.id === learner.id);
    if (record) record.lastSeenAt = nowIso();
    logAuthEvent(store, email, "success", "Signed in to the AthenIQ app.", "the app");
  });

  return ok({
    token: issueToken({ sub: learner.id, role: "learner", name: learner.name, email: learner.email }),
    learner: {
      id: learner.id,
      name: learner.name,
      email: learner.email,
      programId: learner.programId,
    },
  });
}

export function OPTIONS() {
  return preflight();
}
