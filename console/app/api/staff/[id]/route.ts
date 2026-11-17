import { cookies } from "next/headers";
import { notifyAccessChange } from "@/lib/alerts";
import { fail, ok, readBody, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { revokeStaffSessions } from "@/lib/login-sessions";
import { SESSION_COOKIE } from "@/lib/session";
import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import { emptyTotp, hashPassword } from "@/lib/staff";
import { can, coerceRole } from "@/lib/staff-policy";
import { confirmDestructiveAction, hasSecondFactor } from "@/lib/step-up";
import { publicVault } from "@/lib/vaultwarden";
import type { Staff } from "@/lib/types";

export const dynamic = "force-dynamic";

function publicStaff(member: Staff) {
  const { passwordHash, ...rest } = member;
  return { ...rest, vault: publicVault(member.vault) };
}

function activeRegistrars(staff: Staff[]): Staff[] {
  return staff.filter((member) => member.role === "registrar" && !member.disabled);
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const me = await currentStaff();
  if (process.env.AUTH_PASSWORD && !can(me?.role, "staff")) {
    return fail("Only a registrar can manage staff accounts.", 403);
  }

  const body = (await request.json().catch(() => null)) as {
    name?: string;
    title?: string;
    role?: string;
    password?: string;
    disabled?: boolean;
    reset2fa?: boolean;
    /** Drop every passkey on the account, forcing a fresh enrollment. */
    revokePasskeys?: boolean;
    /** Fresh authenticator code, when the acting registrar has one enrolled. */
    code?: string;
    /** Ticket from a passkey confirmation, as an alternative to the code. */
    stepUp?: string;
  } | null;
  if (!body) return fail("Invalid body.");

  const target = getDb().staff.find((member) => member.id === id);
  if (!target) return fail("That account does not exist.", 404);
  const wasDisabled = Boolean(target.disabled);

  const nextRole = body.role === undefined ? target.role : coerceRole(body.role);
  const nextDisabled = body.disabled === undefined ? target.disabled : Boolean(body.disabled);

  // Never let the console lose its last way in.
  const removingRegistrar =
    target.role === "registrar" && !target.disabled && (nextRole !== "registrar" || nextDisabled);
  if (removingRegistrar && activeRegistrars(getDb().staff).length <= 1) {
    return fail("This is the last active registrar — add another before changing this one.", 409);
  }
  if (me && me.id === id && nextDisabled) {
    return fail("You cannot disable the account you are signed in with.", 409);
  }
  if (body.password !== undefined && str(body.password).length < 10) {
    return fail("Use a password of at least 10 characters.");
  }

  // Taking someone's access away — or resetting the factor that protects it — is
  // the kind of change a borrowed browser should not be able to make, so it needs
  // a fresh code or a passkey confirmation. Turning access back on does not.
  const needsStepUp =
    body.reset2fa === true || body.revokePasskeys === true || (body.disabled === true && !wasDisabled);
  if (me && needsStepUp && hasSecondFactor(me)) {
    const problem = await confirmDestructiveAction(me, body, {
      missing: "Enter an authenticator code or use a passkey to disable an account or reset its second factor.",
      wrong: "That confirmation is not right. Nothing was changed.",
    });
    if (problem) return fail(problem, 401);
  }

  const updated = await mutate((db) => {
    const record = db.staff.find((member) => member.id === id) as Staff;
    if (body.name !== undefined) record.name = str(body.name) || record.name;
    if (body.title !== undefined) record.title = str(body.title) || record.title;
    record.role = nextRole;
    record.disabled = nextDisabled;
    if (body.password !== undefined) record.passwordHash = hashPassword(str(body.password));
    if (body.reset2fa) {
      record.totp = emptyTotp();
      logActivity(db, "settings.updated", `Reset two-factor for ${record.name}`, record.id);
    }
    if (body.revokePasskeys) {
      const removed = record.passkeys?.length ?? 0;
      record.passkeys = [];
      logActivity(
        db,
        "settings.updated",
        `Revoked ${removed} passkey(s) for ${record.name}`,
        record.id,
      );
    }
    logActivity(
      db,
      "settings.updated",
      `Updated ${record.name} (${record.role}${record.disabled ? ", disabled" : ""})`,
      record.id,
    );

    // A disabled account and a reset second factor both mean "this person is not
    // who they were when they signed in", so no session they hold survives either.
    let ended = 0;
    if (nextDisabled || body.reset2fa || body.revokePasskeys) {
      ended = revokeStaffSessions(db, record.id, {
        reason: "access_change",
        actor: me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null,
      });
      if (ended > 0) {
        logActivity(db, "settings.updated", `Ended every live session for ${record.name} (${ended})`, record.id);
      }
    }
    return { record, ended };
  });

  // A registrar should hear about access changes even if they were watching.
  const changed = { name: updated.record.name, email: updated.record.email };
  if (nextDisabled && !wasDisabled) {
    notifyAccessChange(changed, "Account disabled", me, updated.ended);
  }
  if (body.reset2fa) {
    notifyAccessChange(changed, "Two-factor reset", me, updated.ended);
  }
  if (body.revokePasskeys) {
    notifyAccessChange(changed, "Passkeys revoked", me, updated.ended);
  }

  // Resetting your own factor or passkeys ends your own session too; drop the
  // cookie so the browser goes to the sign-in page instead of a console that
  // refuses it.
  if (me?.id === id && updated.ended > 0) {
    (await cookies()).delete(SESSION_COOKIE);
  }

  return ok({ ...publicStaff(updated.record), sessionsEnded: updated.ended });
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await readBody<{ code?: string; stepUp?: string }>(request);
  const me = await currentStaff();
  if (process.env.AUTH_PASSWORD && !can(me?.role, "staff")) {
    return fail("Only a registrar can manage staff accounts.", 403);
  }
  if (me?.id === id) return fail("You cannot remove the account you are signed in with.", 409);

  const target = getDb().staff.find((member) => member.id === id);
  if (!target) return fail("That account does not exist.", 404);
  if (target.role === "registrar" && !target.disabled && activeRegistrars(getDb().staff).length <= 1) {
    return fail("This is the last active registrar — add another before removing this one.", 409);
  }

  // Removal cannot be undone from the console, so it needs a fresh code or a
  // passkey confirmation when the acting registrar has a second factor.
  if (me && hasSecondFactor(me)) {
    const problem = await confirmDestructiveAction(me, body, {
      missing: "Enter an authenticator code or use a passkey to remove an account.",
      wrong: "That confirmation is not right. Nothing was removed.",
    });
    if (problem) return fail(problem, 401);
  }

  const removed = await mutate((db) => {
    const index = db.staff.findIndex((member) => member.id === id);
    if (index < 0) return null;
    // End their sessions first: the account is gone, so nothing it opened stays live.
    const ended = revokeStaffSessions(db, id, {
      reason: "access_change",
      actor: me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null,
    });
    const [record] = db.staff.splice(index, 1);
    logActivity(
      db,
      "settings.updated",
      `Removed ${record.name} from the console${ended ? ` and ended ${ended} live session(s)` : ""}`,
      record.id,
    );
    return { record, ended };
  });

  if (removed) {
    notifyAccessChange(
      { name: removed.record.name, email: removed.record.email },
      "Account removed",
      me,
      removed.ended,
    );
  }

  return ok({ removed: removed?.record.id ?? id, at: nowIso() });
}
