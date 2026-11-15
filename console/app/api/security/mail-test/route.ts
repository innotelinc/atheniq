import { fail, ok } from "@/lib/api";
import { currentStaff } from "@/lib/current-staff";
import { alertRecipients, alertsConfigured } from "@/lib/alerts";
import { mailerConfig, sendMail } from "@/lib/mailer";
import { getDb } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * Prove the relay works without waiting for a real incident: send the same kind
 * of message a registrar alert uses, and answer with the relay's own result.
 */
export async function POST() {
  const me = await currentStaff();
  if (process.env.AUTH_PASSWORD && me?.role !== "registrar") {
    return fail("Only a registrar can send an alert test.", 403);
  }

  const to = alertRecipients();
  if (!alertsConfigured()) {
    return ok({
      configured: false,
      sent: false,
      detail: "No mail relay configured — set MAIL_API_KEY and MAIL_FROM in .env, then restart the console.",
      to,
    });
  }
  if (to.length === 0) {
    return ok({
      configured: true,
      sent: false,
      detail: "No registrar email address to send to.",
      to,
    });
  }

  const db = getDb();
  const result = await sendMail({
    to,
    subject: `${db.settings.brand.siteName} — registrar alert test`,
    text: [
      "This is a test of the registrar alert relay.",
      "",
      "When it carries a real alert it names the person asking for access, or the address",
      "that has failed to sign in three times in fifteen minutes.",
      "",
      `Sent from ${db.settings.brand.domain}.`,
    ].join("\n"),
    html: `<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px;color:#0b1a16;">
      <p style="font-weight:600;">This is a test of the registrar alert relay.</p>
      <p>When it carries a real alert it names the person asking for access, or the address that has failed to sign in three times in fifteen minutes.</p>
      <p style="color:#46605a;">Sent from ${db.settings.brand.domain}.</p>
    </div>`,
  });

  return ok({
    configured: mailerConfig().configured,
    sent: result.ok,
    detail: result.detail,
    skipped: result.skipped ?? false,
    to,
  });
}
