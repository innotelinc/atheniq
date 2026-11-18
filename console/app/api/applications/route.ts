import { fail, ok, str } from "@/lib/api";
import { notifyApplication } from "@/lib/alerts";
import {
  DECIDED_STATUSES,
  OPEN_STATUSES,
  STATUS_LABELS,
  applicationView,
  isApplicationStatus,
  removeTranscript,
  saveTranscript,
} from "@/lib/applications";
import { currentStaff } from "@/lib/current-staff";
import { requestSource } from "@/lib/request-source";
import { authEnabled } from "@/lib/session";
import { can } from "@/lib/staff-policy";
import { getDb, logActivity, mutate, newId, nowIso } from "@/lib/store";
import { termLabel, termOptions } from "@/lib/term";
import type { Application } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Applications are admissions' business: a registrar answers them. */
async function staffOnly(): Promise<boolean> {
  if (!authEnabled()) return true;
  const me = await currentStaff();
  return can(me?.role, "staff");
}

/**
 * The public application form: program, term, goals statement and transcript.
 *
 * It is a multipart POST because of the upload — one request, one record, so an
 * application cannot arrive without the transcript (or the transcript without a
 * record). The transcript is written under the application id; nothing a client
 * sends is used as a path.
 */
export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return fail("The form could not be read. Try again, or email admissions instead.");
  }

  const name = str(form.get("name")).slice(0, 120);
  const email = str(form.get("email")).toLowerCase().slice(0, 200);
  const phone = str(form.get("phone")).slice(0, 40);
  const programId = str(form.get("programId"));
  const term = str(form.get("term"));
  const goals = str(form.get("goals")).slice(0, 4000);
  const upload = form.get("transcript");

  if (!name) return fail("Enter your full name.");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return fail("That email address does not look right.");

  const db = getDb();
  const program = db.programs.find((entry) => entry.id === programId && entry.status === "active");
  if (!program) return fail("Choose the program you are applying to.");
  if (!termOptions().includes(term)) return fail("Choose the term you are applying for.");
  if (goals.length < 40) {
    return fail("Write a few sentences about your goals — at least 40 characters is enough to start.");
  }
  if (!(upload instanceof File) || upload.size === 0) {
    return fail("Attach your transcript as a PDF, PNG or JPEG (up to 10 MB).");
  }

  if (
    db.applications.some(
      (entry) =>
        entry.email === email &&
        entry.programId === program.id &&
        entry.term === term &&
        OPEN_STATUSES.includes(entry.status),
    )
  ) {
    return fail("You already have an application under review for that program and term.", 409);
  }
  const open = db.applications.filter((entry) => OPEN_STATUSES.includes(entry.status)).length;
  if (open >= 300) return fail("The admissions queue is full. Contact admissions and they will clear it.", 429);

  const id = newId("app");
  let transcript;
  try {
    transcript = await saveTranscript(id, upload);
  } catch (error) {
    return fail(error instanceof Error ? error.message : "The transcript could not be stored.");
  }

  const created = await mutate((store) => {
    const entry: Application = {
      id,
      name,
      email,
      phone,
      programId: program.id,
      programName: program.name,
      term,
      goals,
      transcript,
      status: "received",
      note: "",
      source: requestSource(request),
      createdAt: nowIso(),
      updatedAt: nowIso(),
      decidedAt: null,
      decidedBy: null,
    };
    store.applications.unshift(entry);
    logActivity(
      store,
      "application.received",
      `${name} applied to ${program.name} for ${termLabel(term)}`,
      id,
      null,
    );
    return entry;
  }).catch((error) => {
    // The record did not land, so the upload is an orphan: drop it rather than
    // leave a file no application points at.
    removeTranscript(transcript.storedAs);
    throw error;
  });

  notifyApplication({
    name: created.name,
    email: created.email,
    programName: created.programName,
    term: termLabel(created.term),
    goals: created.goals,
    transcript: created.transcript,
    createdAt: created.createdAt,
  });

  return ok({ received: true, id: created.id }, 201);
}

/** Admissions' queue, for a caller that wants JSON. The page reads the store. */
export async function GET() {
  if (!(await staffOnly())) return fail("Only a registrar can read applications.", 403);
  return ok(getDb().applications.map(applicationView));
}

/**
 * A registrar moves an application along and says why. "Accepted" and the other
 * decisions stamp who decided and when; "under review" only records the change.
 */
export async function PATCH(request: Request) {
  if (!(await staffOnly())) return fail("Only a registrar can decide applications.", 403);

  const body = (await request.json().catch(() => null)) as
    | { id?: string; status?: string; note?: string }
    | null;
  const id = str(body?.id);
  const status = str(body?.status);
  if (!isApplicationStatus(status)) return fail("Choose a status from the list.");
  const note = str(body?.note).slice(0, 500);

  const me = await currentStaff();
  const actor = me ? { id: me.id, name: me.name, email: me.email, role: me.role } : null;

  const updated = await mutate((store) => {
    const entry = store.applications.find((item) => item.id === id);
    if (!entry) return null;
    const before = entry.status;
    entry.status = status;
    entry.note = note;
    entry.updatedAt = nowIso();
    if (DECIDED_STATUSES.includes(status)) {
      entry.decidedAt = nowIso();
      entry.decidedBy = me?.id ?? null;
    } else {
      entry.decidedAt = null;
      entry.decidedBy = null;
    }
    logActivity(
      store,
      "application.decided",
      `${entry.name}: ${STATUS_LABELS[before]} → ${STATUS_LABELS[status]} (${entry.programName})`,
      entry.id,
      actor,
    );
    return entry.status;
  });

  if (!updated) return fail("That application is gone.", 404);
  return ok({ id, status: updated });
}
