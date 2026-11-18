import { consoleOrigin } from "./branding";
import { digestRecipients, mailerConfig, sendMail } from "./mailer";
import { getDb } from "./store";
import type { AccessRequest, Staff } from "./types";

/**
 * Registrar alerts over the same mail relay as the operations digest.
 *
 * Everything here is best-effort: a missing relay, a refused request or a slow
 * endpoint must never change the answer the person signing in (or asking for an
 * account) receives. Nothing is queued or retried — an alert that cannot be
 * sent is dropped.
 */

const FAILURE_WINDOW_MS = 15 * 60_000;
const FAILURE_THRESHOLD = 3;
const quietUntil = new Map<string, number>();

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Console links in mail, never the brand domain that serves the public site. */
function consoleBase(): string {
  return consoleOrigin(getDb().settings.brand.domain);
}

/** The configured security address, else every registrar, else the digest list. */
function recipients(): string[] {
  const db = getDb();
  const dedicated = digestRecipients(db.settings.mail.alertsTo || "");
  if (dedicated.length) return Array.from(new Set(dedicated));
  const registrars = db.staff
    .filter((member) => member.role === "registrar" && !member.disabled)
    .map((member) => member.email);
  const list = registrars.length ? registrars : digestRecipients(db.settings.mail.digestTo);
  return Array.from(new Set(list.filter((value) => /.+@.+/.test(value))));
}

export function alertsConfigured(): boolean {
  return mailerConfig().configured;
}

/** Who an alert would reach right now — shown by the test button. */
export function alertRecipients(): string[] {
  return recipients();
}

async function deliver(subject: string, text: string, html: string): Promise<void> {
  if (!mailerConfig().configured) return;
  const to = recipients();
  if (to.length === 0) return;
  try {
    await sendMail({ to, subject, text, html });
  } catch {
    /* an alert is never worth failing the request that triggered it */
  }
}

function frame(title: string, rows: string, footer: string): string {
  const brand = getDb().settings.brand;
  return `<!doctype html>
<html><body style="margin:0;padding:24px;background:#f4f8f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0b1a16;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #dce9e4;border-radius:14px;overflow:hidden;">
    <div style="padding:18px 22px;background:${brand.accent};color:#04110d;">
      <div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;opacity:.75;">${escapeHtml(brand.siteName)}</div>
      <div style="font-size:19px;font-weight:700;margin-top:4px;">${escapeHtml(title)}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">${rows}</table>
    <div style="padding:12px 22px;background:#f0f6f3;font-size:12px;color:#46605a;">${footer}</div>
  </div>
</body></html>`;
}

function row(label: string, value: string): string {
  return `<tr>
    <td style="padding:9px 22px;border-bottom:1px solid #eef4f1;color:#6b827c;width:38%;">${escapeHtml(label)}</td>
    <td style="padding:9px 22px;border-bottom:1px solid #eef4f1;">${escapeHtml(value)}</td>
  </tr>`;
}

/** Someone on a registered domain asked for an account. */
export function notifyAccessRequest(entry: AccessRequest): void {
  if (!mailerConfig().configured) return;
  const db = getDb();
  const lines = [
    `${entry.name} <${entry.email}> asked for staff access.`,
    entry.title ? `Title: ${entry.title}` : "",
    entry.reason ? `Reason: ${entry.reason}` : "",
    "",
    "Approve or decline it on the Staff page of the console.",
  ].filter(Boolean);
  const rows =
    row("Name", entry.name) +
    row("Email", entry.email) +
    (entry.title ? row("Title", entry.title) : "") +
    (entry.reason ? row("Reason", entry.reason) : "") +
    row("Asked", entry.createdAt);
  void deliver(
    `Access request — ${entry.name}`,
    lines.join("\n"),
    frame(`Access request — ${entry.name}`, rows, `Review at ${consoleBase()}/staff`),
  );
}

/** Someone applied to a program; admissions reads it from the console. */
export function notifyApplication(
  app: {
    name: string;
    email: string;
    programName: string;
    term: string;
    goals: string;
    transcript: { fileName: string } | null;
    createdAt: string;
  },
): void {
  if (!mailerConfig().configured) return;
  const rows =
    row("Applicant", `${app.name} <${app.email}>`) +
    row("Program", app.programName) +
    row("Term", app.term) +
    row("Transcript", app.transcript ? app.transcript.fileName : "not attached") +
    row("Goals", app.goals.slice(0, 400)) +
    row("Applied", app.createdAt);
  const text = [
    `${app.name} <${app.email}> applied to ${app.programName} for ${app.term}.`,
    app.transcript ? `Transcript: ${app.transcript.fileName}` : "No transcript attached.",
    app.goals ? `Goals: ${app.goals.slice(0, 400)}` : "",
    "",
    "Read it, download the transcript and set a status on the Admissions page of the console.",
  ].filter(Boolean);
  void deliver(
    `Application — ${app.name}`, 
    text.join("\n"),
    frame(`Application — ${app.name}`, rows, `Review at ${consoleBase()}/admissions`),
  );
}

/**
 * Three refusals for one address inside fifteen minutes is worth a look. One
 * alert per address per window, so a bot hammering the form cannot flood inboxes.
 */
export function noteAuthFailure(email: string, outcome: string): void {
  if (!mailerConfig().configured) return;
  const key = email.trim().toLowerCase();
  if (!key || key === "unknown") return;
  const now = Date.now();
  if ((quietUntil.get(key) ?? 0) > now) return;

  const db = getDb();
  const recent = db.authLog.filter(
    (event) =>
      event.email.trim().toLowerCase() === key &&
      event.outcome !== "success" &&
      now - new Date(event.at).getTime() <= FAILURE_WINDOW_MS,
  );
  if (recent.length < FAILURE_THRESHOLD) return;

  quietUntil.set(key, now + FAILURE_WINDOW_MS);
  const attempted = Array.from(new Set(recent.map((event) => event.outcome))).join(", ");
  const text = [
    `${recent.length} refused sign-in attempts for ${email} in the last 15 minutes.`,
    `Latest: ${outcome}`,
    `Outcomes: ${attempted}`,
    "",
    "If this was not the account owner, reset the account's password and two-factor on the Staff page.",
  ].join("\n");
  const rows =
    row("Address", email) +
    row("Attempts", String(recent.length)) +
    row("Latest", outcome) +
    row("Outcomes", attempted);
  void deliver(
    `Repeated sign-in failures — ${email}`,
    text,
    frame("Repeated sign-in failures", rows, `Security detail: ${consoleBase()}/security`),
  );
}

/**
 * A sign-in from an address this account has never used. Loopback is skipped —
 * "this computer" is the machine running the console, which already holds the
 * store — so the alert means the sign-in arrived over the network.
 */
export function notifyNewSource(staff: Staff, source: string): void {
  if (!mailerConfig().configured || source === "this computer") return;
  const db = getDb();
  const when = new Date().toISOString();
  const rows =
    row("Person", `${staff.name} <${staff.email}>`) +
    row("Signed in from", source) +
    row("When", when);
  const text = [
    `${staff.name} <${staff.email}> signed in from a source this account has never used before.`,
    `Source: ${source}`,
    "",
    "If this was not them, end the session on the Security page and reset their two-factor.",
  ].join("\n");
  void deliver(
    `New sign-in source — ${staff.name}`,
    text,
    frame(`New sign-in source — ${staff.name}`, rows, `Security detail: ${consoleBase()}/security`),
  );
}

/** A registrar changed someone's access; the sessions that change ended go with it. */
export function notifyAccessChange(
  person: { name: string; email: string },
  change: string,
  actor: { name: string; email: string } | null,
  sessionsEnded: number,
): void {
  if (!mailerConfig().configured) return;
  const db = getDb();
  const rows =
    row("Person", `${person.name} <${person.email}>`) +
    row("Change", change) +
    row("Made by", actor ? actor.name : "the console") +
    row("Live sessions ended", String(sessionsEnded));
  const text = [
    `${change} for ${person.name} <${person.email}>.`,
    `Made by ${actor ? actor.name : "the console"}.`,
    `${sessionsEnded} live session(s) ended; they sign in again with their second factor.`,
    "",
    `Staff record: ${consoleBase()}/staff`,
  ].join("\n");
  void deliver(
    `Access changed — ${person.name}`,
    text,
    frame(`Access changed — ${person.name}`, rows, `Staff record: ${consoleBase()}/staff`),
  );
}
