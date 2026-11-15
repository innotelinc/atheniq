import { fail, ok, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import { actorRef, emptyTotp, hashPassword, verifyPassword } from "@/lib/staff";
import { describeDomains, emailAllowed } from "@/lib/email-policy";
import { ROLE_DESCRIPTIONS, can, coerceRole } from "@/lib/staff-policy";
import { provisionVault, publicVault, vaultPassword } from "@/lib/vaultwarden";
import type { Staff } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Neither the password hash nor the vault API key ever leaves the server. */
function publicStaff(member: Staff) {
  const { passwordHash, ...rest } = member;
  return { ...rest, vault: publicVault(member.vault) };
}

async function guard() {
  if (!process.env.AUTH_PASSWORD) return null;
  const me = await currentStaff();
  return can(me?.role, "staff") ? me : null;
}

export async function GET() {
  if (process.env.AUTH_PASSWORD && !(await guard())) {
    return fail("Only a registrar can manage staff accounts.", 403);
  }
  return ok(getDb().staff.map(publicStaff));
}

interface Body {
  name?: string;
  email?: string;
  title?: string;
  role?: string;
  password?: string;
}

export async function POST(request: Request) {
  const me = await guard();
  if (process.env.AUTH_PASSWORD && !me) return fail("Only a registrar can manage staff accounts.", 403);

  const body = (await request.json().catch(() => null)) as Body | null;
  const name = str(body?.name);
  const email = str(body?.email).toLowerCase();
  const password = str(body?.password);
  const role = coerceRole(body?.role);

  if (!name) return fail("Give the staff member a name.");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return fail("That email address does not look right.");
  const allowedDomains = getDb().settings.auth.allowedDomains;
  if (!emailAllowed(email, allowedDomains)) {
    return fail(`Staff accounts must use a registered domain (${describeDomains(allowedDomains)}).`);
  }
  if (password.length < 10) return fail("Use a password of at least 10 characters.");
  if (getDb().staff.some((member) => member.email.toLowerCase() === email)) {
    return fail(`${email} already has an account.`);
  }

  const created = await mutate((db) => {
    const staff: Staff = {
      id: newId("stf"),
      email,
      name,
      title: str(body?.title) || ROLE_DESCRIPTIONS[role].split(".")[0],
      role,
      passwordHash: hashPassword(password),
      createdAt: nowIso(),
      lastLoginAt: null,
      disabled: false,
      totp: emptyTotp(),
      passkeys: [],
    };
    db.staff.push(staff);
    logActivity(db, "settings.updated", `Added ${staff.name} as ${role}`, staff.id, me ? actorRef(me) : null);
    return staff;
  });

  // The vault account gets its own generated password, so the console login and
  // the vault never share one. It is handed back once, to whoever created the
  // account; a vault failure never blocks the console account.
  const secret = vaultPassword();
  const vault = await provisionVault(created.email, secret, created.name);
  if (vault.ok && vault.vault) {
    const link = { ...vault.vault, sharedPassword: verifyPassword(secret, created.passwordHash) };
    const linked = await mutate((db) => {
      const record = db.staff.find((member) => member.id === created.id) as Staff;
      record.vault = link;
      logActivity(
        db,
        "settings.updated",
        `Linked the Vaultwarden account for ${record.name}`,
        record.id,
        me ? actorRef(me) : null,
      );
      return record;
    });
    // Shown once: the vault password is generated here and never stored.
    return ok({ ...publicStaff(linked), vaultPassword: secret }, 201);
  }
  if (vault.error) {
    await mutate((db) => {
      logActivity(
        db,
        "settings.updated",
        `Vaultwarden account for ${created.name} was not linked: ${vault.error}`,
        created.id,
        me ? actorRef(me) : null,
      );
    });
  }
  return ok(publicStaff(created), 201);
}
