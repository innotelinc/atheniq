import { fail, ok, str } from "@/lib/api";
import { currentActor, allowed } from "@/lib/current-staff";
import { integrationHealth } from "@/lib/health";
import { buildDigest, mailerConfig, sendMail } from "@/lib/mailer";
import { getDb, logActivity, mutate } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * GET  — the digest as it would be sent (so it can be read without mail).
 * POST — send it now, either from the console or from a scheduler holding
 *        DIGEST_TOKEN (`Authorization: Bearer <token>` or `?token=`).
 */
async function authorize(request: Request): Promise<"console" | "cron" | null> {
  if (await allowed("settings")) return "console";
  const url = new URL(request.url);
  const token =
    (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim() ||
    (url.searchParams.get("token") || "").trim();
  if (process.env.DIGEST_TOKEN && token && token === process.env.DIGEST_TOKEN) return "cron";
  return null;
}

export async function GET(request: Request) {
  if ((await authorize(request)) === null) return fail("Only a registrar can read the digest.", 403);
  const db = getDb();
  const health = await integrationHealth(db.settings);
  const digest = buildDigest(db, health);
  return ok({
    subject: digest.subject,
    text: digest.text,
    html: digest.html,
    recipients: digest.recipients,
    mailConfigured: mailerConfig().configured,
    lastDigestAt: db.settings.mail.lastDigestAt,
    cadenceDays: db.settings.mail.cadenceDays,
  });
}

export async function POST(request: Request) {
  const mode = await authorize(request);
  if (mode === null) return fail("Only a registrar can send the digest.", 403);

  const db = getDb();
  const health = await integrationHealth(db.settings);
  const digest = buildDigest(db, health);
  if (!digest.recipients.length) {
    return fail("No digest recipients — add at least one address on the health page.", 400);
  }

  const result = await sendMail({
    to: digest.recipients,
    subject: digest.subject,
    text: digest.text,
    html: digest.html,
  });

  if (!result.ok) {
    return fail(result.detail, result.skipped ? 503 : 502, {
      skipped: Boolean(result.skipped),
      recipients: digest.recipients,
      preview: digest.text,
    });
  }

  const actor = mode === "cron" ? null : await currentActor();
  await mutate((store) => {
    store.settings.mail.lastDigestAt = new Date().toISOString();
    logActivity(
      store,
      "digest.sent",
      `Emailed the operations digest to ${digest.recipients.join(", ")}`,
      "digest",
      actor,
    );
  });

  return ok({
    detail: result.detail,
    id: result.id,
    recipients: digest.recipients,
    subject: digest.subject,
    lastDigestAt: new Date().toISOString(),
  });
}

export async function PUT(request: Request) {
  if (!(await allowed("settings"))) return fail("Only a registrar can change digest settings.", 403);
  const body = (await request.json().catch(() => null)) as
    | { digestTo?: string; cadenceDays?: number; alertsTo?: string }
    | null;
  if (!body) return fail("Invalid body.");
  const cadence = Number(body.cadenceDays);
  const updated = await mutate((store) => {
    if (body.digestTo !== undefined) store.settings.mail.digestTo = str(body.digestTo);
    if (body.alertsTo !== undefined) store.settings.mail.alertsTo = str(body.alertsTo);
    if (Number.isFinite(cadence)) {
      store.settings.mail.cadenceDays = Math.min(90, Math.max(1, Math.round(cadence)));
    }
    logActivity(store, "settings.updated", "Updated the operations digest recipients", "mail");
    return store.settings.mail;
  });
  return ok(updated);
}
