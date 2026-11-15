import { getDb, logActivity, mutate, nowIso } from "@/lib/store";
import { submitToSignara } from "@/lib/signara";
import { fail, ok, str } from "@/lib/api";
import { allowed, currentActor } from "@/lib/current-staff";
import type { Credential } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = getDb();
  const credential = db.credentials.find((c) => c.id === id);
  if (!credential) return fail("Credential not found.", 404);
  return ok(credential);
}

interface Body {
  action?: "retry" | "revoke" | "mark_issued";
  reason?: string;
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => null)) as Body | null;
  const action = str(body?.action);
  if (!(await allowed("award"))) return fail("Only a registrar can change an award.", 403);
  const actor = await currentActor();

  const db = getDb();
  const credential = db.credentials.find((c) => c.id === id);
  if (!credential) return fail("Credential not found.", 404);

  if (action === "retry") {
    if (credential.status === "revoked") return fail("A revoked award cannot be re-submitted.", 409);
    const signing = await submitToSignara(credential, db.settings.signara);
    const updated = await mutate((database) => {
      const target = database.credentials.find((c) => c.id === id) as Credential;
      target.signara = signing.signara;
      target.timeline.push(...signing.timeline);
      target.updatedAt = nowIso();
      if (signing.status === "signed") {
        target.status = "issued";
        target.signedAt = nowIso();
        target.issuedAt = target.signedAt;
        target.timeline.push({ at: target.issuedAt, label: "Issued to learner record" });
      } else if (signing.status === "partial") {
        target.status = "partial";
      } else if (signing.status === "failed") {
        target.status = "failed";
      } else {
        target.status = "queued_local";
      }
      logActivity(database, "credential.signed", `Re-submitted ${target.subjectLabel} to Signara`, target.id, actor);
      return target;
    });
    return ok({ credential: updated, error: signing.error });
  }

  if (action === "revoke") {
    const reason = str(body?.reason);
    const updated = await mutate((database) => {
      const target = database.credentials.find((c) => c.id === id) as Credential;
      target.status = "revoked";
      target.revokedAt = nowIso();
      target.revokeReason = reason || "Revoked by the registrar";
      target.updatedAt = target.revokedAt;
      target.timeline.push({ at: target.revokedAt, label: "Award revoked", detail: target.revokeReason ?? undefined });
      logActivity(database, "credential.revoked", `Revoked ${target.subjectLabel} for ${target.learner.name}`, target.id, actor);
      return target;
    });
    return ok(updated);
  }

  if (action === "mark_issued") {
    if (credential.status === "revoked") return fail("A revoked award cannot be issued.", 409);
    const updated = await mutate((database) => {
      const target = database.credentials.find((c) => c.id === id) as Credential;
      target.status = "issued";
      target.issuedAt = nowIso();
      target.updatedAt = target.issuedAt;
      target.timeline.push({ at: target.issuedAt, label: "Marked issued by the registrar" });
      return target;
    });
    return ok(updated);
  }

  return fail("Unknown action. Use retry, revoke or mark_issued.");
}
