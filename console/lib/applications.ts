import fs from "node:fs";
import path from "node:path";
import type { Application, ApplicationStatus, TranscriptRef } from "./types";

/**
 * Admissions records and the transcripts that arrive with them.
 *
 * The applicant writes one form; the console keeps the whole record in the
 * store and the uploaded file on disk beside it. Nothing here accepts a path
 * from a client: the stored name is derived from the application id, so a
 * crafted filename cannot escape the directory it is written to.
 */

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "received",
  "reviewing",
  "accepted",
  "waitlisted",
  "declined",
];

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  received: "Received",
  reviewing: "Under review",
  accepted: "Accepted",
  waitlisted: "Waitlisted",
  declined: "Declined",
};

/** The statuses admissions still owes an answer on. */
export const OPEN_STATUSES: ApplicationStatus[] = ["received", "reviewing"];

/** Deciding one of these is what finishes an application. */
export const DECIDED_STATUSES: ApplicationStatus[] = ["accepted", "waitlisted", "declined"];

export function isApplicationStatus(value: string): value is ApplicationStatus {
  return (APPLICATION_STATUSES as string[]).includes(value);
}

const TRANSCRIPT_DIR = path.join(process.cwd(), "data", "transcripts");

export const TRANSCRIPT_MAX_BYTES = 10 * 1024 * 1024;

/** Only formats a registrar can open without installing anything. */
const TRANSCRIPT_TYPES: Record<string, string> = {
  "application/pdf": "pdf",
  "image/png": "png",
  "image/jpeg": "jpg",
};

export const TRANSCRIPT_HELP = "PDF, PNG or JPEG, up to 10 MB.";

export function saveTranscript(applicationId: string, file: File): Promise<TranscriptRef> {
  return (async () => {
    const extension = TRANSCRIPT_TYPES[file.type];
    if (!extension) throw new Error(`Attach the transcript as a ${TRANSCRIPT_HELP}`);
    if (file.size === 0) throw new Error("That transcript file is empty.");
    if (file.size > TRANSCRIPT_MAX_BYTES) {
      throw new Error("That transcript is larger than 10 MB. Send the pages you have as a PDF.");
    }
    // Named after the application, never after the upload: this is the only
    // thing that reaches the filesystem.
    const storedAs = `${applicationId}.${extension}`;
    const bytes = Buffer.from(await file.arrayBuffer());
    fs.mkdirSync(TRANSCRIPT_DIR, { recursive: true });
    fs.writeFileSync(path.join(TRANSCRIPT_DIR, storedAs), bytes);
    return {
      fileName: (file.name || `transcript.${extension}`).slice(0, 160),
      mimeType: file.type,
      bytes: bytes.length,
      storedAs,
      uploadedAt: new Date().toISOString(),
    };
  })();
}

export function transcriptFile(storedAs: string): { path: string; bytes: number } | null {
  const base = path.basename(storedAs);
  if (!base) return null;
  const full = path.join(TRANSCRIPT_DIR, base);
  try {
    const stat = fs.statSync(full);
    if (!stat.isFile()) return null;
    return { path: full, bytes: stat.size };
  } catch {
    return null;
  }
}

export function removeTranscript(storedAs: string): void {
  try {
    fs.rmSync(path.join(TRANSCRIPT_DIR, path.basename(storedAs)), { force: true });
  } catch {
    /* a lost upload is not worth failing the request that noticed it */
  }
}

/** What the staff surfaces show: the record, with the transcript named. */
export function applicationView(app: Application) {
  return {
    id: app.id,
    name: app.name,
    email: app.email,
    phone: app.phone,
    programId: app.programId,
    programName: app.programName,
    term: app.term,
    goals: app.goals,
    status: app.status,
    statusLabel: STATUS_LABELS[app.status],
    note: app.note,
    createdAt: app.createdAt,
    updatedAt: app.updatedAt,
    decidedAt: app.decidedAt,
    decidedBy: app.decidedBy,
    transcript: app.transcript
      ? {
          fileName: app.transcript.fileName,
          mimeType: app.transcript.mimeType,
          bytes: app.transcript.bytes,
          uploadedAt: app.transcript.uploadedAt,
        }
      : null,
  };
}
