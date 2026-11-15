import { getDb, logActivity, mutate } from "@/lib/store";
import { buildCourse, coerceGrading, coerceLevel, coerceModules, nextCourseCode, normaliseCode } from "@/lib/courses";
import { num, ok, str, strArray } from "@/lib/api";
import { currentActor } from "@/lib/current-staff";
import { seedTerm } from "@/lib/term";
import type { Course } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  const db = getDb();
  return ok(
    db.courses.map((course) => ({
      id: course.id,
      code: course.code,
      key: course.key,
      title: course.title,
      status: course.status,
      credits: course.credits,
      price: course.price,
      programIds: course.programIds,
      trackIds: course.trackIds,
    })),
  );
}

interface Body {
  code?: string;
  title?: string;
  term?: string;
  credits?: number;
  level?: number;
  department?: string;
  summary?: string;
  description?: string;
  outcomes?: string[];
  audience?: string;
  prerequisites?: string[];
  modules?: unknown;
  grading?: unknown;
  plan?: string | null;
  amountCents?: number | null;
  programIds?: string[];
  trackIds?: string[];
  publishNow?: boolean;
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Body | null;
  if (!body) return ok(null, 400);

  const title = str(body.title);
  if (!title) return new Response(JSON.stringify({ ok: false, error: "A course title is required." }), { status: 400 });

  const actor = await currentActor();
  const result = await mutate((db) => {
    const term = str(body.term) || db.settings.defaultTerm || seedTerm();
    let code = normaliseCode(str(body.code));
    if (!code) {
      code = nextCourseCode(db, str(body.department) || "General Studies");
    }

    if (!/^[A-Z]{2,8}[0-9]{2,4}$/.test(code)) {
      throw new Error("Course codes look like BUS101 — 2–8 letters followed by 2–4 digits.");
    }
    if (db.courses.some((course) => course.code === code && course.term === term)) {
      throw new Error(`${code} already exists in ${term}.`);
    }

    const course = buildCourse(
      {
        code,
        title,
        term,
        credits: num(body.credits, db.settings.creditsPerCourse),
        level: coerceLevel(body.level, 100),
        department: str(body.department) || "General Studies",
        summary: str(body.summary) || `${title} — a new AthenIQ course.`,
        description: str(body.description),
        outcomes: strArray(body.outcomes),
        audience: str(body.audience),
        prerequisites: strArray(body.prerequisites),
        modules: coerceModules(body.modules),
        grading: coerceGrading(body.grading, []),
        price: {
          plan: body.plan === undefined ? "premium" : body.plan || null,
          amountCents: body.amountCents ?? null,
        },
        programIds: strArray(body.programIds),
        trackIds: strArray(body.trackIds),
      },
      db,
    );

    if (body.publishNow && course.modules.length > 0) {
      course.status = "in_review";
    }

    db.courses.push(course);
    logActivity(db, "course.created", `Created ${course.code} — ${title}`, course.key, actor);
    return course;
  }).catch((error: Error) => error);

  if (result instanceof Error) {
    return new Response(JSON.stringify({ ok: false, error: result.message }), { status: 400 });
  }
  return ok(result as Course, 201);
}
