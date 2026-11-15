import type { Database } from "./types";

/**
 * The audit trail as a file a registrar can keep. Every staff action the
 * console has recorded, newest first, with the actor denormalised so the row
 * stays meaningful after the account is renamed or removed.
 */

export const ACTION_LABELS: Record<string, string> = {
  "course.created": "Added a course",
  "course.published": "Published a course",
  "course.updated": "Edited a course",
  "program.updated": "Changed a program",
  "session.created": "Started a draft",
  "session.revised": "Revised a draft",
  "credential.issued": "Awarded a credential",
  "credential.signed": "Signed a credential",
  "credential.revoked": "Revoked a credential",
  "settings.updated": "Changed settings",
  "site.updated": "Updated the public site",
  "key.rotated": "Rotated the Signara key",
  "digest.sent": "Sent the operations digest",
};

export interface AuditRow {
  at: string;
  action: string;
  kind: string;
  detail: string;
  ref: string;
  actor: string;
  role: string;
  email: string;
}

export function auditRows(db: Database, staffId?: string | null): AuditRow[] {
  return db.activity
    .filter((item) => !staffId || item.actor?.id === staffId)
    .map((item) => ({
      at: item.at,
      action: ACTION_LABELS[item.kind] ?? item.kind,
      kind: item.kind,
      detail: item.message,
      ref: item.ref,
      actor: item.actor?.name ?? "Unattributed",
      role: item.actor?.role ?? "",
      email: item.actor?.email ?? "",
    }));
}

const HEADER = ["timestamp", "action", "detail", "reference", "staff", "role", "email"];

/** RFC 4180 quoting; CRLF rows so Excel opens it cleanly. */
export function auditCsv(db: Database, staffId?: string | null): string {
  const rows = auditRows(db, staffId).map((row) =>
    [row.at, row.action, row.detail, row.ref, row.actor, row.role, row.email].map(cell).join(","),
  );
  return `${HEADER.join(",")}\r\n${rows.join("\r\n")}${rows.length ? "\r\n" : ""}`;
}

function cell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function auditFileName(db: Database, staffId?: string | null): string {
  const member = staffId ? db.staff.find((record) => record.id === staffId) : null;
  const slug = member ? member.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") : "all-staff";
  return `atheniq-audit-${slug}-${new Date().toISOString().slice(0, 10)}.csv`;
}
