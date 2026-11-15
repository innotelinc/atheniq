import { fail, ok, readBody, str } from "@/lib/api";
import { currentSessionId, currentStaff } from "@/lib/current-staff";
import { liveSessions, revokeSessions, revokeStaffSessions } from "@/lib/login-sessions";
import { SESSION_COOKIE } from "@/lib/session";
import { can } from "@/lib/staff-policy";
import { confirmDestructiveAction, hasSecondFactor } from "@/lib/step-up";
import { cookies } from "next/headers";
import { getDb, logActivity, mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * End one live session, every session a person holds, or every session on the
 * console. Registrars only: an ended session stops resolving an account on the
 * next request, even though middleware still accepts the signed cookie. The
 * activity trail records the act, so a mass sign-out is never silent.
 *
 * Ending anything other than your own session asks for a fresh authenticator
 * code first, so a borrowed browser cannot throw everyone else out.
 */
export async function POST(request: Request) {
  const me = await currentStaff();
  if (process.env.AUTH_PASSWORD && !can(me?.role, "staff")) {
    return fail("Only a registrar can end a session.", 403);
  }

  const body = await readBody<{ scope?: string; id?: string; staffId?: string; code?: string; stepUp?: string }>(
    request,
  );
  const scope =
    body?.scope === "all" ? "all" : body?.scope === "session" ? "session" : body?.scope === "staff" ? "staff" : null;
  const id = typeof body?.id === "string" ? body.id.trim() : "";
  const staffId = typeof body?.staffId === "string" ? body.staffId.trim() : "";
  if (!scope) return fail("Say whether to end one session, a person's sessions or every session.");
  if (scope === "session" && !id) return fail("Name the session to end.");
  if (scope === "staff" && !staffId) return fail("Name the person whose sessions should end.");

  // Whose session would this end? Everything except your own needs a fresh code.
  const targetStaffId =
    scope === "staff"
      ? staffId
      : scope === "session"
        ? (liveSessions(getDb()).find((entry) => entry.id === id)?.staffId ?? null)
        : null;
  const foreign = scope === "all" || (targetStaffId !== null && targetStaffId !== me?.id);
  if (me && foreign && hasSecondFactor(me)) {
    const problem = await confirmDestructiveAction(me, body, {
      missing: "Enter an authenticator code or use a passkey to end sessions other than your own.",
      wrong: "That confirmation is not right. No session was ended.",
    });
    if (problem) return fail(problem, 401);
  }

  const actor = me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null;
  const mine = await currentSessionId();
  const ended = await mutate((store) => {
    if (scope === "staff") {
      const person = store.staff.find((member) => member.id === staffId);
      const count = revokeStaffSessions(store, staffId, { reason: "ended_by_registrar", actor });
      if (count === 0) return null;
      logActivity(
        store,
        "settings.updated",
        `Signed out every session for ${person?.name ?? "a former staff member"} (${count})`,
        staffId,
        actor,
      );
      return count;
    }

    const target = scope === "session" ? liveSessions(store).find((entry) => entry.id === id) : null;
    if (scope === "session" && !target) return null;
    const count = revokeSessions(store, scope === "session" ? id : undefined, {
      reason: scope === "all" ? "signed_out_everywhere" : "ended_by_registrar",
      actor,
    });
    const person = target ? store.staff.find((member) => member.id === target.staffId) : null;
    logActivity(
      store,
      "settings.updated",
      scope === "all"
        ? `Signed out every live session (${count})`
        : `Signed out a session for ${person?.name ?? "a former staff member"}`,
      target?.id ?? "",
      actor,
    );
    return count;
  });

  if (ended === null) {
    return fail(scope === "staff" ? "That person has no live session." : "That session had already ended.", 404);
  }
  // If this browser's own session went with it, drop the cookie too, so the
  // person lands on the sign-in page instead of a console shell that refuses them.
  const signedSelfOut =
    scope === "all" || (scope === "session" && id === mine) || (scope === "staff" && staffId === me?.id);
  if (signedSelfOut) (await cookies()).delete(SESSION_COOKIE);
  return ok({ ended, live: liveSessions(getDb()).length });
}
