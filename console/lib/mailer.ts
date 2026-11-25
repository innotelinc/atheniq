import nodemailer from "nodemailer";
import { money } from "./format";
import type { IntegrationHealth } from "./health";
import type { Database } from "./types";

/**
 * Outbound mail for alerts and the operations digest.
 *
 * Two transports, picked by configuration:
 *   - SMTP submission (MAIL_SMTP_HOST/USER/PASS), which is what this deployment
 *     uses: the school's own Stalwart server at mail.innotel.us;
 *   - an HTTP relay that accepts `POST {from,to,subject,text,html}` with a bearer
 *     key, Resend's API by default.
 * Either way the console builds and previews mail without a relay present.
 */

const DEFAULT_ENDPOINT = "https://api.resend.com/emails";

export function mailerConfig() {
  const apiKey = (process.env.MAIL_API_KEY || "").trim();
  const from = (process.env.MAIL_FROM || "").trim();
  const endpoint = (process.env.MAIL_API_URL || DEFAULT_ENDPOINT).trim();
  const host = (process.env.MAIL_SMTP_HOST || "").trim();
  const user = (process.env.MAIL_SMTP_USER || "").trim();
  const pass = process.env.MAIL_SMTP_PASS || "";
  const port = Number(process.env.MAIL_SMTP_PORT || 465);
  // 465 is implicit TLS; 587/25 start plain and upgrade with STARTTLS.
  const secure = (process.env.MAIL_SMTP_SECURE || (port === 465 ? "1" : "0")) !== "0";
  const smtpReady = Boolean(host && user && pass);
  return {
    apiKey,
    from,
    endpoint,
    smtp: { host, user, pass, port, secure, ready: smtpReady },
    configured: Boolean(from && (smtpReady || apiKey)),
  };
}

export interface MailMessage {
  to: string[];
  subject: string;
  text: string;
  html: string;
}

export interface MailResult {
  ok: boolean;
  detail: string;
  id: string | null;
  skipped?: boolean;
}

export async function sendMail(message: MailMessage): Promise<MailResult> {
  const { apiKey, from, endpoint, configured, smtp } = mailerConfig();
  if (!configured) {
    return {
      ok: false,
      skipped: true,
      id: null,
      detail: "No mail sender configured — set MAIL_SMTP_HOST/USER/PASS (or MAIL_API_KEY) and MAIL_FROM in .env.",
    };
  }

  if (smtp.ready) {
    try {
      const transport = nodemailer.createTransport({
        host: smtp.host,
        port: smtp.port,
        secure: smtp.secure,
        auth: { user: smtp.user, pass: smtp.pass },
        connectionTimeout: 15_000,
        greetingTimeout: 15_000,
        socketTimeout: 25_000,
      });
      const info = await transport.sendMail({
        from,
        to: message.to.join(", "),
        subject: message.subject,
        text: message.text,
        html: message.html,
      });
      return {
        ok: true,
        id: info.messageId ?? null,
        detail: `Sent to ${message.to.join(", ")} through ${smtp.host}.`,
      };
    } catch (error) {
      return {
        ok: false,
        id: null,
        detail: `SMTP send failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from,
        to: message.to,
        subject: message.subject,
        text: message.text,
        html: message.html,
      }),
      signal: AbortSignal.timeout(20_000),
    });
    const text = await response.text();
    let id: string | null = null;
    try {
      id = (JSON.parse(text) as { id?: string }).id ?? null;
    } catch {
      /* relays that answer plain text */
    }
    return {
      ok: response.ok,
      id,
      detail: response.ok
        ? `Sent to ${message.to.join(", ")}${id ? ` (id ${id.slice(0, 12)})` : ""}.`
        : `Mail relay returned HTTP ${response.status}: ${text.slice(0, 160)}`,
    };
  } catch (error) {
    return {
      ok: false,
      id: null,
      detail: `Could not reach the mail relay: ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

export function digestRecipients(digestTo: string): string[] {
  return digestTo
    .split(/[,;]/)
    .map((value) => value.trim())
    .filter((value) => /.+@.+/.test(value));
}

export interface Digest {
  subject: string;
  text: string;
  html: string;
  recipients: string[];
}

export function buildDigest(db: Database, health: IntegrationHealth, at = new Date()): Digest {
  const settings = db.settings;
  const brand = settings.brand;
  const day = at.toISOString().slice(0, 10);

  const published = db.courses.filter((course) => course.status === "published");
  const issued = db.credentials.filter((credential) => ["issued", "signed"].includes(credential.status));
  const pending = db.credentials.filter((credential) =>
    ["queued_local", "partial", "failed", "draft"].includes(credential.status),
  );
  const activePrograms = db.programs.filter((program) => program.status === "active");
  const recent = db.activity.slice(0, 6);
  const key = health.window;
  const failing = health.checks.filter((check) => !check.ok);

  const subject = `${brand.siteName} — operations digest ${day}`;
  const statusLine = health.healthy ? "All pipelines answering." : `Needs attention: ${failing.map((c) => c.label).join(", ") || key.label}.`;

  const text = [
    `${brand.siteName} — operations digest ${day}`,
    "",
    statusLine,
    "",
    "Pipelines",
    ...health.checks.map((check) => `  ${check.ok ? "OK  " : "FAIL"}  ${check.label}: ${check.detail}`),
    `  KEY   Signara key: ${key.label}. ${key.detail}`,
    "",
    "School",
    `  Catalog: ${published.length} published of ${db.courses.length} courses`,
    `  Programs: ${activePrograms.length} active`,
    `  Credentials: ${issued.length} issued, ${pending.length} waiting on signing`,
    `  Tuition: ${money(settings.tuitionPerCreditCents)} per credit (USD)`,
    "",
    "Recent activity",
    ...(recent.length
      ? recent.map((item) => `  ${item.at.slice(0, 10)}  ${item.message}${item.actor ? ` — ${item.actor.name}` : ""}`)
      : ["  Nothing recorded yet."]),
    "",
    `Public site: https://${brand.domain}${settings.site.published ? "" : " (not published)"}`,
    "",
    "Full detail: the console → Health.",
  ].join("\n");

  const checkRows = health.checks
    .map(
      (check) => `<tr>
        <td style="padding:7px 10px;border-bottom:1px solid #e6efeb;">${escapeHtml(check.label)}</td>
        <td style="padding:7px 10px;border-bottom:1px solid #e6efeb;font-weight:600;color:${check.ok ? "#047857" : "#c0393d"};">
          ${check.ok ? "OK" : "Failing"}
        </td>
        <td style="padding:7px 10px;border-bottom:1px solid #e6efeb;color:#46605a;">${escapeHtml(check.detail)}</td>
      </tr>`,
    )
    .join("");

  const activityRows = (recent.length ? recent : [])
    .map(
      (item) => `<tr>
        <td style="padding:6px 10px;border-bottom:1px solid #eef4f1;color:#6b827c;white-space:nowrap;">${item.at.slice(0, 10)}</td>
        <td style="padding:6px 10px;border-bottom:1px solid #eef4f1;">${escapeHtml(item.message)}${
          item.actor ? `<span style="color:#6b827c;"> — ${escapeHtml(item.actor.name)}</span>` : ""
        }</td>
      </tr>`,
    )
    .join("");

  const html = `<!doctype html>
<html><body style="margin:0;padding:24px;background:#f4f8f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0b1a16;">
  <div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #dce9e4;">
    <div style="padding:20px 24px;background:${brand.accent};color:#04110d;">
      <div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;opacity:.75;">${escapeHtml(brand.siteName)}</div>
      <div style="font-size:20px;font-weight:700;margin-top:4px;">Operations digest — ${day}</div>
    </div>
    <div style="padding:20px 24px;">
      <p style="margin:0 0 16px;font-size:15px;font-weight:600;">${escapeHtml(statusLine)}</p>
      <p style="margin:0 0 6px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#6b827c;">Signara key</p>
      <p style="margin:0 0 18px;font-size:14px;">${escapeHtml(key.label)} — ${escapeHtml(key.detail)}</p>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">${checkRows}</table>
      <div style="display:flex;gap:10px;margin:18px 0;font-size:13px;color:#0b1a16;">
        <div style="flex:1;background:#f0f6f3;border-radius:10px;padding:12px;">
          <div style="color:#6b827c;font-size:11px;text-transform:uppercase;letter-spacing:.08em;">Catalog</div>
          <div style="font-size:18px;font-weight:700;">${published.length}</div>
          <div style="color:#6b827c;">of ${db.courses.length} courses published</div>
        </div>
        <div style="flex:1;background:#f0f6f3;border-radius:10px;padding:12px;">
          <div style="color:#6b827c;font-size:11px;text-transform:uppercase;letter-spacing:.08em;">Credentials</div>
          <div style="font-size:18px;font-weight:700;">${issued.length}</div>
          <div style="color:#6b827c;">${pending.length} waiting on signing</div>
        </div>
        <div style="flex:1;background:#f0f6f3;border-radius:10px;padding:12px;">
          <div style="color:#6b827c;font-size:11px;text-transform:uppercase;letter-spacing:.08em;">Tuition</div>
          <div style="font-size:18px;font-weight:700;">${escapeHtml(money(settings.tuitionPerCreditCents))}</div>
          <div style="color:#6b827c;">per credit, USD</div>
        </div>
      </div>
      <p style="margin:18px 0 6px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#6b827c;">Recent activity</p>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">${activityRows || `<tr><td style="padding:6px 10px;color:#6b827c;">Nothing recorded yet.</td></tr>`}</table>
    </div>
    <div style="padding:14px 24px;background:#f0f6f3;font-size:12px;color:#46605a;">
      Public site: <strong>${escapeHtml(brand.domain)}</strong>${settings.site.published ? "" : " (not published)"}
    </div>
  </div>
</body></html>`;

  return { subject, text, html, recipients: digestRecipients(settings.mail.digestTo) };
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
