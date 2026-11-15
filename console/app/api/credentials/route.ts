import fs from "node:fs";
import path from "node:path";
import { getDb, logActivity, mutate, newId, nowIso, verifyId } from "@/lib/store";
import { evidenceHash, submitToSignara } from "@/lib/signara";
import { programEligibility, trackEligibility } from "@/lib/eligibility";
import { fail, ok, str } from "@/lib/api";
import { allowed, currentActor } from "@/lib/current-staff";
import type { Credential, CredentialType, Learner } from "@/lib/types";

export const dynamic = "force-dynamic";

const TYPES: CredentialType[] = ["course_certificate", "track_credential", "degree_conferral"];

export async function GET() {
  const db = getDb();
  return ok(db.credentials.slice().sort((a, b) => b.createdAt.localeCompare(a.createdAt)));
}

interface Body {
  type?: string;
  subjectRef?: string;
  learnerId?: string;
  learner?: { username?: string; name?: string; email?: string };
  grade?: string;
  completedOn?: string;
  credits?: number;
  gpa?: string;
  override?: boolean;
  autoSign?: boolean;
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Body | null;
  const type = str(body?.type) as CredentialType;
  const subjectRef = str(body?.subjectRef);

  if (!TYPES.includes(type)) return fail("Choose a credential type.");
  if (!subjectRef) return fail("Choose what the award is for.");
  if (!(await allowed("award"))) {
    return fail("Only a registrar can award credentials.", 403);
  }
  const actor = await currentActor();

  const db = getDb();
  const settings = db.settings;

  // Resolve the learner: an existing record, or a new one from the form.
  let learner: Learner | undefined = body?.learnerId
    ? db.learners.find((l) => l.id === body.learnerId)
    : undefined;

  if (!learner && body?.learner?.email) {
    const email = str(body.learner.email).toLowerCase();
    learner =
      db.learners.find((l) => l.email.toLowerCase() === email) ??
      (await mutate((database) => {
        const created: Learner = {
          id: newId("lrn"),
          username: str(body?.learner?.username) || email.split("@")[0],
          name: str(body?.learner?.name) || email.split("@")[0],
          email: str(body!.learner!.email),
          programId: type === "degree_conferral" ? subjectRef : null,
          enrolledAt: nowIso(),
        };
        database.learners.push(created);
        return created;
      }));
  }

  if (!learner) return fail("Choose a learner, or give a name and email.");

  const learnerRecord = learner;
  let title = "";
  let subjectLabel = "";
  let template = settings.signara.defaultTemplate;
  let evidence: Credential["evidence"] = {};

  if (type === "course_certificate") {
    const course = db.courses.find((c) => c.key === subjectRef);
    if (!course) return fail("That course is not in the catalog.", 404);
    const completion = db.completions.find(
      (c) => c.learnerId === learnerRecord.id && c.courseKey === course.key && c.status === "pass",
    );
    if (!completion && !body?.override) {
      return fail(`${learnerRecord.name} has no passing completion for ${course.code}. Use the manual override to award anyway.`, 422);
    }
    title = `${course.title} — Certificate of Completion (${learnerRecord.name})`;
    subjectLabel = course.title;
    template = settings.signara.defaultTemplate;
    evidence = {
      grade: str(body?.grade) || completion?.grade || "Pass",
      completedOn: str(body?.completedOn) || completion?.completedOn || nowIso().slice(0, 10),
      courses: [course.key],
    };
  } else if (type === "track_credential") {
    const track = db.tracks.find((t) => t.id === subjectRef);
    if (!track) return fail("That track does not exist.", 404);
    const eligibility = trackEligibility(db, track, learnerRecord);
    if (!eligibility.eligible && !body?.override) {
      return fail(
        `${learnerRecord.name} has ${eligibility.missing.length} course(s) outstanding on ${track.title}. Use the manual override to award anyway.`,
        422,
      );
    }
    title = `${track.credential.title} (${learnerRecord.name})`;
    subjectLabel = track.credential.title;
    template = track.credential.signara_template || settings.signara.defaultTemplate;
    evidence = {
      grade: "Pass",
      completedOn: str(body?.completedOn) || nowIso().slice(0, 10),
      courses: track.courses,
    };
  } else {
    const program = db.programs.find((p) => p.id === subjectRef);
    if (!program) return fail("That program does not exist.", 404);
    const eligibility = programEligibility(db, program, learnerRecord);
    if (!eligibility.eligible && !body?.override) {
      return fail(
        `${learnerRecord.name} has ${eligibility.creditsEarned} of ${eligibility.creditsRequired} credits. Use the manual override to confer anyway.`,
        422,
      );
    }
    title = `${program.credential} — ${learnerRecord.name}`;
    subjectLabel = program.credential;
    template = program.signaraTemplate || "degree-conferral";
    evidence = {
      credits: body?.credits ?? eligibility.creditsEarned,
      gpa: str(body?.gpa) || eligibility.gpa,
      program: program.name,
      completedOn: str(body?.completedOn) || nowIso().slice(0, 10),
    };
  }

  const at = nowIso();
  const withoutHash: Omit<Credential, "hash"> = {
    id: newId("cred"),
    verifyId: verifyId(),
    type,
    title,
    subjectRef,
    subjectLabel,
    learner: {
      username: learnerRecord.username,
      name: learnerRecord.name,
      email: learnerRecord.email,
    },
    evidence,
    status: "draft",
    signara: {
      documentId: null,
      requestId: null,
      signerToken: null,
      apiBase: null,
      lastHttp: null,
      lastError: null,
    },
    template,
    signer: settings.signer,
    previewPath: null,
    createdAt: at,
    updatedAt: at,
    signedAt: null,
    issuedAt: null,
    revokedAt: null,
    revokeReason: null,
    timeline: [{ at, label: "Award created", detail: `${type.replace(/_/g, " ")} — ${subjectLabel}` }],
  };

  const credential: Credential = { ...withoutHash, hash: evidenceHash(withoutHash) };

  const signing = await submitToSignara(credential, {
    ...settings.signara,
    autoSign: body?.autoSign === undefined ? settings.signara.autoSign : Boolean(body.autoSign),
  });

  // Keep the exact document that was sent for signing on disk.
  const certDir = path.join(process.cwd(), "data", "certificates");
  fs.mkdirSync(certDir, { recursive: true });
  fs.writeFileSync(path.join(certDir, `${credential.verifyId}.pdf`), signing.pdf);
  credential.previewPath = `/api/credentials/${credential.id}/certificate`;
  credential.timeline.push(...signing.timeline);

  if (signing.status === "signed") {
    credential.status = "issued";
    credential.signedAt = nowIso();
    credential.issuedAt = credential.signedAt;
    credential.timeline.push({ at: credential.issuedAt, label: "Issued to learner record" });
  } else if (signing.status === "partial") {
    credential.status = "partial";
  } else if (signing.status === "failed") {
    credential.status = "failed";
  } else {
    credential.status = "queued_local";
  }

  credential.signara = signing.signara;
  credential.updatedAt = nowIso();

  const saved = await mutate((database) => {
    database.credentials.unshift(credential);
    logActivity(
      database,
      credential.status === "issued" ? "credential.signed" : "credential.issued",
      `${credential.status === "issued" ? "Signed and issued" : "Staged"} ${subjectLabel} for ${credential.learner.name}`,
      credential.id,
      actor,
    );
    return credential;
  });

  return ok(saved, 201);
}
