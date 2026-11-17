import { getDb, logActivity, logAuthEvent, mutate, newId, nowIso } from "@/lib/store";
import { fail, ok, passwordProblem, preflight, text, validEmail } from "@/lib/mobile-api";
import { issueToken } from "@/lib/mobile-auth";
import { hashPassword } from "@/lib/staff";
import type { Learner } from "@/lib/types";

export const dynamic = "force-dynamic";

interface Body {
  name?: string;
  email?: string;
  password?: string;
  programId?: string | null;
}

/** Create a learner account. The app is the only place learners sign up. */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Body | null;
  const name = text(body?.name, 80);
  const email = text(body?.email, 200).toLowerCase();
  const password = typeof body?.password === "string" ? body.password : "";

  if (!name) return fail("Tell us your name.");
  if (!validEmail(email)) return fail("Enter a valid email address.");
  const problem = passwordProblem(password);
  if (problem) return fail(problem);

  const db = getDb();
  if (db.learners.some((learner) => learner.email.toLowerCase() === email)) {
    return fail("An account already uses that address. Sign in instead.", 409);
  }

  const programId =
    typeof body?.programId === "string" && db.programs.some((program) => program.id === body.programId)
      ? body.programId
      : null;

  const learner = await mutate((store) => {
    const created: Learner = {
      id: newId("lrn"),
      username: email,
      name,
      email,
      programId,
      enrolledAt: nowIso(),
      passwordHash: hashPassword(password),
      lastSeenAt: nowIso(),
    };
    store.learners.push(created);
    logAuthEvent(store, email, "success", "Created a learner account in the AthenIQ app.");
    logActivity(store, "learner.enrolled", `${name} created a learner account in the app.`, created.id);
    return created;
  });

  return ok(
    {
      token: issueToken({ sub: learner.id, role: "learner", name: learner.name, email: learner.email }),
      learner: { id: learner.id, name: learner.name, email: learner.email, programId: learner.programId },
    },
    201,
  );
}

export function OPTIONS() {
  return preflight();
}
