import { getDb, logActivity, mutate } from "@/lib/store";
import { num, ok, str, strArray } from "@/lib/api";
import { slugify } from "@/lib/seed";
import type { Program, Semester } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const db = getDb();
  return ok(db.programs);
}

interface Body {
  name?: string;
  credential?: string;
  credentialType?: Program["credentialType"];
  department?: string;
  summary?: string;
  totalCredits?: number;
  tuitionPerCreditCents?: number;
  semesters?: Semester[];
  status?: Program["status"];
  accreditation?: string;
}

const CREDENTIAL_TYPES = ["Bachelor", "Associate", "Master", "Certificate"] as const;

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Body | null;
  const name = str(body?.name);
  if (!name) return ok({ error: "A program name is required." }, 400);

  const created = await mutate((db) => {
    const credentialType = CREDENTIAL_TYPES.includes(body?.credentialType as "Bachelor")
      ? (body!.credentialType as Program["credentialType"])
      : "Bachelor";
    const program: Program = {
      id: `prog-${slugify(name)}`,
      slug: slugify(name),
      name,
      credential: str(body?.credential) || name,
      credentialType,
      department: str(body?.department) || name,
      summary: str(body?.summary),
      totalCredits: Math.max(1, num(body?.totalCredits, 120)),
      tuitionPerCreditCents: Math.max(0, num(body?.tuitionPerCreditCents, db.settings.tuitionPerCreditCents)),
      semesters: Array.isArray(body?.semesters) ? body!.semesters : [],
      status: "draft",
      accreditation: str(body?.accreditation) || db.settings.org,
      signaraTemplate: "degree-conferral",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    db.programs.push(program);
    logActivity(db, "program.updated", `Created program ${program.credential}`, program.id);
    return program;
  });

  return ok(created, 201);
}

export async function PATCH(request: Request) {
  const body = (await request.json().catch(() => null)) as { id?: string } & Body;
  const id = str(body?.id);
  if (!id) return ok({ error: "A program id is required." }, 400);

  const updated = await mutate((db) => {
    const program = db.programs.find((p) => p.id === id);
    if (!program) return null;
    if (body.name !== undefined) program.name = str(body.name) || program.name;
    if (body.credential !== undefined) program.credential = str(body.credential) || program.credential;
    if (body.department !== undefined) program.department = str(body.department);
    if (body.summary !== undefined) program.summary = str(body.summary);
    if (body.totalCredits !== undefined) program.totalCredits = Math.max(1, num(body.totalCredits, program.totalCredits));
    if (body.tuitionPerCreditCents !== undefined)
      program.tuitionPerCreditCents = Math.max(0, num(body.tuitionPerCreditCents, program.tuitionPerCreditCents));
    if (body.status !== undefined && ["active", "draft", "retired"].includes(str(body.status)))
      program.status = str(body.status) as Program["status"];
    if (body.accreditation !== undefined) program.accreditation = str(body.accreditation);
    if (Array.isArray(body.semesters)) {
      program.semesters = body.semesters.map((semester, i) => ({
        number: i + 1,
        focus: str(semester.focus),
        credits: num(semester.credits, 0),
        courses: Array.isArray(semester.courses)
          ? semester.courses
              .map((c) => ({ code: str(c.code).toUpperCase(), title: str(c.title) }))
              .filter((c) => c.code)
          : [],
      }));
    }
    program.updatedAt = new Date().toISOString();
    logActivity(db, "program.updated", `Updated ${program.credential}`, program.id);
    return program;
  });

  if (!updated) return ok({ error: "Program not found." }, 404);
  return ok(updated);
}
