import { fail, ok, str } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { emailAllowed, describeDomains } from "@/lib/email-policy";
import { can } from "@/lib/staff-policy";
import { hashPassword, verifyPassword } from "@/lib/staff";
import { notifyAccessRequest } from "@/lib/alerts";
import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import { provisionVault, vaultPassword } from "@/lib/vaultwarden";

export const dynamic = "force-dynamic";

const PUBLIC_FIELDS = (request: { id: string; name: string; email: string; title: string; reason: string; status: string; createdAt: string }) => ({
  id: request.id,
  name: request.name,
  email: request.email,
  title: request.title,
  reason: request.reason,
  status: request.status,
  createdAt: request.createdAt,
});

/** Anyone on a registered domain may ask for an account; a registrar decides. */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as
    | { name?: string; email?: string; title?: string; reason?: string; password?: string }
    | null;
  if (!body) return fail("Invalid body.");

  const db = getDb();
  const name = str(body.name);
  const email = str(body.email).toLowerCase();
  const password = str(body.password);
  const reason = str(body.reason).slice(0, 500);

  if (!name) return fail("Enter your name.");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return fail("That email address does not look right.");
  if (!emailAllowed(email, db.settings.auth.allowedDomains)) {
    return fail(
      `Access requests are limited to registered domains (${describeDomains(db.settings.auth.allowedDomains)}).`,
      403,
    );
  }
  if (password.length < 10) return fail("Choose a password of at least 10 characters.");
  if (db.staff.some((member) => member.email.toLowerCase() === email)) {
    return fail("That address already has an account. Sign in instead.", 409);
  }
  if (db.accessRequests.some((entry) => entry.status === "pending" && entry.email === email)) {
    return fail("That address already has a request waiting for review.", 409);
  }
  if (db.accessRequests.filter((entry) => entry.status === "pending").length >= 25) {
    return fail("The request queue is full. Ask a registrar to review it.", 429);
  }

  const created = await mutate((store) => {
    const entry = {
      id: newId("req"),
      name,
      email,
      title: str(body.title).slice(0, 80),
      reason,
      passwordHash: hashPassword(password),
      status: "pending" as const,
      createdAt: nowIso(),
      decidedAt: null,
      decidedBy: null,
    };
    store.accessRequests.unshift(entry);
    return entry;
  });

  notifyAccessRequest(created);
  return ok({ received: true, id: created.id }, 201);
}

/** Registrars see the queue; the password hash never leaves the server. */
export async function GET() {
  if (process.env.AUTH_PASSWORD) {
    const me = await currentStaff();
    if (!can(me?.role, "staff")) return fail("Only a registrar can review access requests.", 403);
  }
  const pending = getDb().accessRequests.filter((entry) => entry.status === "pending");
  return ok(pending.map(PUBLIC_FIELDS));
}

export async function PATCH(request: Request) {
  if (process.env.AUTH_PASSWORD) {
    const me = await currentStaff();
    if (!can(me?.role, "staff")) return fail("Only a registrar can review access requests.", 403);
  }
  const body = (await request.json().catch(() => null)) as { id?: string; action?: string } | null;
  const id = str(body?.id);
  const action = str(body?.action);
  if (action !== "approve" && action !== "decline") return fail("Choose approve or decline.");

  const db = getDb();
  const entry = db.accessRequests.find((item) => item.id === id && item.status === "pending");
  if (!entry) return fail("That request is no longer pending.", 404);

  if (action === "decline") {
    await mutate((store) => {
      const record = store.accessRequests.find((item) => item.id === id);
      if (record) record.status = "declined";
    });
    return ok({ id, status: "declined" });
  }

  if (!emailAllowed(entry.email, db.settings.auth.allowedDomains)) {
    return fail("That domain is no longer registered, so the account cannot be created.", 409);
  }
  if (db.staff.some((member) => member.email.toLowerCase() === entry.email)) {
    return fail("That address already has an account.", 409);
  }

  const me = await currentStaff();
  const staffId = await mutate((store) => {
    const pending = store.accessRequests.find((item) => item.id === id);
    if (!pending) return null;
    const staff = {
      id: newId("stf"),
      email: pending.email,
      name: pending.name,
      title: pending.title || "Staff",
      role: "publisher" as const,
      passwordHash: pending.passwordHash,
      createdAt: nowIso(),
      lastLoginAt: null,
      disabled: false,
      totp: { secret: null, enabled: false, enrolledAt: null, recoveryCodes: [] },
      passkeys: [],
    };
    store.staff.push(staff);
    pending.status = "approved";
    pending.decidedAt = nowIso();
    pending.decidedBy = me?.id ?? null;
    logActivity(store, "settings.updated", `Approved access for ${staff.name}`, staff.id, me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null);
    return staff.id;
  });

  if (!staffId) return fail("That request is no longer pending.", 404);

  // The password chosen at request time is only stored hashed, so the vault
  // account gets its own generated one; the registrar who approved it is the
  // only person who sees it, once.
  const password = vaultPassword();
  const vault = await provisionVault(entry.email, password, entry.name);
  if (vault.ok && vault.vault) {
    await mutate((store) => {
      const record = store.staff.find((member) => member.id === staffId);
      // The generated vault password is usually different, but say so honestly.
      if (record) record.vault = { ...vault.vault!, sharedPassword: verifyPassword(password, entry.passwordHash) };
      logActivity(
        store,
        "settings.updated",
        `Linked the Vaultwarden account for ${record?.name ?? entry.name}`,
        staffId,
        me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null,
      );
    });
    return ok({ id, status: "approved", staffId, vault: vault.vault, vaultPassword: password });
  }
  if (vault.error) {
    await mutate((store) => {
      logActivity(
        store,
        "settings.updated",
        `Vaultwarden account for ${entry.name} was not linked: ${vault.error}`,
        staffId,
        me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null,
      );
    });
  }
  return ok({ id, status: "approved", staffId, vaultError: vault.error });
}
